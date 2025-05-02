import os
import base64
import time
import json
import logging
from pathlib import Path
from app.models import ParsedData, Position
from app.config import settings

try:
    import openai
except ImportError:
    openai = None

PROMPT = Path("prompts/invoice_ocr_en_v0.3.txt").read_text(encoding="utf-8")

def _clean_num(v):
    if v in (None, "", "null"): return None
    return float(str(v).lower().replace("rp", "").replace(",", "").replace(".", ""))

def _stub_invoice():
    from datetime import date
    return ParsedData(
        supplier="Test Supplier",
        date=date.today(),
        positions=[Position(name="Tuna loin", qty=1, unit="kg")],
        total=None
    )

def call_openai_ocr(image_bytes: bytes) -> ParsedData:
    if not getattr(settings, "USE_OPENAI_OCR", False):
        return _stub_invoice()
    if not getattr(settings, "OPENAI_API_KEY", None):
        return _stub_invoice()
    if openai is None:
        logging.warning("openai package not installed, falling back to stub")
        return _stub_invoice()
    t0 = time.time()
    try:
        client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
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
        from app.ocr_cleaner import clean_ocr_response
        raw_json = rsp.choices[0].message.content.strip()
        logging.info("OCR %.1fs %dB", time.time()-t0, len(image_bytes))
        parsed = clean_ocr_response(raw_json)
        # normalise numbers
        for p in parsed.get("positions", []):
            p["price"] = _clean_num(p.get("price"))
        if "total" in parsed:
            parsed["total"] = _clean_num(parsed["total"])
        return ParsedData.model_validate(parsed)
    except Exception as e:
        import traceback
        logging.error("OCR failed: %s", traceback.format_exc())
        raise RuntimeError("⚠️ OCR failed, please retake the photo") from e
