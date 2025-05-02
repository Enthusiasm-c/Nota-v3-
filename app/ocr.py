import os
import base64
import time
import json
import logging
import uuid
import pprint
import re
from pathlib import Path
from app.models import ParsedData, Position
from app.config import settings

try:
    import openai
except ImportError:
    openai = None

from pathlib import Path
PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "invoice_ocr_en_v0.5.txt"
PROMPT = PROMPT_PATH.read_text(encoding="utf-8")

# OpenAI function-calling schema for invoice parsing
tool_schema = {
    "type": "function",
    "function": {
        "name": "parse_invoice",
        "description": "Extract structured data from an Indonesian supplier invoice photo",
        "parameters": {
            "type": "object",
            "properties": {
                "supplier": {"type": ["string", "null"]},
                "date": {"type": ["string", "null"], "description": "YYYY-MM-DD"},
                "positions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["name", "qty", "unit"],
                        "properties": {
                            "name": {"type": "string"},
                            "qty": {"type": "number"},
                            "unit": {"type": "string"},
                            "price": {"type": "number", "nullable": True}
                        }
                    }
                }
            },
            "required": ["supplier", "date", "positions"]
        }
    }
}


def _clean_num(v):
    if v in (None, "", "null"):
        return None
    return float(str(v).lower().replace("rp", "").replace(",", "").replace(".", ""))

def _strip_code_fence(text: str) -> str:
    """Remove code fences and leading/trailing whitespace."""
    text = text.strip()
    text = re.sub(r'^```(json)?', '', text, flags=re.IGNORECASE | re.MULTILINE)
    text = re.sub(r'```$', '', text, flags=re.MULTILINE)
    return text.strip()

def _sanitize_response(message):
    # Extract tool call arguments JSON, ensure required fields, wrap if list
    try:
        tool_calls = getattr(message, "tool_calls", None)
        if not tool_calls or not hasattr(tool_calls[0], "function"):
            raise ValueError("No function call in response")
        args_json = tool_calls[0].function.arguments
        data = json.loads(args_json)
        # If supplier/date missing, set to null
        if isinstance(data, dict):
            if "supplier" not in data:
                data["supplier"] = None
            if "date" not in data:
                data["date"] = None
            if "positions" not in data:
                data["positions"] = []
            return data
        elif isinstance(data, list):
            return {"supplier": None, "date": None, "positions": data}
        else:
            return {"supplier": None, "date": None, "positions": []}
    except Exception as e:
        raise RuntimeError(f"Sanitization failed: {e}")

def call_openai_ocr(image_bytes: bytes) -> ParsedData:
    if not getattr(settings, "OPENAI_API_KEY", None):
        raise RuntimeError("No OCR available (OPENAI_API_KEY missing)")
    if openai is None:
        logging.warning("openai package not installed")
    t0 = time.time()
    client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
    req_id = uuid.uuid4().hex[:8]
    rsp = client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        temperature=0,
        max_tokens=800,
        timeout=30,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": PROMPT},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64.b64encode(image_bytes).decode()}"}}
            ]
        }],
        tools=[tool_schema],
        tool_choice={"name": "parse_invoice"}
    )
    message = rsp.choices[0].message
    raw = str(message)[:1000]
    logging.debug(f"[{req_id}] RAW → {raw}")
    try:
        data = _sanitize_response(message)
        logging.debug(f"[{req_id}] CLEAN → {json.dumps(data)[:400]}")
        logging.debug(f"[{req_id}] DICT →\n{pprint.pformat(data, width=88)}")
        # normalise numbers
        for p in data.get("positions", []):
            p["price"] = _clean_num(p.get("price"))
        return ParsedData.model_validate(data)
    except Exception as e:
        logging.error(f"[{req_id}] VALIDATION ERR", exc_info=True)
        raise RuntimeError(f"⚠️ OCR failed. Logged as {req_id}. Please retake or forward to dev.") from e
