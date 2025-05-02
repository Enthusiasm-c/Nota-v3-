from pydantic import BaseModel
from typing import List

class Position(BaseModel):
    name: str
    qty: int
    unit: str

class ParsedData(BaseModel):
    supplier: str
    date: str
    positions: List[Position]

async def call_openai_ocr(image_bytes: bytes) -> dict:
    # Stub: returns mock ParsedData
    return ParsedData(
        supplier="TESTSUPPLIER",
        date="26-Sep-2023",
        positions=[Position(name="Product A", qty=1, unit="pcs") for _ in range(17)] + [Position(name="Unknown", qty=1, unit="pcs") for _ in range(3)]
    ).model_dump()
