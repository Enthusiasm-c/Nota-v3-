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
import time
from typing import Dict, List, Any, Optional, Tuple
import base64
import openai

from app.detectors.table.factory import get_detector
from app.validators.pipeline import ValidationPipeline
from paddleocr import PaddleOCR
from app.ocr import call_openai_ocr
from app.models import ParsedData
from app.postprocessing import postprocess_parsed_data
from app.ocr_prompt import OCR_SYSTEM_PROMPT
from app.config import settings

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
            # Замеряем общее время выполнения
            start_time = time.time()
            
            # Шаг 1: Детекция таблицы и ячеек
            table_start = time.time()
            logger.info("Шаг 1: Детекция таблицы и ячеек")
            cells = self.table_detector.extract_cells(image_bytes)
            table_time = time.time() - table_start
            logger.info(f"[TIMING] Детекция таблицы: {table_time:.2f} сек. Обнаружено ячеек: {len(cells)}")
            
            # Шаг 2: OCR для каждой ячейки
            ocr_start = time.time()
            logger.info("Шаг 2: OCR для ячеек")
            lines_data = await self._process_cells(cells, lang)
            ocr_time = time.time() - ocr_start
            
            # Проверяем тип данных перед валидацией
            if not isinstance(lines_data, list):
                logger.error(f"Некорректный тип данных от OCR: {type(lines_data)}. Ожидался List[Dict]. Содержимое: {lines_data}")
                return {
                    "status": "error",
                    "message": f"Некорректный формат данных OCR: {type(lines_data)}",
                    "timing": {
                        "table_detection": table_time,
                        "ocr": ocr_time,
                        "total": time.time() - start_time
                    }
                }
            
            logger.info(f"[TIMING] OCR: {ocr_time:.2f} сек. Распознано строк: {len(lines_data)}")
            
            # Шаг 3: Валидация и исправление ошибок
            validation_start = time.time()
            logger.info("Шаг 3: Валидация данных")
            invoice_data = {"lines": lines_data}
            result = self.validation_pipeline.validate(invoice_data)
            validation_time = time.time() - validation_start
            logger.info(f"[TIMING] Валидация: {validation_time:.2f} сек")
            
            # Шаг 4: Формирование итогового результата
            logger.info("Шаг 4: Подготовка ответа")
            metadata = result.get('metadata', {})
            
            # Общее время выполнения
            total_time = time.time() - start_time
            logger.info(f"[TIMING] Общее время обработки: {total_time:.2f} сек")
            
            response = {
                "status": "ok",
                "accuracy": metadata.get('accuracy', 0),
                "lines": result.get('lines', []),
                "issues": result.get('issues', []),
                "gpt4o_percent": getattr(self, '_last_gpt4o_percent', 0),
                "gpt4o_count": getattr(self, '_last_gpt4o_count', 0),
                "total_cells": getattr(self, '_last_total_cells', 0),
                "timing": {
                    "table_detection": table_time,
                    "ocr": ocr_time,
                    "validation": validation_time,
                    "total": total_time
                }
            }
            
            return response
            
        except Exception as e:
            logger.error(f"Ошибка в OCR-пайплайне: {e}", exc_info=True)
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
        import time

        gpt4o_count = 0
        total_cells = len(cells)
        cell_results = []

        # Функция для безопасного преобразования текста в число
        def parse_numeric_value(text, default=0, is_float=False):
            if not text or not isinstance(text, str):
                return default
            try:
                # Удалим все нецифровые символы, кроме точки и запятой
                cleaned = text.replace(' ', '').replace(',', '.')
                if is_float:
                    return float(cleaned) if cleaned else default
                else:
                    # Для целых чисел удаляем все десятичные разделители
                    cleaned = cleaned.replace('.', '')
                    return int(cleaned) if cleaned else default
            except (ValueError, TypeError):
                logger.warning(f"Не удалось преобразовать '{text}' в число. Использую значение по умолчанию: {default}")
                return default

        # Функция для обработки ячейки через GPT-4o
        async def process_cell_with_gpt4o(cell_image_bytes):
            from app.config import get_ocr_client
            import json

            client = get_ocr_client()
            if not client:
                logger.error("GPT-4o OCR unavailable: no OpenAI client")
                return "", 0.0
                
            # Проверка наличия атрибута chat у клиента
            if not hasattr(client, 'chat'):
                logger.error("GPT-4o OCR unavailable: OpenAI client does not have chat attribute")
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
            try:
                image = Image.open(io.BytesIO(cell['image'])).convert("RGB")
                np_img = np.array(image)
                
                # Проверяем размер изображения - если слишком мал, не пытаемся распознавать
                if image.width < 10 or image.height < 10:
                    logger.warning(f"Ячейка слишком мала для OCR: {image.width}x{image.height}")
                    return {**cell, 'text': '', 'confidence': 0.0, 'used_gpt4o': False, 'error': 'too_small'}
                
                try:
                    result = self.paddle_ocr.ocr(np_img, cls=True)
                    if result and result[0]:
                        text, conf = result[0][0][1][0], result[0][0][1][1]
                    else:
                        text, conf = '', 0.0
                except Exception as e:
                    logger.warning(f"Ошибка PaddleOCR: {e}")
                    # Если PaddleOCR не работает, сразу идем на GPT4o
                    text, conf = '', 0.0
                
                used_gpt = False
                # Используем GPT-4o, если уверенность низкая или PaddleOCR вернул пустой результат
                if conf < self.low_conf_threshold or not text:
                    try:
                        # Вместо call_openai_ocr используем нашу функцию для ячеек
                        gpt_text, gpt_conf = await process_cell_with_gpt4o(cell['image'])
                        if gpt_text:
                            text = gpt_text
                            conf = gpt_conf
                            used_gpt = True
                    except Exception as e:
                        logger.warning(f"Ошибка при обработке ячейки через GPT-4o: {e}")
                
                if used_gpt:
                    gpt4o_count += 1
                return {**cell, 'text': text, 'confidence': conf, 'used_gpt4o': used_gpt}
                
            except Exception as e:
                logger.error(f"Критическая ошибка при обработке ячейки: {e}")
                return {**cell, 'text': '', 'confidence': 0.0, 'used_gpt4o': False, 'error': str(e)}

        # Замеряем время OCR для каждой ячейки
        ocr_cells_start = time.time()
        ocr_results = []
        
        # Проверяем, есть ли ячейки для обработки
        if not cells:
            logger.warning("Не обнаружено ячеек для OCR")
            self._last_gpt4o_percent = 0
            self._last_gpt4o_count = 0
            self._last_total_cells = 0
            
            # Если таблицы нет или не удалось извлечь ячейки, возвращаем пустой список
            return []
            
        try:
            ocr_results = await asyncio.gather(*(ocr_cell(cell) for cell in cells))
        except Exception as e:
            logger.error(f"Ошибка при выполнении OCR для ячеек: {e}")
            # Если падает на всех ячейках, пробуем хотя бы частично обработать их
            for cell in cells:
                try:
                    result = await ocr_cell(cell)
                    ocr_results.append(result)
                except Exception as cell_e:
                    logger.error(f"Не удалось обработать ячейку: {cell_e}")
                    ocr_results.append({**cell, 'text': '', 'confidence': 0.0, 'error': str(cell_e)})
            
        ocr_cells_time = time.time() - ocr_cells_start
        gpt4o_percent = (gpt4o_count / total_cells) * 100 if total_cells else 0
        
        logger.info(f"[TIMING] OCR для {total_cells} ячеек: {ocr_cells_time:.2f} сек")
        logger.info(f"Доля ячеек, отправленных в GPT-4o: {gpt4o_percent:.1f}% ({gpt4o_count}/{total_cells})")

        # Экстренный случай: если все ячейки пустые, пробуем запустить OCR на всем изображении
        all_empty = all(not cell.get('text') for cell in ocr_results)
        if all_empty and len(ocr_results) > 2:
            logger.warning("Все ячейки не содержат текста. Добавляем предварительно распознанный текст из ячеек.")
            # Если есть HTML-представление, добавляем текст из HTML
            for i, cell in enumerate(ocr_results):
                if 'text' in cell and not cell['text'] and cell.get('structure') and 'text' in cell['structure']:
                    ocr_results[i]['text'] = cell['structure'].get('text', '')
                    logger.info(f"Добавлен текст из HTML для ячейки {i}: {ocr_results[i]['text']}")
                    
        # Замеряем время построения строк
        lines_build_start = time.time()
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
            
            # Используем безопасное преобразование чисел
            qty = parse_numeric_value(qty_text, default=0, is_float=True)
            price = parse_numeric_value(price_text, default=0)
            amount = parse_numeric_value(amount_text, default=0)
            
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
        
        lines_build_time = time.time() - lines_build_start
        logger.info(f"[TIMING] Построение строк: {lines_build_time:.2f} сек. Сформировано строк: {len(lines)}")
        
        # Сохраняем статистику для вывода в response
        self._last_gpt4o_percent = gpt4o_percent
        self._last_gpt4o_count = gpt4o_count
        self._last_total_cells = total_cells
        return lines

def send_to_gpt(text: str, req_id: str) -> dict:
    """
    Send OCR text to OpenAI API for processing.
    
    Args:
        text: Extracted OCR text
        req_id: Request ID for tracking
        
    Returns:
        JSON response from OpenAI API
    """
    logger.info(f"[{req_id}] Sending to GPT: {len(text)} chars")
    
    try:
        response = openai.chat.completions.create(
            model=settings.OPENAI_GPT_MODEL,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": OCR_SYSTEM_PROMPT},
                {"role": "user", "content": text}
            ],
            temperature=0.2,
            seed=777,
        )
        logger.info(f"[{req_id}] Got GPT response, usage: {response.usage}")
        result = json.loads(response.choices[0].message.content)
        return result
    except Exception as e:
        logger.error(f"[{req_id}] Error sending to GPT: {e}")
        raise RuntimeError(f"Error calling OpenAI API: {e}") 