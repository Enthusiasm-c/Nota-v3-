from datetime import date
from typing import Optional, List
from pydantic import BaseModel

class Position(BaseModel):
    name: str
    qty: float
    unit: str
    price: Optional[float] = None

class ParsedData(BaseModel):
    supplier: str
    date: date
    positions: List[Position]
    total: Optional[float] = None
