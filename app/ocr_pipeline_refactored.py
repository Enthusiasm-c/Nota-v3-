"""
Полный OCR-пайплайн для обработки накладных.

Включает:
1. Детектор таблиц
2. OCR-обработчик
3. Валидационный пайплайн (арифметический + бизнес-правила)
"""
import json
import logging
import asyncio
import time
from typing import Dict, List, Any, Optional, Tuple, Union
import base64
import openai
import numpy as np
from PIL import Image
import io

from app.detectors.table.factory import get_detector
from app.validators.pipeline import ValidationPipeline
from paddleocr import PaddleOCR
from app.ocr import call_openai_ocr_async
from app.ocr_prompt import OCR_SYSTEM_PROMPT
from app.config import settings, get_ocr_client

logger = logging.getLogger(__name__)

class OCRPipeline:
    """
    Полный OCR-пайплайн для обработки накладных.
    """
    
    def __init__(self, 
               table_detector_method="paddle",
               paddle_ocr_lang="en"):
        """
        Инициализирует OCR-пайплайн.
        
        Args:
            table_detector_method: Метод детекции таблиц ('paddle', etc.)
            paddle_ocr_lang: Язык для PaddleOCR
        """
        self.table_detector = get_detector(method=table_detector_method)
        self.validation_pipeline = ValidationPipeline()
        self.paddle_ocr = PaddleOCR(use_angle_cls=True, lang=paddle_ocr_lang, show_log=False)
        self.low_conf_threshold = 0.7  # Порог уверенности для fallback на GPT-4o
        
        # Initialize statistics variables
        self._last_gpt4o_percent = 0
        self._last_gpt4o_count = 0
        self._last_total_cells = 0
    
    async def process_image(self, image_bytes: bytes, lang: List[str], max_retries: int = 2) -> Dict[str, Any]:
        """
        Обрабатывает изображение, извлекает таблицу и распознает текст.
        
        Args:
            image_bytes: Бинарные данные изображения
            lang: Список языков для OCR
            max_retries: Максимальное количество попыток при ошибках
            
        Returns:
            Структура данных с результатами OCR
        """
        start_time = time.time()
        timing = {}
        
        try:
            # Пытаемся использовать детектор таблиц
            table_detection_start = time.time()
            try:
                table_detector = get_detector("paddle")
                cells = table_detector.extract_cells(image_bytes)
                timing['table_detection'] = time.time() - table_detection_start
                
                # Обрабатываем ячейки
                processing_start = time.time()
                lines = await self._process_cells(cells, lang)
                timing['cell_processing'] = time.time() - processing_start
                
                # Собираем результат
                result = {
                    'status': 'success',
                    'lines': lines,
                    'accuracy': 0.8,  # Оценка точности по умолчанию
                    'issues': [],
                    'timing': timing
                }
                
            except Exception as e:
                # Ошибка детектора таблиц - используем резервный метод (OpenAI Vision)
                logger.warning(f"Ошибка при использовании детектора таблиц: {str(e)}, переключаемся на OpenAI Vision")
                
                # Сбрасываем таймеры и фиксируем ошибку
                timing['table_detection_error'] = time.time() - table_detection_start
                timing['table_detection_error_message'] = str(e)
                
                # Используем OpenAI Vision для всего изображения
                vision_start = time.time()
                result = await self._process_with_openai_vision(image_bytes, lang)
                timing['vision_processing'] = time.time() - vision_start
                result['timing'] = timing
                result['used_fallback'] = True
                
            # Применяем валидацию
            if result["status"] == "success":
                validation_start = time.time()
                validation_pipeline = ValidationPipeline()
                validated_result = validation_pipeline.validate(result)
                timing['validation'] = time.time() - validation_start
                validated_result['timing'] = timing
                validated_result['total_time'] = time.time() - start_time
                return validated_result
            else:
                result['total_time'] = time.time() - start_time
                return result
                
        except Exception as e:
            # Крайний случай - общая ошибка
            logger.error(f"Критическая ошибка в OCR-пайплайне: {str(e)}", exc_info=True)
            return {
                'status': 'error',
                'message': f"Ошибка обработки: {str(e)}",
                'timing': timing,
                'total_time': time.time() - start_time
            }
    
    @staticmethod
    def parse_numeric_value(text: Optional[str], default: Union[int, float] = 0, is_float: bool = False) -> Union[int, float]:
        """
        Функция для безопасного преобразования текста в число.
        
        Args:
            text: Текст для преобразования в число
            default: Значение по умолчанию, если преобразование не удалось
            is_float: Флаг, указывающий, что нужно преобразовать в float (иначе в int)
            
        Returns:
            Преобразованное число или значение по умолчанию
        """
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
            
    async def process_cell_with_gpt4o(self, cell_image_bytes: bytes) -> Tuple[str, float]:
        """
        Функция для обработки ячейки через GPT-4o.
        
        Args:
            cell_image_bytes: Бинарные данные изображения ячейки
            
        Returns:
            Кортеж (текст, уверенность)
        """
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
                model=settings.OPENAI_MODEL,
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
                max_tokens=1024,
                temperature=0.0
            )
            
            # Получаем только текст из ответа
            extracted_text = response.choices[0].message.content.strip()
            return extracted_text, 1.0
        except Exception as e:
            logger.error(f"Ошибка GPT-4o при обработке ячейки: {e}")
            return "", 0.0
        
    async def _ocr_cell(self, cell: Dict[str, Any], gpt4o_count: int = 0) -> Dict[str, Any]:
        """
        Обрабатывает одну ячейку с помощью OCR, с возможным fallback на GPT-4o.
        
        Args:
            cell: Данные ячейки
            gpt4o_count: Счетчик использования GPT-4o (передается по ссылке)
            
        Returns:
            Обработанные данные ячейки
        """
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
                    # Используем метод класса для обработки ячейки
                    gpt_text, gpt_conf = await self.process_cell_with_gpt4o(cell['image'])
                    if gpt_text:
                        text = gpt_text
                        conf = gpt_conf
                        used_gpt = True
                except Exception as e:
                    logger.warning(f"Ошибка при обработке ячейки через GPT-4o: {e}")
            
            return {**cell, 'text': text, 'confidence': conf, 'used_gpt4o': used_gpt}
            
        except Exception as e:
            logger.error(f"Критическая ошибка при обработке ячейки: {e}")
            return {**cell, 'text': '', 'confidence': 0.0, 'used_gpt4o': False, 'error': str(e)}
        
    def _build_lines_from_cells(self, ocr_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Строит структуру строк из обработанных ячеек.
        
        Args:
            ocr_results: Результаты OCR для ячеек
            
        Returns:
            Список строк с данными
        """
        # Замеряем время построения строк
        lines_build_start = time.time()
        row_cells = {}
        
        # Группируем ячейки по строкам на основе координаты Y
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
                
        # Сортируем строки по вертикальной позиции
        sorted_rows = sorted(row_cells.items())
        if len(sorted_rows) > 1:
            sorted_rows = sorted_rows[1:]  # Пропускаем заголовок
            
        lines = []
        for _, row in sorted_rows:
            # Сортируем ячейки в строке по горизонтальной позиции
            row.sort(key=lambda cell: cell.get('bbox', [0, 0, 0, 0])[0])
            
            # Извлекаем данные из ячеек
            name = row[0].get('text', '') if len(row) > 0 else ''
            qty_text = row[1].get('text', '') if len(row) > 1 else '0'
            unit = row[2].get('text', '') if len(row) > 2 else 'pcs'
            price_text = row[3].get('text', '') if len(row) > 3 else '0'
            amount_text = row[4].get('text', '') if len(row) > 4 else '0'
            
            # Используем безопасное преобразование чисел
            qty = self.parse_numeric_value(qty_text, default=0, is_float=True)
            price = self.parse_numeric_value(price_text, default=0)
            amount = self.parse_numeric_value(amount_text, default=0)
            
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
        
        return lines
    
    async def _process_cells(self, cells: List[Dict[str, Any]], lang: List[str]) -> List[Dict[str, Any]]:
        """
        Обрабатывает ячейки и строит структуру данных для накладной.
        
        Args:
            cells: Список ячеек с координатами и изображениями
            lang: Список языков для OCR
            
        Returns:
            Список строк накладной
        """
        gpt4o_count = 0
        total_cells = len(cells)
        
        # Проверяем, есть ли ячейки для обработки
        if not cells:
            logger.warning("Не обнаружено ячеек для OCR")
            self._last_gpt4o_percent = 0
            self._last_gpt4o_count = 0
            self._last_total_cells = 0
            
            # Если таблицы нет или не удалось извлечь ячейки, возвращаем пустой список
            return []
        
        # Замеряем время OCR для каждой ячейки
        ocr_cells_start = time.time()
        ocr_results = []
        
        try:
            # Параллельно обрабатываем все ячейки
            async def process_with_counter(cell):
                nonlocal gpt4o_count
                result = await self._ocr_cell(cell)
                if result.get('used_gpt4o', False):
                    gpt4o_count += 1
                return result
                
            ocr_results = await asyncio.gather(*(process_with_counter(cell) for cell in cells))
        except Exception as e:
            logger.error(f"Ошибка при выполнении OCR для ячеек: {e}")
            # Если падает на всех ячейках, пробуем хотя бы частично обработать их
            for cell in cells:
                try:
                    result = await self._ocr_cell(cell)
                    if result.get('used_gpt4o', False):
                        gpt4o_count += 1
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
        
        # Строим структуру строк из обработанных ячеек
        lines = self._build_lines_from_cells(ocr_results)
        
        # Сохраняем статистику для вывода в response
        self._last_gpt4o_percent = gpt4o_percent
        self._last_gpt4o_count = gpt4o_count
        self._last_total_cells = total_cells
        
        return lines
        
    async def _process_with_openai_vision(self, image_bytes: bytes, lang: List[str]) -> Dict[str, Any]:
        """
        Резервный метод обработки через OpenAI Vision API.
        Используется, когда PaddleOCR/PPStructure не может обработать изображение.
        
        Args:
            image_bytes: Бинарные данные изображения
            lang: Список языков для OCR
            
        Returns:
            Структура данных с результатами OCR
        """
        try:
            # Используем OpenAI Vision для распознавания таблицы
            vision_result = await call_openai_ocr_async(
                image_bytes=image_bytes, 
                system_prompt=OCR_SYSTEM_PROMPT,
                api_key=settings.OPENAI_API_KEY
            )
            
            # Преобразуем результат в формат строк
            if isinstance(vision_result, str):
                try:
                    parsed = json.loads(vision_result)
                    if isinstance(parsed, dict) and 'lines' in parsed:
                        return {
                            'status': 'success',
                            'lines': parsed.get('lines', []),
                            'accuracy': 0.9,  # Оценка точности для OpenAI Vision
                            'issues': []
                        }
                except json.JSONDecodeError:
                    # Если результат не является JSON, пытаемся обработать текст
                    logger.warning("OpenAI не вернул JSON, пытаемся обработать текст")
            
            # Возвращаем ошибку, если не удалось разобрать результат
            return {
                'status': 'error',
                'message': "Не удалось разобрать результат OpenAI Vision",
                'raw_result': vision_result[:200] + '...' if len(str(vision_result)) > 200 else vision_result
            }
            
        except Exception as e:
            logger.error(f"Ошибка в резервном методе OpenAI Vision: {str(e)}", exc_info=True)
            return {
                'status': 'error',
                'message': f"Ошибка в резервном методе: {str(e)}"
            }


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