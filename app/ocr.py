import asyncio
import base64
import io
import json
import logging
import re
import time
from typing import Any
from pathlib import Path
from uuid import uuid4
import openai

from app.models import ParsedData
from app.config import settings, get_ocr_client
from app.utils.monitor import increment_counter, ocr_monitor
from app.utils.api_decorators import with_async_retry_backoff, with_retry_backoff, ErrorType
from app.utils.debug_logger import log_ocr_call, log_ocr_performance, ocr_logger, create_memory_monitor
from app.ocr_prompt import build_prompt

VISION_ASSISTANT_TIMEOUT_SECONDS = int(getattr(settings, "VISION_ASSISTANT_TIMEOUT_SECONDS", 120))

# Определение схемы инструмента для OpenAI API
tool_schema = {
    "type": "function",
    "function": {
        "name": "parse_invoice",
        "description": "Parse invoice data from the image",
        "parameters": {
            "type": "object",
            "properties": {
                "supplier": {
                    "type": "string",
                    "description": "Supplier name from the invoice"
                },
                "date": {
                    "type": "string",
                    "description": "Invoice date in ISO format (YYYY-MM-DD)"
                },
                "positions": {
                    "type": "array",
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
                        "required": ["name"]
                    },
                    "description": "List of products/positions in the invoice"
                }
            },
            "required": ["positions"]
        }
    }
}

@log_ocr_call
@with_retry_backoff(max_retries=1, initial_backoff=0.5, backoff_factor=2.0)
def call_openai_ocr(image_bytes: bytes, _req_id=None) -> ParsedData:
    """
    Отправляет изображение в OpenAI Vision API для распознавания инвойса.
    Использует декоратор with_retry_backoff для автоматической обработки ошибок и повторных попыток.
    Включает детальное логирование для диагностики проблем производительности.
    
    Args:
        image_bytes: Байты изображения для обработки
        _req_id: Идентификатор запроса для логирования
    Returns:
        ParsedData: Структурированные данные инвойса
    Raises:
        RuntimeError: При ошибках API или парсинга данных с дружественными сообщениями
    """
    client = get_ocr_client()
    if not client:
        logging.error("OCR unavailable: no OpenAI OCR client")
        raise RuntimeError("OCR unavailable: Please check your OPENAI_OCR_KEY")
    
    t0 = time.time()
    req_id = _req_id or f"ocr_{int(t0)}"
    ocr_logger.info(f"[{req_id}] Начинаю OCR-обработку изображения размером {len(image_bytes)} байт")
    
    # Создаем и запускаем поток для мониторинга памяти
    try:
        memory_monitor = create_memory_monitor()(req_id)
        memory_monitor.start()
        ocr_logger.debug(f"[{req_id}] Запущен мониторинг памяти")
    except Exception as mon_err:
        ocr_logger.warning(f"[{req_id}] Не удалось запустить мониторинг памяти: {str(mon_err)}")
    
    t_step = log_ocr_performance(t0, "Initialization", req_id)
    prompt_prefix = build_prompt()
    
    # НОВЫЙ СПОСОБ: Загрузка файла в Files API
    try:
        ocr_logger.info(f"[{req_id}] Загружаю изображение в Files API")
        file_obj = client.files.create(
            file=image_bytes,
            purpose="vision",
            file_name=f"invoice_{req_id}.jpg"
        )
        file_id = file_obj.id
        t_step = log_ocr_performance(t_step, "File upload", req_id)
        ocr_logger.debug(f"[{req_id}] Изображение успешно загружено, file_id: {file_id}")
    except Exception as upload_err:
        ocr_logger.error(f"[{req_id}] Ошибка загрузки файла: {str(upload_err)}")
        raise RuntimeError(f"Ошибка загрузки изображения: {str(upload_err)}")
    
    # Создаем Thread для работы с ассистентом
    try:
        thread = client.beta.threads.create()
        thread_id = thread.id
        t_step = log_ocr_performance(t_step, "Thread creation", req_id)
        ocr_logger.debug(f"[{req_id}] Создан thread: {thread_id}")
        
        # Отправляем сообщение с изображением
        client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=[
                {"type": "text", "text": "Extract invoice data as JSON."},
                {"type": "image_file", "image_file": {"file_id": file_id}}
            ]
        )
        t_step = log_ocr_performance(t_step, "Message creation", req_id)
        ocr_logger.debug(f"[{req_id}] Отправлено сообщение с изображением")
        
        # Запускаем обработку ассистентом
        ocr_logger.info(f"[{req_id}] Запускаю ассистента с таймаутом 15 секунд")
        run = client.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=settings.OPENAI_VISION_ASSISTANT_ID,
            temperature=0,
            response_format={"type": "json_object"}
        )
        
        # Ожидаем завершения обработки с таймаутом
        timeout = 15  # 15 секунд таймаут
        start_wait = time.time()
        while run.status in ("queued", "in_progress"):
            if time.time() - start_wait > timeout:
                ocr_logger.error(f"[{req_id}] Превышен таймаут ожидания ассистента")
                raise RuntimeError("Превышен таймаут ожидания. Пожалуйста, попробуйте еще раз.")
            
            time.sleep(1)
            run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
        
        t_step = log_ocr_performance(t_step, "Assistant processing", req_id)
        ocr_logger.info(f"[{req_id}] Ассистент завершил обработку со статусом: {run.status}")
        
        # Проверяем статус запуска
        if run.status != "completed":
            ocr_logger.error(f"[{req_id}] Ошибка обработки ассистентом: {run.status}")
            raise RuntimeError(f"Ошибка обработки изображения: {run.status}")
        
        # Получаем результат из сообщений
        messages = client.beta.threads.messages.list(thread_id=thread_id)
        for msg in messages.data:
            if msg.role == "assistant":
                content = msg.content[0]
                if content.type == "text":
                    # Извлекаем JSON из текстового ответа
                    try:
                        response_text = content.text.value
                        data = json.loads(response_text)
                        t_step = log_ocr_performance(t_step, "Response parsing", req_id)
                        ocr_logger.debug(f"[{req_id}] Ответ API успешно обработан")
                    except json.JSONDecodeError:
                        raise ValueError(f"Неверный формат JSON в ответе: {response_text[:100]}...")
                    
                    # Постобработка данных
                    for p in data.get("positions", []):
                        p["price"] = _clean_num(p.get("price"))
                        p["price_per_unit"] = _clean_num(p.get("price_per_unit"))
                        p["total_price"] = _clean_num(p.get("total_price"))
                    data["price"] = _clean_num(data.get("price"))
                    data["price_per_unit"] = _clean_num(data.get("price_per_unit"))
                    data["total_price"] = _clean_num(data.get("total_price"))
                    supplier = data.get("supplier")
                    if supplier and supplier.strip() in settings.OWN_COMPANY_ALIASES:
                        data["supplier"] = None
                        data["supplier_status"] = "unknown"
                    
                    try:
                        parsed_data = ParsedData.model_validate(data)
                        elapsed = time.time() - t0
                        logging.info(f"OCR successful after {elapsed:.1f}s with {len(parsed_data.positions)} positions")
                        t_step = log_ocr_performance(t_step, "Validation completed", req_id)
                        ocr_logger.info(f"[{req_id}] OCR успешно завершен за {elapsed:.2f} сек, найдено {len(parsed_data.positions)} позиций")
                        return parsed_data
                    except Exception as validation_err:
                        logging.error(f"Model validation error: {validation_err}")
                        raise RuntimeError(f"⚠️ Could not process the invoice data: {str(validation_err)}") from validation_err
        
        # Если не нашли ответ в сообщениях
        raise ValueError("Не удалось получить ответ от ассистента")
    
    except openai.APITimeoutError:
        elapsed = time.time() - t0
        ocr_logger.error(f"[{req_id}] OpenAI API timeout after {elapsed:.1f}s")
        raise RuntimeError("OCR processing timed out. Please try with a clearer image.")
    except openai.APIError as api_err:
        elapsed = time.time() - t0
        ocr_logger.error(f"[{req_id}] OpenAI API error after {elapsed:.1f}s: {str(api_err)}")
        raise RuntimeError(f"OpenAI API error: {str(api_err)}")
    except Exception as e:
        elapsed = time.time() - t0
        ocr_logger.error(f"[{req_id}] Unexpected error after {elapsed:.1f}s: {str(e)}")
        raise RuntimeError(f"Unexpected error: {str(e)}")

