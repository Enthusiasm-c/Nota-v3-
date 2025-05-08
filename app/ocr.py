import asyncio
import base64
import io
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Union
from pathlib import Path
from uuid import uuid4
import openai
from io import BytesIO

from app.models import ParsedData
from app.config import settings, get_ocr_client
from app.utils.monitor import increment_counter, ocr_monitor
from app.utils.api_decorators import with_async_retry_backoff, with_retry_backoff, ErrorType
from app.utils.debug_logger import log_ocr_call, log_ocr_performance, ocr_logger, create_memory_monitor
from app.ocr_prompt import build_prompt
from app.postprocessing import postprocess_parsed_data, clean_num
from app.utils.enhanced_logger import log_indonesian_invoice, log_format_issues, PerformanceTimer

# --- Удалено: tool_schema, VISION_ASSISTANT_TIMEOUT_SECONDS ---

# --- Добавляю импорт оптимизации изображений ---
try:
    from app.imgprep import prepare_for_ocr
    IMG_PREP_AVAILABLE = True
except ImportError:
    IMG_PREP_AVAILABLE = False

# Схема для функции получения данных инвойса
INVOICE_FUNCTION_SCHEMA = {
    "name": "get_parsed_invoice",
    "description": "Извлекает структурированные данные из накладной, включая список товаров, поставщика, дату и суммы",
    "parameters": {
        "type": "object",
        "properties": {
            "supplier": {
                "type": "string", 
                "description": "Название поставщика из накладной или null",
                "nullable": True
            },
            "date": {
                "type": "string",
                "description": "Дата накладной в формате YYYY-MM-DD",
                "nullable": True
            },
            "positions": {
                "type": "array",
                "description": "Список позиций (товаров) в накладной",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Название товара (СТРОГО из списка разрешенных в промпте)"
                        },
                        "qty": {
                            "type": "number",
                            "description": "Количество товара (может быть дробным)"
                        },
                        "unit": {
                            "type": "string",
                            "description": "Единица измерения (кг, гр, л, мл, шт, упак)",
                            "nullable": True
                        },
                        "price": {
                            "type": "number",
                            "description": "Цена за единицу товара (целое число)",
                            "nullable": True
                        },
                        "total_price": {
                            "type": "number",
                            "description": "Общая стоимость позиции (цена * количество)",
                            "nullable": True
                        }
                    },
                    "required": ["name", "qty"]
                }
            },
            "total_price": {
                "type": "number",
                "description": "Общая сумма накладной",
                "nullable": True
            }
        },
        "required": ["positions"]
    }
}

