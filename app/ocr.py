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
from app.utils.api_decorators import with_async_retry_backoff

VISION_ASSISTANT_TIMEOUT_SECONDS = int(getattr(settings, "VISION_ASSISTANT_TIMEOUT_SECONDS", 30))

@with_async_retry_backoff(max_retries=2, initial_backoff=2.0)
async def call_openai_ocr(image_bytes: bytes) -> ParsedData:
    """
    Отправляет изображение OpenAI Vision Assistant для распознавания инвойса.
    """
    start_time = time.time()
    client = get_ocr_client()
    vision_assistant_id = getattr(settings, "OPENAI_VISION_ASSISTANT_ID", None)
    if not client:
        logging.error("Vision Assistant unavailable: no OpenAI client")
        raise RuntimeError("Vision Assistant unavailable: Please check your OPENAI_API_KEY")
    if not vision_assistant_id:
        logging.error("Vision Assistant unavailable: no Assistant ID configured")
        raise RuntimeError("Vision Assistant unavailable: Please set OPENAI_VISION_ASSISTANT_ID in .env")

    loop = asyncio.get_running_loop()
    tmp_path = Path("/tmp") / f"{uuid4()}.jpg"
    tmp_path.write_bytes(image_bytes)
    logging.debug("Telegram file downloaded: %d bytes", len(image_bytes))
    try:
        # 1. Загрузить файл в Files API (blocking)
        file_obj = await loop.run_in_executor(
            None,
            lambda: client.files.create(file=open(tmp_path, "rb"), purpose="vision")
        )
        file_id = file_obj.id
        logging.debug("OpenAI file_id: %s", file_id)
        # 2. Создать thread
        thread = await loop.run_in_executor(None, lambda: client.beta.threads.create())
        # 3. Сформировать content
        content = [
            {
                "type": "text",
                "text": "Extract items as JSON."
            },
            {
                "type": "image_file",
                "image_file": {"file_id": file_id}
            }
        ]
        logging.debug("Content payload: %s", json.dumps(content, indent=2)[:300])
        # 4. Отправить в Vision-ассистент
        message = await loop.run_in_executor(
            None,
            lambda: client.beta.threads.messages.create(
                thread_id=thread.id,
                role="user",
                content=content
            )
        )
        # 5. Создать запуск ассистента
        run = await loop.run_in_executor(
            None,
            lambda: client.beta.threads.runs.create(
                thread_id=thread.id,
                assistant_id=vision_assistant_id
            )
        )
        timeout = VISION_ASSISTANT_TIMEOUT_SECONDS
        completion_time = time.time() + timeout
        while time.time() < completion_time:
            run_status = await loop.run_in_executor(
                None,
                lambda: client.beta.threads.runs.retrieve(
                    thread_id=thread.id,
                    run_id=run.id
                )
            )
            if getattr(run_status, 'status', None) == 'completed':
                break
            elif getattr(run_status, 'status', None) in ['failed', 'cancelled', 'expired']:
                raise RuntimeError(f"Assistant run failed with status: {run_status.status}")
            await asyncio.sleep(1)
        else:
            await loop.run_in_executor(
                None,
                lambda: client.beta.threads.runs.cancel(
                    thread_id=thread.id,
                    run_id=run.id
                )
            )
            raise RuntimeError(f"Assistant run timed out after {timeout} seconds")
        # 6. Получить результат
        messages = await loop.run_in_executor(
            None,
            lambda: client.beta.threads.messages.list(
                thread_id=thread.id
            )
        )
        if not messages.data:
            raise RuntimeError("No messages returned from Assistant")
        last_message = messages.data[0]
        if getattr(last_message, 'role', None) != "assistant":
            raise RuntimeError("Unexpected message format from Assistant")
        invoice_data = None
        for content_part in getattr(last_message, 'content', []):
            if getattr(content_part, 'type', None) == "text":
                json_match = re.search(r'```(?:json)?\n(.*?)\n```', content_part.text, re.DOTALL)
                if json_match:
                    invoice_data = json_match.group(1)
                    break
        if not invoice_data:
            raise RuntimeError("No invoice data found in Assistant response")
        # Попробовать распарсить JSON и провалидировать результат
        try:
            parsed = json.loads(invoice_data)
        except Exception as e:
            logging.error(f"Failed to parse invoice JSON: {e}")
            logging.error(f"Raw invoice data: {invoice_data}")
            raise RuntimeError(f"Invalid invoice data format: {str(e)}") from e
        try:
            result = ParsedData.model_validate(parsed)
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
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception as e:
            logging.warning(f"Failed to remove temp file {tmp_path}: {e}")

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


