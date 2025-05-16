from datetime import date
from typing import Optional, Union, List
from pydantic import BaseModel, Field


class Product(BaseModel):
    id: str
    code: str
    name: str
    alias: str
    unit: str
    price_hint: Union[float, None] = None


class Position(BaseModel):
    """Модель для представления позиции в накладной."""
    name: str
    qty: Optional[float] = None
    unit: Optional[str] = None
    price: Optional[float] = None
    price_per_unit: Optional[float] = None
    total_price: Optional[float] = None
    calculated_price: Optional[float] = None
    price_mismatch: bool = False
    mismatch_type: Optional[str] = None
    expected_total: Optional[float] = None
    status: Optional[str] = "ok"  # Добавляем поле status со значением по умолчанию "ok"


from pydantic import field_validator

import sys

if sys.version_info >= (3, 10):
    from typing import TypeAlias

    DateOrNone: TypeAlias = Union[date, None]
else:
    from typing import Optional as DateOrNone

import datetime





class ParsedData(BaseModel):
    supplier: Optional[str] = None
    date: Optional[datetime.date] = None
    positions: list[Position] = []
    price: Optional[float] = None
    price_per_unit: Optional[float] = None
    total_price: Optional[float] = None
    supplier_status: Optional[str] = None  # For marking supplier status
    has_price_mismatches: bool = False
    price_mismatch_count: int = 0

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