@log_ocr_call
@with_retry_backoff(max_retries=1, initial_backoff=0.5, backoff_factor=2.0)
def call_openai_ocr(image_bytes: bytes, _req_id=None) -> ParsedData:
    """
    Прямой вызов OpenAI Vision API (gpt-4o) для распознавания инвойса с использованием function calling.
    Args:
        image_bytes: Байты изображения для обработки
        _req_id: Идентификатор запроса для логирования
    Returns:
        ParsedData: Структурированные данные инвойса
    Raises:
        RuntimeError: При ошибках API или парсинга данных
    """
    client = get_ocr_client()
    if not client:
        logging.error("OCR unavailable: no OpenAI OCR client")
        raise RuntimeError("OCR unavailable: Please check your OPENAI_OCR_KEY")

    t0 = time.time()
    req_id = _req_id or f"ocr_{int(t0)}"
    ocr_logger.info(f"[{req_id}] Начинаю OCR-обработку изображения размером {len(image_bytes)} байт (Vision API)")

    # Мониторинг памяти
    try:
        memory_monitor = create_memory_monitor()(req_id)
        memory_monitor.start()
        ocr_logger.debug(f"[{req_id}] Запущен мониторинг памяти")
    except Exception as mon_err:
        ocr_logger.warning(f"[{req_id}] Не удалось запустить мониторинг памяти: {str(mon_err)}")

    t_step = log_ocr_performance(t0, "Initialization", req_id)
    prompt = build_prompt()

    # --- Автоматическая оптимизация изображения ---
    if IMG_PREP_AVAILABLE:
        try:
            # Сохраняем изображение во временный файл
            tmp_path = f"/tmp/nota_ocr_{req_id}.jpg"
            with open(tmp_path, "wb") as f:
                f.write(image_bytes)
            image_bytes = prepare_for_ocr(tmp_path, use_preprocessing=True)
            ocr_logger.info(f"[{req_id}] Изображение оптимизировано для Vision API, размер: {len(image_bytes)} байт")
        except Exception as prep_err:
            ocr_logger.warning(f"[{req_id}] Ошибка оптимизации изображения: {prep_err}. Использую оригинал.")

    # Формируем base64 изображение
    b64_image = base64.b64encode(image_bytes).decode("utf-8")
    messages = [
        {"role": "system", "content": prompt},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Распознай накладную и верни структурированные данные используя функцию get_parsed_invoice. Не придумывай лишних позиций."},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_image}", "detail": "high"}}
            ]
        }
    ]

    try:
        ocr_logger.info(f"[{req_id}] Отправляю запрос в gpt-4o с использованием function calling")
        with PerformanceTimer(req_id, "openai_vision_api_call"):
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                max_tokens=2048,
                temperature=0.0,
                tools=[{"type": "function", "function": INVOICE_FUNCTION_SCHEMA}],
                tool_choice={"type": "function", "function": {"name": "get_parsed_invoice"}},
                timeout=90
            )
        t_step = log_ocr_performance(t_step, "Vision API call", req_id)
        ocr_logger.info(f"[{req_id}] Получен ответ от Vision API")
        # Логируем полный ответ Vision API
        try:
            import json as _json
            ocr_logger.debug(f"[{req_id}] RAW Vision API response: {_json.dumps(response.model_dump() if hasattr(response, 'model_dump') else str(response), ensure_ascii=False)[:2000]}")
        except Exception as log_raw_err:
            ocr_logger.warning(f"[{req_id}] Не удалось залогировать сырой ответ Vision API: {log_raw_err}")

        # Извлекаем данные из ответа с function calling
        function_call = response.choices[0].message.tool_calls[0]
        if function_call.function.name != "get_parsed_invoice":
            raise RuntimeError(f"Неожиданное имя функции в ответе: {function_call.function.name}")
        
        # Извлекаем аргументы функции (JSON с данными инвойса)
        try:
            data = json.loads(function_call.function.arguments)
            ocr_logger.debug(f"[{req_id}] Получены структурированные данные через function calling")
            # Логируем результат для индонезийских накладных
            log_indonesian_invoice(req_id, data, phase="ocr_result")
        except Exception as e:
            raise RuntimeError(f"Не удалось распарсить JSON из аргументов функции: {e}")

        # Постобработка данных
        for p in data.get("positions", []):
            p["price"] = clean_num(p.get("price"))
            p["price_per_unit"] = clean_num(p.get("price_per_unit"))
            p["total_price"] = clean_num(p.get("total_price"))
        data["price"] = clean_num(data.get("price"))
        data["price_per_unit"] = clean_num(data.get("price_per_unit"))
        data["total_price"] = clean_num(data.get("total_price"))
        supplier = data.get("supplier")
        if supplier and supplier.strip() in settings.OWN_COMPANY_ALIASES:
            data["supplier"] = None
            data["supplier_status"] = "unknown"

        try:
            parsed_data = ParsedData.model_validate(data)
            parsed_data = postprocess_parsed_data(parsed_data)
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
    except Exception as e:
        elapsed = time.time() - t0
        ocr_logger.error(f"[{req_id}] Unexpected error after {elapsed:.1f}s: {str(e)}")
        raise RuntimeError(f"Unexpected error: {str(e)}")

def _strip_code_fence(text: str) -> str:
    """Remove code fences and leading/trailing whitespace."""
    text = text.strip()
    text = re.sub(r"^```(json)?", "", text, flags=re.IGNORECASE | re.MULTILINE)
    text = re.sub(r"```$", "", text, flags=re.MULTILINE)
    return text.strip()


