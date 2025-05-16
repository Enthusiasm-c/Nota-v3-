import pytest
from app.models import Position, ParsedData
from app.validators.price_validator import validate_invoice_prices
from app.formatters.report import build_report

def test_price_validation_total_mismatch():
    """Тест валидации позиции с несоответствием в общей сумме."""
    # Создаем тестовые данные
    position = Position(
        name="Test Item",
        qty=2.0,
        price_per_unit=100.0,
        total_price=205.0  # Должно быть 200.0
    )
    parsed_data = ParsedData(positions=[position])
    
    # Проверяем валидацию
    validated_data = validate_invoice_prices(parsed_data)
    
    assert validated_data.has_price_mismatches
    assert validated_data.price_mismatch_count == 1
    assert validated_data.positions[0].price_mismatch
    assert validated_data.positions[0].mismatch_type == "total_mismatch"
    assert validated_data.positions[0].expected_total == 200.0

def test_price_validation_no_mismatch():
    """Тест валидации позиции без несоответствий в ценах."""
    position = Position(
        name="Test Item",
        qty=2.0,
        price_per_unit=100.0,
        total_price=200.0
    )
    parsed_data = ParsedData(positions=[position])
    
    validated_data = validate_invoice_prices(parsed_data)
    
    assert not validated_data.has_price_mismatches
    assert validated_data.price_mismatch_count == 0
    assert not validated_data.positions[0].price_mismatch
    assert validated_data.positions[0].mismatch_type is None
    assert validated_data.positions[0].expected_total is None

def test_price_validation_within_tolerance():
    """Тест валидации позиции с разницей в пределах допустимой погрешности."""
    position = Position(
        name="Test Item",
        qty=2.0,
        price_per_unit=100.0,
        total_price=200.009  # Разница меньше PRICE_TOLERANCE
    )
    parsed_data = ParsedData(positions=[position])
    
    validated_data = validate_invoice_prices(parsed_data)
    
    assert not validated_data.has_price_mismatches
    assert validated_data.price_mismatch_count == 0
    assert not validated_data.positions[0].price_mismatch

def test_price_validation_report_display():
    """Тест отображения несоответствий в ценах в отчете."""
    # Создаем тестовые данные с несоответствием в цене
    position1 = Position(
        name="Item 1",
        qty=2.0,
        price_per_unit=100.0,
        total_price=205.0,  # Должно быть 200.0
        status="ok"
    )
    position2 = Position(
        name="Item 2",
        qty=3.0,
        price=50.0,
        total_price=200.0,  # Должно быть 150.0
        status="ok"
    )
    parsed_data = ParsedData(positions=[position1, position2])
    
    # Валидируем данные
    validated_data = validate_invoice_prices(parsed_data)
    
    # Создаем отчет
    match_results = [
        {
            "name": position.name,
            "qty": position.qty,
            "unit": position.unit,
            "price": position.price,
            "status": position.status,
            "price_mismatch": position.price_mismatch,
            "mismatch_type": position.mismatch_type,
            "expected_total": position.expected_total
        }
        for position in validated_data.positions
    ]
    
    report, has_errors = build_report(validated_data, match_results)
    
    # Проверяем наличие информации о несоответствиях в отчете
    assert "💰" in report  # Символ для несоответствий в ценах
    assert "Found 2 price mismatches" in report
    assert "expected total: 200.0" in report
    assert "expected total: 150.0" in report
    assert has_errors  # Отчет должен показывать наличие ошибок

def test_price_validation_empty_data():
    """Тест валидации пустых данных."""
    parsed_data = ParsedData(positions=[])
    
    validated_data = validate_invoice_prices(parsed_data)
    
    assert not validated_data.has_price_mismatches
    assert validated_data.price_mismatch_count == 0
    assert len(validated_data.positions) == 0

def test_price_validation_missing_values():
    """Тест валидации позиции с отсутствующими значениями."""
    position = Position(
        name="Test Item",
        qty=2.0,
        # Отсутствуют price_per_unit и total_price
    )
    parsed_data = ParsedData(positions=[position])
    
    validated_data = validate_invoice_prices(parsed_data)
    
    assert not validated_data.has_price_mismatches
    assert validated_data.price_mismatch_count == 0
    assert not validated_data.positions[0].price_mismatch 