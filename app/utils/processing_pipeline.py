"""
Асинхронный пайплайн обработки изображений накладных.

Этот модуль предоставляет асинхронные функции для обработки и анализа 
фотографий накладных, включая OCR, предобработку и валидацию.
"""

import logging
import asyncio
import time
from typing import Tuple, Any
import app.ocr as ocr  # Импортируем весь модуль ocr вместо отдельной функции

logger = logging.getLogger(__name__)

async def process_image_step(step_func, *args, **kwargs):
    """
    Выполняет один шаг обработки в отдельном потоке с таймаутом.
    """
    return await asyncio.wait_for(
        asyncio.to_thread(step_func, *args, **kwargs),
        timeout=90.0
    )

async def process_invoice_pipeline(
    img_bytes: bytes, 
    tmp_path: str, 
    req_id: str
) -> Tuple[bytes, Any]:
    """
    Асинхронный пайплайн для обработки изображения накладной.
    
    Выполняет следующие этапы:
    1. Предварительная обработка изображения
    2. OCR-распознавание
    3. Валидация результатов
    
    Args:
        img_bytes: Бинарные данные изображения
        tmp_path: Путь к временному файлу
        req_id: Уникальный идентификатор запроса для логирования
        
    Returns:
        Кортеж (обработанные бинарные данные, результат OCR)
    """
    logger.info(f"[{req_id}] Starting invoice processing pipeline")
    pipeline_start = time.time()
    
    # Шаг 1: Предобработка изображения
    # Для простоты используем оригинальные байты изображения
    processed_bytes = img_bytes
    
    # Сохраняем изображение во временный файл
    with open(tmp_path, "wb") as f:
        f.write(processed_bytes)
    
    # Шаг 2: OCR распознавание
    step_start = time.time()
    try:
        # Запускаем OCR в отдельном потоке для асинхронной работы
        # Используем call_openai_ocr вместо process_image, так как это единственная доступная функция
        ocr_result = await asyncio.to_thread(ocr.call_openai_ocr, processed_bytes, req_id)
        ocr_time = time.time() - step_start
        logger.info(f"[{req_id}] OCR processing completed in {ocr_time:.2f} seconds")
        
        # Шаг 3: Базовая валидация результатов OCR
        if not ocr_result or not hasattr(ocr_result, 'positions') or not ocr_result.positions:
            logger.warning(f"[{req_id}] OCR returned empty or invalid result")
            raise ValueError("OCR did not return valid data structure")
            
        positions_count = len(ocr_result.positions)
        logger.info(f"[{req_id}] Found {positions_count} positions in invoice")
        
        # Лог общей информации из OCR
        supplier = getattr(ocr_result, 'supplier', None)
        date = getattr(ocr_result, 'date', None)
        invoice_num = getattr(ocr_result, 'invoice_num', None)
        logger.info(f"[{req_id}] Invoice metadata: supplier='{supplier}', date='{date}', number='{invoice_num}'")
        
    except Exception as e:
        logger.error(f"[{req_id}] OCR processing failed: {str(e)}")
        raise
    
    total_time = time.time() - pipeline_start
    logger.info(f"[{req_id}] Invoice processing pipeline completed in {total_time:.2f} seconds")
    
    return processed_bytes, ocr_result

async def measure_execution_time(func, *args, **kwargs):
    """
    Измеряет время выполнения функции и возвращает результат.
    
    Args:
        func: Измеряемая функция
        *args, **kwargs: Аргументы для функции
        
    Returns:
        Кортеж (результат функции, время выполнения в секундах)
    """
    start_time = time.time()
    result = await func(*args, **kwargs)
    execution_time = time.time() - start_time
    return result, execution_time