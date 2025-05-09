import pytest
from app.edit.apply_intent import (
    set_price,
    set_date,
    set_name,
    set_quantity,
    set_unit,
    apply_intent
)
from app.models import ParsedData
from app.converters import parsed_to_dict

def test_parsed_to_dict_with_dict():
    d = {"a": 1, "b": 2}
    assert parsed_to_dict(d) == d

def test_parsed_to_dict_with_parseddata():
    pd = ParsedData(supplier="Test", date=None, positions=[])
    result = parsed_to_dict(pd)
    assert isinstance(result, dict)
    assert result["supplier"] == "Test"
    assert result["positions"] == []

def test_apply_intent_with_parseddata():
    pd = ParsedData(
        supplier="Test",
        date=None,
        positions=[{"name": "A", "qty": 1, "price": "10", "status": "error"}]
    )
    intent = {"action": "set_price", "line_index": 0, "value": "1000"}
    result = apply_intent(pd, intent)
    assert result["positions"][0]["price"] == "1000"
    assert result["positions"][0]["status"] == "ok"


def test_set_price():
    """Тест функции set_price"""
    invoice = {
        "positions": [
            {"name": "Товар 1", "price": "100", "status": "error"},
            {"name": "Товар 2", "price": "200", "status": "error"},
        ]
    }
    
    # Меняем цену второго товара
    result = set_price(invoice, 1, "95000")
    
    # Проверяем что цена изменилась
    assert result["positions"][1]["price"] == "95000"
    # Проверяем что статус изменился на ok
    assert result["positions"][1]["status"] == "ok"
    # Проверяем что первый товар не изменился
    assert result["positions"][0]["price"] == "100"

def test_set_date():
    """Тест функции set_date"""
    invoice = {"date": "", "supplier": "Test"}
    
    # Устанавливаем дату
    result = set_date(invoice, "2025-04-16")
    
    # Проверяем что дата изменилась
    assert result["date"] == "2025-04-16"
    # Проверяем что supplier не изменился
    assert result["supplier"] == "Test"

def test_apply_intent_price():
    """Тест apply_intent для изменения цены"""
    invoice = {
        "positions": [
            {"name": "Товар 1", "price": "100", "status": "error"},
        ]
    }
    
    intent = {
        "action": "set_price",
        "line_index": 0,
        "value": "95000"
    }
    
    result = apply_intent(invoice, intent)
    
    # Проверяем что цена изменилась
    assert result["positions"][0]["price"] == "95000"
    # Проверяем что статус изменился на ok
    assert result["positions"][0]["status"] == "ok"

def test_apply_intent_date():
    """Тест apply_intent для изменения даты"""
    invoice = {"date": "", "supplier": "Test"}
    
    intent = {
        "action": "set_date",
        "value": "2025-04-16"
    }
    
    result = apply_intent(invoice, intent)
    
    # Проверяем что дата изменилась
    assert result["date"] == "2025-04-16"