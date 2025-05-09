"""
Полный OCR-пайплайн для обработки накладных.

Включает:
1. Детектор таблиц
2. OCR-обработчик
3. Валидационный пайплайн (арифметический + бизнес-правила)
"""
import os
import json
import logging
import asyncio
from typing import Dict, List, Any, Optional, Tuple
import base64

from app.detectors.table.factory import get_detector
from app.validators.pipeline import ValidationPipeline
from paddleocr import PaddleOCR
from app.ocr import call_openai_ocr

logger = logging.getLogger(__name__)

class OCRPipeline:
    """
    Полный OCR-пайплайн для обработки накладных.
    """
    
    def __init__(self, 
                 table_detector_method="paddle",
                 arithmetic_max_error=1.0, 
                 strict_validation=False,
                 paddle_ocr_lang="en"):
        """
        Инициализирует OCR-пайплайн.
        
        Args:
            table_detector_method: Метод детекции таблиц ('paddle', etc.)
            arithmetic_max_error: Максимальный процент ошибки для арифметического валидатора
            strict_validation: Строгий режим для валидатора бизнес-правил
            paddle_ocr_lang: Язык для PaddleOCR
        """
        self.table_detector = get_detector(method=table_detector_method)
        self.validation_pipeline = ValidationPipeline(
            arithmetic_max_error=arithmetic_max_error,
            strict_mode=strict_validation
        )
        self.paddle_ocr = PaddleOCR(use_angle_cls=True, lang=paddle_ocr_lang, show_log=False)
        self.low_conf_threshold = 0.7  # Порог уверенности для fallback на GPT-4o
    
    async def process_image(self, image_bytes: bytes, lang: List[str] = None) -> Dict[str, Any]:
        """
        Обрабатывает изображение накладной.
        
        Args:
            image_bytes: Бинарные данные изображения
            lang: Список языков для OCR (по умолчанию ['id', 'en'])
            
        Returns:
            Словарь с результатами распознавания и валидации
        """
        if lang is None:
            lang = ['id', 'en']
        
        try:
            # Шаг 1: Детекция таблицы и ячеек
            logger.info("Шаг 1: Детекция таблицы и ячеек")
            cells = self.table_detector.extract_cells(image_bytes)
            logger.info(f"Обнаружено ячеек: {len(cells)}")
            
            # Шаг 2: OCR для каждой ячейки
            logger.info("Шаг 2: OCR для ячеек")
            lines_data = await self._process_cells(cells, lang)
            
            # Шаг 3: Валидация и исправление ошибок
            logger.info("Шаг 3: Валидация данных")
            invoice_data = {"lines": lines_data}
            result = self.validation_pipeline.validate(invoice_data)
            
            # Шаг 4: Формирование итогового результата
            logger.info("Шаг 4: Подготовка ответа")
            metadata = result.get('metadata', {})
            
            response = {
                "status": "ok",
                "accuracy": metadata.get('accuracy', 0),
                "lines": result.get('lines', []),
                "issues": result.get('issues', []),
                "gpt4o_percent": getattr(self, '_last_gpt4o_percent', 0),
                "gpt4o_count": getattr(self, '_last_gpt4o_count', 0),
                "total_cells": getattr(self, '_last_total_cells', 0)
            }
            
            return response
            
        except Exception as e:
            logger.error(f"Ошибка в OCR-пайплайне: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    async def _process_cells(self, cells: List[Dict[str, Any]], lang: List[str]) -> List[Dict[str, Any]]:
        """
        Обрабатывает ячейки и строит структуру данных для накладной.
        
        В текущей реализации просто берет текст из ячеек (если доступен из PP-Structure).
        В будущем здесь можно добавить вызов PaddleOCR или OpenAI Vision для ячеек с низкой
        уверенностью.
        
        Args:
            cells: Список ячеек с координатами и изображениями
            lang: Список языков для OCR
            
        Returns:
            Список строк накладной
        """
        import numpy as np
        from PIL import Image
        import io
        import asyncio

        gpt4o_count = 0
        total_cells = len(cells)
        cell_results = []

        # Функция для обработки ячейки через GPT-4o
        async def process_cell_with_gpt4o(cell_image_bytes):
            from app.config import get_ocr_client
            import json

            client = get_ocr_client()
            if not client:
                logger.error("GPT-4o OCR unavailable: no OpenAI client")
                return "", 0.0

            # Формируем простой промпт для ячейки
            cell_prompt = "Внимательно посмотри на изображение. Оно содержит текст из одной ячейки таблицы. Просто извлеки и верни этот текст. Не добавляй никаких объяснений."
            
            # Формируем base64 изображение
            b64_image = base64.b64encode(cell_image_bytes).decode("utf-8")
            
            try:
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": "Извлеки только текст, видимый на изображении."},
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": cell_prompt},
                                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_image}", "detail": "high"}}
                            ]
                        }
                    ],
                    max_tokens=100,
                    temperature=0.0
                )
                
                # Получаем только текст из ответа
                extracted_text = response.choices[0].message.content.strip()
                return extracted_text, 1.0
            except Exception as e:
                logger.error(f"Ошибка GPT-4o при обработке ячейки: {e}")
                return "", 0.0

        async def ocr_cell(cell):
            nonlocal gpt4o_count
            image = Image.open(io.BytesIO(cell['image'])).convert("RGB")
            np_img = np.array(image)
            result = self.paddle_ocr.ocr(np_img, cls=True)
            if result and result[0]:
                text, conf = result[0][0][1][0], result[0][0][1][1]
            else:
                text, conf = '', 0.0
            used_gpt = False
            if conf < self.low_conf_threshold:
                try:
                    # Вместо call_openai_ocr используем нашу функцию для ячеек
                    gpt_text, gpt_conf = await process_cell_with_gpt4o(cell['image'])
                    if gpt_text:
                        text = gpt_text
                        conf = gpt_conf
                        used_gpt = True
                except Exception as e:
                    logger.warning(f"Ошибка при обработке ячейки через GPT-4o: {e}")
                    pass
            if used_gpt:
                gpt4o_count += 1
            return {**cell, 'text': text, 'confidence': conf, 'used_gpt4o': used_gpt}

        ocr_results = await asyncio.gather(*(ocr_cell(cell) for cell in cells))
        gpt4o_percent = (gpt4o_count / total_cells) * 100 if total_cells else 0
        logger.info(f"Доля ячеек, отправленных в GPT-4o: {gpt4o_percent:.1f}% ({gpt4o_count}/{total_cells})")

        row_cells = {}
        for cell in ocr_results:
            y1 = cell.get('bbox', [0, 0, 0, 0])[1]
            row_found = False
            for row_y in row_cells.keys():
                if abs(row_y - y1) < 20:
                    row_cells[row_y].append(cell)
                    row_found = True
                    break
            if not row_found:
                row_cells[y1] = [cell]
        sorted_rows = sorted(row_cells.items())
        if len(sorted_rows) > 1:
            sorted_rows = sorted_rows[1:]
        lines = []
        for _, row in sorted_rows:
            row.sort(key=lambda cell: cell.get('bbox', [0, 0, 0, 0])[0])
            name = row[0].get('text', '') if len(row) > 0 else ''
            qty_text = row[1].get('text', '') if len(row) > 1 else '0'
            unit = row[2].get('text', '') if len(row) > 2 else 'pcs'
            price_text = row[3].get('text', '') if len(row) > 3 else '0'
            amount_text = row[4].get('text', '') if len(row) > 4 else '0'
            try:
                qty = float(qty_text.replace(',', '.').replace(' ', ''))
            except ValueError:
                qty = 0
            try:
                price = int(price_text.replace('.', '').replace(',', '').replace(' ', ''))
            except ValueError:
                price = 0
            try:
                amount = int(amount_text.replace('.', '').replace(',', '').replace(' ', ''))
            except ValueError:
                amount = 0
            line = {
                'name': name.strip(),
                'qty': qty,
                'unit': unit.strip().lower(),
                'price': price,
                'amount': amount,
                'cells': [
                    {
                        'text': c.get('text', ''),
                        'confidence': c.get('confidence', 0),
                        'used_gpt4o': c.get('used_gpt4o', False)
                    } for c in row
                ]
            }
            lines.append(line)
        # Сохраняем статистику для вывода в response
        self._last_gpt4o_percent = gpt4o_percent
        self._last_gpt4o_count = gpt4o_count
        self._last_total_cells = total_cells
        return lines 