import base64
import time
import json
import logging
from pathlib import Path
from app.models import ParsedData
from app.config import settings, get_ocr_client
from app.ocr_prompt import build_prompt

import types

try:
    import openai
except ImportError:
    openai: types.ModuleType | None = None

from app.utils.api_decorators import with_retry_backoff

PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "invoice_ocr_en_v0.5.txt"
PROMPT = (
    PROMPT_PATH.read_text(encoding="utf-8")
    + "\nReturn qty_value and unit separately; unit must be one of "
    "[kg, g, l, ml, pcs, pack]. If unclear → null. "
    "Add price_per_unit and total_price for each position and for the invoice."
)

# OpenAI function-calling schema for invoice parsing
tool_schema = {
    "type": "function",
    "function": {
        "name": "parse_invoice",
        "description": (
            "Extract structured data from an Indonesian supplier invoice photo"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "supplier": {"type": ["string", "null"]},
                "date": {
                    "type": ["string", "null"],
                    "description": "YYYY-MM-DD",
                },
                "positions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["name", "qty", "unit"],
                        "properties": {
                            "name": {"type": "string"},
                            "qty": {"type": "number"},
                            "unit": {
                                "type": "string",
                                "enum": [
                                    "kg",
                                    "g",
                                    "l",
                                    "ml",
                                    "pcs",
                                    "pack"
                                ],
                            },
                            "price": {"type": "number", "nullable": True},
                            "price_per_unit": {"type": "number", "nullable": True},
                            "total_price": {"type": "number", "nullable": True},
                            "status": {"type": "string", "nullable": True},
                        },
                    },
                },
                "price": {"type": ["number", "null"]},
                "price_per_unit": {"type": ["number", "null"]},
                "total_price": {"type": ["number", "null"]},
            },
            "required": ["supplier", "date", "positions"],
        },
    },
}

import re


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


@with_retry_backoff(max_retries=2, initial_backoff=1.0, backoff_factor=2.0)
def call_openai_ocr(image_bytes: bytes) -> ParsedData:
    """
    Отправляет изображение в OpenAI Vision API для распознавания инвойса.
    Использует декоратор with_retry_backoff для автоматической обработки ошибок
    и повторных попыток.

    Args:
        image_bytes: Байты изображения для обработки

    Returns:
        ParsedData: Структурированные данные инвойса

    Raises:
        RuntimeError: При ошибках API или парсинга данных с дружественными сообщениями
    """
    # Use global client from config instead of creating a new one each time
    client = get_ocr_client()
    if not client:
        logging.error("OCR unavailable: no OpenAI OCR client")
        raise RuntimeError(
            "OCR unavailable: Please check your OPENAI_OCR_KEY"
        )

    t0 = time.time()
    # req_id берется из контекста декоратора
    prompt_prefix = build_prompt()

    # Подготовка base64 изображения - вынесено из цикла для эффективности
    base64_image = base64.b64encode(image_bytes).decode()
    image_url = f"data:image/jpeg;base64,{base64_image}"

    # Set longer timeout and increase max_tokens
    logging.info(f"[OCR] Используется модель для Vision: gpt-4o")
    rsp = client.chat.completions.create(
        model="gpt-4o",
        temperature=0,
        max_tokens=1200,  # Increased max tokens
        timeout=45,  # Increased timeout for larger invoices
        messages=[
            {"role": "system", "content": prompt_prefix},
            {
                "role": "user",
                "content": [{"type": "image_url", "image_url": {"url": image_url}}],
            },
        ],
        tools=[tool_schema],
        tool_choice={"type": "function", "function": {"name": "parse_invoice"}},
    )
    message = rsp.choices[0].message
    data = _sanitize_response(message)

    # Обработка числовых данных
    for p in data.get("positions", []):
        p["price"] = _clean_num(p.get("price"))
        p["price_per_unit"] = _clean_num(p.get("price_per_unit"))
        p["total_price"] = _clean_num(p.get("total_price"))
        # Если price отсутствует, но есть total_price и qty > 0, вычислить price
        if (p.get("price") is None or p.get("price") == 0) and p.get("total_price") and p.get("qty"):
            try:
                qty = float(p["qty"])
                if qty > 0:
                    p["price"] = float(p["total_price"]) / qty
            except Exception as e:
                logging.warning(f"Failed to auto-calc price: {e} for position {p}")
    data["price"] = _clean_num(data.get("price"))
    data["price_per_unit"] = _clean_num(data.get("price_per_unit"))
    data["total_price"] = _clean_num(data.get("total_price"))

    # OWN_COMPANY_ALIASES check
    supplier = data.get("supplier")
    if supplier and supplier.strip() in settings.OWN_COMPANY_ALIASES:
        data["supplier"] = None
        data["supplier_status"] = "unknown"

    # Валидация модели и возврат результата
    try:
        parsed_data = ParsedData.model_validate(data)
        elapsed = time.time() - t0
        logging.info(
            (
                f"OCR successful after {elapsed:.1f}s with "
                f"{len(parsed_data.positions)} positions"
            )
        )
        return parsed_data
    except Exception as validation_err:
        # Детальное логирование ошибок валидации
        logging.error(f"Model validation error: {validation_err}")
        raise RuntimeError(
            (
                "⚠️ Could not process the invoice data: "
                f"{str(validation_err)}"
            )
        ) from validation_err
