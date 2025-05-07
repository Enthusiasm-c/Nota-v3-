import asyncio
import base64
import json
import logging
import re
import time
from typing import Any

from app.models import ParsedData
from app.config import settings, get_ocr_client
from app.utils.monitor import increment_counter, ocr_monitor
from app.utils.api_decorators import with_retry_backoff

VISION_ASSISTANT_TIMEOUT_SECONDS = int(getattr(settings, "VISION_ASSISTANT_TIMEOUT_SECONDS", 30))

@with_retry_backoff(max_retries=2, initial_backoff=2.0)
async def call_openai_ocr(image_bytes: bytes) -> ParsedData:
    """
    Отправляет изображение OpenAI Vision Assistant для распознавания инвойса.
    Возвращает ParsedData или кидает RuntimeError при ошибке.
    """
    client = get_ocr_client()
    if not client:
        logging.error("Vision Assistant unavailable: no OpenAI client")
        raise RuntimeError("Vision Assistant unavailable: Please check your OPENAI_API_KEY")
    vision_assistant_id = getattr(settings, "OPENAI_VISION_ASSISTANT_ID", None)
    if not vision_assistant_id:
        logging.error("Vision Assistant unavailable: no Assistant ID configured")
        raise RuntimeError("Vision Assistant unavailable: Please set OPENAI_VISION_ASSISTANT_ID in .env")

    base64_image = base64.b64encode(image_bytes).decode('utf-8')
    start_time = time.time()
    try:
        # Используем run_in_executor для синхронных методов OpenAI API
        loop = asyncio.get_running_loop()
        # Создаем поток синхронно
        thread = await loop.run_in_executor(None, lambda: client.beta.threads.create())
        
        # Создаем сообщение синхронно
        message_params = {
            "thread_id": thread.id,
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "Распознай этот инвойс и верни структурированные данные в JSON формате. Используй формат, где есть поля supplier, date, positions с товарами (name, qty, unit, price), и total_price."
                },
                {
                    "type": "image",
                    "image": {
                        "data": base64_image
                    }
                }
            ]
        }
        await loop.run_in_executor(
            None,
            lambda: client.beta.threads.messages.create(**message_params)
        )
        
        # Создаем запуск синхронно
        run_params = {
            "thread_id": thread.id,
            "assistant_id": vision_assistant_id
        }
        run = await loop.run_in_executor(
            None,
            lambda: client.beta.threads.runs.create(**run_params)
        )
        timeout = VISION_ASSISTANT_TIMEOUT_SECONDS
        completion_time = time.time() + timeout
        while time.time() < completion_time:
            # Получаем статус запуска синхронно
            retrieve_params = {
                "thread_id": thread.id,
                "run_id": run.id
            }
            run_status = await loop.run_in_executor(
                None,
                lambda: client.beta.threads.runs.retrieve(**retrieve_params)
            )
            if run_status.status == 'completed':
                break
            elif run_status.status in ['failed', 'cancelled', 'expired']:
                raise RuntimeError(f"Assistant run failed with status: {run_status.status}")
            await asyncio.sleep(1)
        else:
            # Отменяем запуск синхронно
            cancel_params = {
                "thread_id": thread.id,
                "run_id": run.id
            }
            await loop.run_in_executor(
                None,
                lambda: client.beta.threads.runs.cancel(**cancel_params)
            )
            raise RuntimeError(f"Assistant run timed out after {timeout} seconds")
        
        # Получаем список сообщений синхронно
        list_params = {
            "thread_id": thread.id
        }
        messages = await loop.run_in_executor(
            None,
            lambda: client.beta.threads.messages.list(**list_params)
        )
        if not messages.data:
            raise RuntimeError("No messages returned from Assistant")
        last_message = messages.data[0]
        if last_message.role != "assistant":
            raise RuntimeError("Unexpected message format from Assistant")
        invoice_data = None
        for content_part in last_message.content:
            if content_part.type == "text":
                json_match = re.search(r'```(?:json)?\n(.*?)\n```', content_part.text, re.DOTALL)
                if json_match:
                    invoice_json = json_match.group(1)
                    try:
                        invoice_data = json.loads(invoice_json)
                        break
                    except json.JSONDecodeError:
                        logging.warning("Failed to parse JSON from markdown block, trying full message text")
                try:
                    invoice_data = json.loads(content_part.text)
                    break
                except json.JSONDecodeError:
                    continue
        if not invoice_data:
            raise RuntimeError("No valid JSON data found in Assistant response")
        try:
            result = ParsedData.model_validate(invoice_data)
        except Exception as e:
            logging.error(f"Failed to validate invoice data: {str(e)}")
            logging.error(f"Raw invoice data: {invoice_data}")
            raise RuntimeError(f"Invalid invoice data format: {str(e)}") from e
        elapsed = time.time() - start_time
        logging.info(f"Vision Assistant OCR successful after {elapsed:.1f}s")
        increment_counter("nota_ocr_requests_total", {"status": "ok"})
        ocr_monitor.record(int(elapsed * 1000), 0)
        if elapsed > 6.0:
            logging.warning(f"High Vision Assistant OCR latency detected: {elapsed:.1f}s > 6.0s threshold")
        return result
    except Exception as e:
        elapsed = time.time() - start_time
        logging.error(f"Vision Assistant API error after {elapsed:.1f}s: {str(e)}")
        increment_counter("nota_ocr_requests_total", {"status": "error"})
        raise RuntimeError(f"Vision OCR failed: {str(e)}") from e
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


