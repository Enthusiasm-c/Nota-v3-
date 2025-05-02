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

PROMPT = Path("prompts/invoice_ocr_en_v0.3.txt").read_text(encoding="utf-8")

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
                {"type": "image_url",
                 "image_url": {"url": f"data:image/jpeg;base64,{base64.b64encode(image_bytes).decode()}"}}
            ]
        }]
    )
    raw = rsp.choices[0].message.content.strip()
    logging.debug(f"[{req_id}] RAW → {raw[:1000]}")
    clean = _strip_code_fence(raw)
    logging.debug(f"[{req_id}] CLEAN → {clean[:400]}")
    def _sanitize_json(obj):
        if isinstance(obj, dict):
            if "positions" in obj:
                if "supplier" not in obj:
                    obj["supplier"] = None
                if "date" not in obj:
                    obj["date"] = None
                return obj
            return {"supplier": None, "date": None, "positions": [obj]}
        if isinstance(obj, list):
            return {"supplier": None, "date": None, "positions": obj}
        return {"supplier": None, "date": None, "positions": []}

    try:
        data = json.loads(clean)
        data = _sanitize_json(data)
        logging.debug(f"[{req_id}] DICT →\n{pprint.pformat(data, width=88)}")
        # normalise numbers
        for p in data.get("positions", []):
            p["price"] = _clean_num(p.get("price"))
        if "total" in data:
            data["total"] = _clean_num(data["total"])
        return ParsedData.model_validate(data)
    except Exception as e:
        logging.error(f"[{req_id}] VALIDATION ERR", exc_info=True)
        raise RuntimeError(f"⚠️ OCR failed. Logged as {req_id}. Please retake or forward to dev.") from e
