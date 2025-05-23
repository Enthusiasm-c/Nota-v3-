import datetime
import sys
from datetime import date
from typing import Optional, Union

from pydantic import BaseModel, field_validator


class Product(BaseModel):
    id: str
    code: str
    name: str
    alias: str
    unit: str
    price_hint: Union[float, None] = None


class Position(BaseModel):
    name: str
    qty: float
    unit: Optional[str] = None
    price: Optional[float] = None
    price_per_unit: Optional[float] = None
    total_price: Optional[float] = None


if sys.version_info >= (3, 10):
    from typing import TypeAlias

    DateOrNone: TypeAlias = Union[date, None]
else:
    pass


class ParsedData(BaseModel):
    supplier: Optional[str] = None
    date: Optional[datetime.date] = None
    positions: list[Position] = []
    price: Optional[float] = None
    price_per_unit: Optional[float] = None
    total_price: Optional[float] = None
    supplier_status: Optional[str] = None  # For marking supplier status

    @field_validator("date", mode="before")
    def parse_iso(cls, v):
        """Конвертирует дату из строки ISO в datetime.date"""
        if not v:
            return None

        if isinstance(v, str):
            try:
                return datetime.date.fromisoformat(v)
            except ValueError as e:
                # More helpful error message with the actual value
                raise ValueError(
                    f"Invalid date format '{v}'. Expected ISO format (YYYY-MM-DD)"
                ) from e
        return v

    @field_validator("positions")
    def validate_positions(cls, v):
        """Проверяет, что в позициях есть хотя бы базовые поля"""
        if not v:
            return []

        # Ensure all positions have at least name, qty and unit
        for i, pos in enumerate(v):
            if not getattr(pos, "name", None) and not isinstance(pos, dict):
                raise ValueError(f"Position {i+1} missing 'name' field")
            if not getattr(pos, "qty", None) and not isinstance(pos, dict):
                raise ValueError(f"Position {i+1} missing 'qty' field")
        return v