def _clean_num(v):
    if v in (None, "", "null"):
        return None
    return float(
        str(v)
        .lower()
        .replace("rp", "")
        .replace(",", "")
        .replace(".", "")
    )


def _strip_code_fence(text: str) -> str:
    """Remove code fences and leading/trailing whitespace."""
    text = text.strip()
    text = re.sub(r"^```(json)?", "", text, flags=re.IGNORECASE | re.MULTILINE)
    text = re.sub(r"```$", "", text, flags=re.MULTILINE)
    return text.strip()


def _sanitize_response(message):
    """
    Extract and sanitize the OpenAI function call result.

    Args:
        message: OpenAI completion message containing function call

    Returns:
        dict: Cleaned data with properly set defaults

    Raises:
        RuntimeError: If parsing or sanitization fails
    """
    try:
        # Extract the function call arguments
        tool_calls = getattr(message, "tool_calls", None)
        if not tool_calls:
            raise ValueError("Response has no tool_calls")

        # Find the first function call (should be parse_invoice)
        function_call = None
        for call in tool_calls:
            if hasattr(call, "function"):
                function_call = call.function
                break

        if not function_call:
            raise ValueError("No function call found in response")

        # Get the arguments JSON string
        args_json = function_call.arguments
        if not args_json:
            raise ValueError("Function arguments are empty")

        # Parse the JSON data
        try:
            data = json.loads(args_json)
        except json.JSONDecodeError as e:
            # More detailed error with context
            error_context = args_json[:50] + "..." if len(args_json) > 50 else args_json
            raise ValueError(
                f"Invalid JSON in response: {error_context}. Error: {str(e)}"
            )

        # Handle different data shapes and ensure required fields
        if isinstance(data, dict):
            # Ensure required fields with defaults
            data.setdefault("supplier", None)
            data.setdefault("date", None)
            data.setdefault("positions", [])
            data.setdefault("supplier_status", None)
            return data
        elif isinstance(data, list):
            # If API returned just a list of positions
            return {
                "supplier": None,
                "date": None,
                "positions": data,
                "supplier_status": None,
            }
        else:
            # Unexpected data type
            raise ValueError(f"Unexpected data type: {type(data).__name__}")

    except Exception as e:
        # Wrap all errors with context
        raise RuntimeError(f"Sanitization failed: {str(e)}")


