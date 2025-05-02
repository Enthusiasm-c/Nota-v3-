from datetime import date
from typing import Optional
from pydantic import BaseModel


class Position(BaseModel):
    name: str
    qty: float
    unit: str
    price: Optional[float] = None


from pydantic import field_validator

class ParsedData(BaseModel):
    supplier: Optional[str] = None
    date: Optional[date] = None  # Принимает строку или date
    positions: list[Position]

    # Валидатор: преобразует строку в date
    @field_validator("date", mode="before")
    def _parse_date(cls, v):
        if isinstance(v, str):
            return date.fromisoformat(v)
        return v
