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

from app.models import ParsedData
from app.config import settings, get_ocr_client
from app.utils.monitor import increment_counter, ocr_monitor
from app.utils.api_decorators import with_async_retry_backoff, with_retry_backoff, ErrorType
from app.utils.debug_logger import log_ocr_call, log_ocr_performance, ocr_logger, create_memory_monitor

VISION_ASSISTANT_TIMEOUT_SECONDS = int(getattr(settings, "VISION_ASSISTANT_TIMEOUT_SECONDS", 120))

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
    
    # Подготовка base64 изображения
    base64_image = base64.b64encode(image_bytes).decode()
    image_url = f"data:image/jpeg;base64,{base64_image}"
    t_step = log_ocr_performance(t_step, "Base64 encoding", req_id)
    ocr_logger.debug(f"[{req_id}] Изображение закодировано в base64, размер URL: {len(image_url)} символов")
    
    ocr_logger.info(f"[{req_id}] Отправляю запрос к OpenAI API с таймаутом 15 секунд")
    t_step = log_ocr_performance(t_step, "Before API call", req_id)
    try:
        rsp = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            temperature=0,
            max_tokens=1200,
            timeout=15,  # Reduced timeout
            messages=[
                {"role": "system", "content": prompt_prefix},
                {"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": image_url}}
                ]}
            ],
            tools=[tool_schema],
            tool_choice={"type": "function", "function": {"name": "parse_invoice"}}
        )
        t_step = log_ocr_performance(t_step, "API call completed", req_id)
        ocr_logger.info(f"[{req_id}] Получен ответ от OpenAI API")
        message = rsp.choices[0].message
        data = _sanitize_response(message)
        t_step = log_ocr_performance(t_step, "Response sanitized", req_id)
        ocr_logger.debug(f"[{req_id}] Ответ API успешно обработан")
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
    except openai.APITimeoutError:
        elapsed = time.time() - t0
        ocr_logger.error(f"[{req_id}] OpenAI API timeout after {elapsed:.1f}s")
        raise RuntimeError("OCR processing timed out. Please try with a clearer image.")
    except openai.APIError as api_err:
        elapsed = time.time() - t0
        ocr_logger.error(f"[{req_id}] OpenAI API error after {elapsed:.1f}s: {str(api_err)}")
        raise RuntimeError(f"OpenAI API error: {str(api_err)}")

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


