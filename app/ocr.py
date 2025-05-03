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
from app.ocr_prompt import build_prompt

try:
    import openai
except ImportError:
    openai = None

from pathlib import Path
PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "invoice_ocr_en_v0.5.txt"
PROMPT = (
    PROMPT_PATH.read_text(encoding="utf-8")
    + "\nReturn qty_value and unit separately; unit must be one of [kg, g, l, ml, pcs, pack]. If unclear → null. Add price_per_unit and total_price for each position and for the invoice."
)

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
                            "unit": {"type": "string", "enum": ["kg", "g", "l", "ml", "pcs", "pack", None]},
                            "price": {"type": "number", "nullable": True},
                            "price_per_unit": {"type": "number", "nullable": True},
                            "total_price": {"type": "number", "nullable": True},
                            "status": {"type": "string", "nullable": True}
                        }
                    }
                },
                "price": {"type": ["number", "null"]},
                "price_per_unit": {"type": ["number", "null"]},
                "total_price": {"type": ["number", "null"]}
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

from app.config import get_ocr_client

def call_openai_ocr(image_bytes: bytes) -> ParsedData:
    # Always create client with OCR key to ensure correct key usage
    import openai
    client = openai.OpenAI(api_key=settings.OPENAI_OCR_KEY)
    if not client:
        logging.error("OCR unavailable: no OpenAI OCR client")
        raise RuntimeError("OCR unavailable")
    t0 = time.time()
    req_id = uuid.uuid4().hex[:8]
    prompt_prefix = build_prompt()
    logging.info(f"ocr_prompt:\n{prompt_prefix}")
    try:
        rsp = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            temperature=0,
            max_tokens=800,
            timeout=30,
            messages=[
                {"role": "system", "content": prompt_prefix},
                {"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(image_bytes).decode()}}
                ]}
            ],
            tools=[tool_schema],
            tool_choice={"type": "function", "function": {"name": "parse_invoice"}}
        )
        message = rsp.choices[0].message
        data = _sanitize_response(message)
        logging.debug(f"[{req_id}] CLEAN → {json.dumps(data)[:400]}")
        logging.debug(f"[{req_id}] DICT →\n{pprint.pformat(data, width=88)}")
        # normalise numbers
        for p in data.get("positions", []):
            p["price"] = _clean_num(p.get("price"))
            p["price_per_unit"] = _clean_num(p.get("price_per_unit"))
            p["total_price"] = _clean_num(p.get("total_price"))
        data["price"] = _clean_num(data.get("price"))
        data["price_per_unit"] = _clean_num(data.get("price_per_unit"))
        data["total_price"] = _clean_num(data.get("total_price"))
        # OWN_COMPANY_ALIASES check
        supplier = data.get("supplier")
        if supplier and supplier.strip() in settings.OWN_COMPANY_ALIASES:
            data["supplier"] = None
            data["supplier_status"] = "unknown"
        # unit_mismatch check (needs unit_group info, so here just placeholder)
        for p in data.get("positions", []):
            # p["status"] = "unit_mismatch"  # <-- actual logic in matcher.py
            pass
        return ParsedData.model_validate(data)
    except Exception as e:
        logging.error(f"[{req_id}] VALIDATION ERR", exc_info=True)
        raise RuntimeError(f"⚠️ OCR failed. Logged as {req_id}. Please retake or forward to dev.") from e
