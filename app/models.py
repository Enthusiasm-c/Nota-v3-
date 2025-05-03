from datetime import date
from typing import Optional
from pydantic import BaseModel


class Product(BaseModel):
    id: str
    code: str
    name: str
    alias: str
    unit: str
    price_hint: float | None = None

class Position(BaseModel):
    name: str
    qty: float
    unit: str
    price: Optional[float] = None
    price_per_unit: Optional[float] = None
    total_price: Optional[float] = None


from pydantic import field_validator

import sys
if sys.version_info >= (3, 10):
    from typing import TypeAlias
    DateOrNone: TypeAlias = date | None
else:
    from typing import Optional as DateOrNone

import datetime

class ParsedData(BaseModel):
    supplier: Optional[str]
    date: Optional[datetime.date]
    positions: list[Position]
    price: Optional[float] = None
    price_per_unit: Optional[float] = None
    total_price: Optional[float] = None

    @field_validator("date", mode="before")
    def parse_iso(cls, v):
        return datetime.date.fromisoformat(v) if isinstance(v, str) else v
