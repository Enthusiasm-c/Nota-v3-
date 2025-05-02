from datetime import date
from typing import Optional
from pydantic import BaseModel


class Position(BaseModel):
    name: str
    qty: float
    unit: str
    price: Optional[float] = None


class ParsedData(BaseModel):
    supplier: Optional[str] = None
    date: Optional[date] = None
    positions: list[Position]
