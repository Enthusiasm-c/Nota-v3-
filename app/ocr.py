import os
from datetime import date
from app.models import ParsedData, Position

async def call_openai_ocr(image_bytes: bytes) -> dict:
    # If USE_OPENAI_OCR=1 and keys exist, call real OCR (stub for now)
    if os.getenv("USE_OPENAI_OCR") == "1":
        # TODO: real OpenAI Vision logic
        raise NotImplementedError("Real OpenAI OCR not implemented.")
    # Otherwise, always return stub ParsedData with Tuna loin
    return ParsedData(
        supplier="Test Supplier",
        date=date.today(),
        positions=[Position(name="Tuna loin", qty=1, unit="kg")]
    ).model_dump()
