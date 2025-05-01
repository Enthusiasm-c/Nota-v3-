import httpx
from app.config import settings

async def call_openai_ocr(image_bytes: bytes) -> dict:
    # Placeholder for OpenAI Vision API call
    # Should return dict with parsed_data
    # Example: {"supplier": ..., "date": ..., "positions": [...]}
    raise NotImplementedError("OpenAI Vision OCR not implemented.")
