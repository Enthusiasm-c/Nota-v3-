import pytest
from decimal import Decimal
from app.models import Position, ParsedData
from app.validators.price_validator import (
    validate_position_price,
    validate_invoice_prices,
    round_decimal
)

def test_round_decimal():
    """Тестирование функции округления."""
    assert round_decimal(10.125) == Decimal('10.13')
    assert round_decimal(10.124) == Decimal('10.12')
    assert round_decimal(None) is None
    assert round_decimal(10.005) == Decimal('10.01')  # Проверка банковского округления

def test_validate_position_price_no_data():
    """Тест валидации позиции без данных."""
    position = Position(name="Test Item", qty=1.0)
    has_mismatch, mismatch_type, expected_total = validate_position_price(position)
    assert not has_mismatch
    assert mismatch_type is None
    assert expected_total is None

def test_validate_position_price_correct_total():
    """Тест валидации позиции с корректной общей суммой."""
    position = Position(
        name="Test Item",
        qty=2.0,
        price_per_unit=100.0,
        total_price=200.0
    )
    has_mismatch, mismatch_type, expected_total = validate_position_price(position)
    assert not has_mismatch
    assert mismatch_type is None
    assert expected_total is None

def test_validate_position_price_mismatch_total():
    """Тест валидации позиции с несоответствием в общей сумме."""
    position = Position(
        name="Test Item",
        qty=2.0,
        price_per_unit=100.0,
        total_price=205.0  # Должно быть 200.0
    )
    has_mismatch, mismatch_type, expected_total = validate_position_price(position)
    assert has_mismatch
    assert mismatch_type == "total_mismatch"
    assert expected_total == 200.0

def test_validate_position_price_mismatch_price():
    """Тест валидации позиции с несоответствием в цене за единицу."""
    position = Position(
        name="Test Item",
        qty=2.0,
        price=98.0,  # Неверная цена
        total_price=200.0
    )
    has_mismatch, mismatch_type, expected_total = validate_position_price(position)
    assert has_mismatch
    assert mismatch_type == "price_mismatch"
    assert expected_total == 196.0

def test_validate_invoice_prices():
    """Тест валидации всей накладной."""
    parsed_data = ParsedData(positions=[
        Position(
            name="Item 1",
            qty=2.0,
            price_per_unit=100.0,
            total_price=200.0  # Корректная сумма
        ),
        Position(
            name="Item 2",
            qty=3.0,
            price_per_unit=50.0,
            total_price=160.0  # Неверная сумма (должно быть 150.0)
        )
    ])
    
    validated_data = validate_invoice_prices(parsed_data)
    assert validated_data.has_price_mismatches
    assert validated_data.price_mismatch_count == 1
    
    # Проверяем первую позицию (корректную)
    assert not validated_data.positions[0].price_mismatch
    assert validated_data.positions[0].mismatch_type is None
    
    # Проверяем вторую позицию (с несоответствием)
    assert validated_data.positions[1].price_mismatch
    assert validated_data.positions[1].mismatch_type == "total_mismatch"
    assert validated_data.positions[1].expected_total == 150.0

def test_validate_position_price_within_tolerance():
    """Тест валидации позиции с разницей в пределах допустимой погрешности."""
    position = Position(
        name="Test Item",
        qty=2.0,
        price_per_unit=100.0,
        total_price=200.009  # Разница меньше PRICE_TOLERANCE
    )
    has_mismatch, mismatch_type, expected_total = validate_position_price(position)
    assert not has_mismatch
    assert mismatch_type is None
    assert expected_total is None 