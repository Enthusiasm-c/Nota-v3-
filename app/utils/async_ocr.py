"""
Асинхронный модуль OCR для обработки изображений.
Предотвращает блокировку основного потока при обработке изображений.
"""
import asyncio
import base64
import json
import logging
import time
from typing import Optional
import aiohttp

from app.models import ParsedData
from app.postprocessing import postprocess_parsed_data
from app.ocr_prompt import OCR_SYSTEM_PROMPT
from app.config import settings
from app.utils.enhanced_ocr_cache import get_from_cache_async, save_to_cache_async
from app.imgprep.prepare import prepare_for_ocr

logger = logging.getLogger(__name__)

# OCR Function Schema
INVOICE_FUNCTION_SCHEMA = {
    "name": "get_parsed_invoice",
    "description": "Parse structured data from invoice image",
    "parameters": {
        "type": "object",
        "properties": {
            "supplier": {
                "type": "string",
                "description": "Supplier name from the invoice"
            },
            "date": {
                "type": "string",
                "description": "Invoice date in YYYY-MM-DD format"
            },
            "positions": {
                "type": "array",
                "description": "List of invoice positions",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Product name"
                        },
                        "qty": {
                            "type": "number",
                            "description": "Quantity"
                        },
                        "unit": {
                            "type": "string",
                            "description": "Unit of measurement"
                        },
                        "price": {
                            "type": "number",
                            "description": "Price per unit"
                        },
                        "total_price": {
                            "type": "number",
                            "description": "Total price for this position"
                        }
                    },
                    "required": ["name", "qty"]
                }
            },
            "total_price": {
                "type": "number",
                "description": "Total invoice amount"
            }
        },
        "required": ["positions"]
    }
}

# Таймаут для сессии HTTP по умолчанию
DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=30)  # 30 секунд общий таймаут

# Асинхронная HTTP сессия
_http_session = None

async def get_http_session() -> aiohttp.ClientSession:
    """
    Получает или создает глобальную HTTP сессию.
    
    Returns:
        Асинхронная HTTP сессия
    """
    global _http_session
    if _http_session is None or _http_session.closed:
        _http_session = aiohttp.ClientSession(timeout=DEFAULT_TIMEOUT)
    return _http_session

async def close_http_session():
    """Закрывает HTTP сессию при завершении работы."""
    global _http_session
    if _http_session is not None and not _http_session.closed:
        await _http_session.close()
        _http_session = None

async def async_ocr(image_bytes: bytes, req_id: Optional[str] = None, 
                   use_cache: bool = True, timeout: int = 60) -> ParsedData:
    """
    Асинхронно выполняет OCR изображения с использованием OpenAI API.
    
    Args:
        image_bytes: Байты изображения
        req_id: ID запроса для логирования
        use_cache: Использовать ли кеш
        timeout: Таймаут в секундах
        
    Returns:
        ParsedData с результатами распознавания
        
    Raises:
        asyncio.TimeoutError: Если распознавание превысило таймаут
        RuntimeError: При ошибке API или обработки
    """
    req_id = req_id or f"ocr_{int(time.time())}"
    start_time = time.time()
    logger.info(f"[{req_id}] Начато асинхронное OCR, таймаут {timeout}с")
    
    # Пробуем получить из кеша
    if use_cache:
        try:
            cached_data = await get_from_cache_async(image_bytes)
            if cached_data:
                logger.info(f"[{req_id}] Использован кешированный OCR результат")
                return cached_data
        except Exception as e:
            logger.warning(f"[{req_id}] Ошибка при чтении из кеша: {e}")
    
    # Подготавливаем изображение
    try:
        # Используем мультипроцессную обработку для оптимизации изображения
        loop = asyncio.get_event_loop() 
        optimized_image = await loop.run_in_executor(None, prepare_for_ocr, image_bytes)
        logger.debug(f"[{req_id}] Изображение оптимизировано для OCR")
    except Exception as e:
        logger.warning(f"[{req_id}] Ошибка оптимизации изображения: {e}, используем оригинал")
        optimized_image = image_bytes
    
    # Превращаем изображение в base64
    base64_image = base64.b64encode(optimized_image).decode("utf-8")
    
    # Формируем параметры запроса к API
    api_url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.OPENAI_OCR_KEY}"
    }
    
    payload = {
        "model": "gpt-4o",
        "max_tokens": 2048,
        "temperature": 0.0,
        "tools": [{
            "type": "function", 
            "function": INVOICE_FUNCTION_SCHEMA
        }],
        "tool_choice": {
            "type": "function", 
            "function": {"name": "get_parsed_invoice"}
        },
        "messages": [
            {"role": "system", "content": OCR_SYSTEM_PROMPT},
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {
                    "url": f"data:image/jpeg;base64,{base64_image}",
                    "detail": "high"
                }}
            ]}
        ]
    }
    
    # Создаем задачу с таймаутом
    try:
        # Используем защищенную сессию с повторными попытками и таймаутом
        session = await get_http_session()
        api_start_time = time.time()
        
        # Создаем сессию с таймаутом для этого конкретного запроса
        request_timeout = aiohttp.ClientTimeout(total=timeout)
        
        # Выполняем запрос с таймаутом
        try:
            async with session.post(api_url, json=payload, headers=headers, timeout=request_timeout) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"[{req_id}] API вернул ошибку: {response.status} {error_text}")
                    raise RuntimeError(f"OCR API вернул ошибку: {response.status}")
                
                # Получаем и обрабатываем ответ
                api_response = await response.json()
                api_duration = time.time() - api_start_time
                logger.info(f"[{req_id}] OCR API вызов выполнен за {api_duration:.2f}с")
        except asyncio.TimeoutError:
            logger.error(f"[{req_id}] OCR API вызов превысил таймаут {timeout}с")
            raise asyncio.TimeoutError(f"OCR операция превысила таймаут {timeout}с")
                
        # Проверяем наличие ответа
        if not api_response.get("choices"):
            raise ValueError("Пустой ответ от OpenAI API")
        
        # Извлекаем результат функции
        message = api_response["choices"][0]["message"]
        if not message.get("tool_calls") or len(message["tool_calls"]) == 0:
            raise ValueError("Ответ не содержит результат функции")
        
        # Получаем первый tool call
        tool_call = message["tool_calls"][0]
        if tool_call["function"]["name"] != "get_parsed_invoice":
            raise ValueError(f"Неожиданное имя функции: {tool_call['function']['name']}")
        
        # Парсим JSON аргументы
        result_data = json.loads(tool_call["function"]["arguments"])
        
        # Конвертируем в Pydantic модель
        parsed_data = ParsedData.model_validate(result_data)
        
        # Постобработка данных
        processed_data = postprocess_parsed_data(parsed_data)
        
        # Кешируем результат
        if use_cache:
            try:
                await save_to_cache_async(image_bytes, processed_data)
                logger.debug(f"[{req_id}] OCR результат сохранен в кеш")
            except Exception as e:
                logger.warning(f"[{req_id}] Ошибка кеширования OCR результата: {e}")
        
        # Логируем общее время обработки
        total_duration = time.time() - start_time
        logger.info(f"[{req_id}] Общее время OCR: {total_duration:.2f}с")
        
        return processed_data
    
    except asyncio.TimeoutError:
        logger.error(f"[{req_id}] OCR превысил таймаут {timeout}с")
        raise asyncio.TimeoutError(f"OCR операция превысила таймаут {timeout}с")
    except Exception as e:
        logger.error(f"[{req_id}] Ошибка OCR: {str(e)}")
        raise RuntimeError(f"Ошибка извлечения данных из изображения: {str(e)}")