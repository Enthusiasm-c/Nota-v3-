from app.edit.apply_intent import (
    set_price,
    set_date,
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

# Sample data for further tests
SAMPLE_INVOICE_POSITIONS = [
    {"name": "Товар 1", "qty": "10", "unit": "шт", "price": "100", "status": "ok"},
    {"name": "Товар 2", "qty": "5.5", "unit": "кг", "price": "250.75", "status": "ok"},
]
SAMPLE_INVOICE_DATA = {
    "supplier": "Test Supplier",
    "date": "2024-01-01",
    "positions": SAMPLE_INVOICE_POSITIONS
}

# Tests for Step 2: Verify robustness of apply_intent for edit_quantity and edit_price
def test_apply_intent_edit_quantity_invalid_string_value():
    """Test apply_intent with action 'edit_quantity' and an invalid string value."""
    from copy import deepcopy
    initial_invoice = deepcopy(SAMPLE_INVOICE_DATA)
    intent = {"action": "edit_quantity", "line": 1, "value": "this_is_not_a_number"} # line is 1-based for intent
    
    result_invoice = apply_intent(deepcopy(initial_invoice), intent)
    
    # The function should log a warning and return the invoice unchanged (or a deepcopy of it)
    assert result_invoice["positions"] == initial_invoice["positions"]
    assert result_invoice == initial_invoice # Overall check

def test_apply_intent_edit_price_invalid_string_value():
    """Test apply_intent with action 'edit_price' and an invalid string value."""
    from copy import deepcopy
    initial_invoice = deepcopy(SAMPLE_INVOICE_DATA)
    intent = {"action": "edit_price", "line": 1, "value": "not_a_price"} # line is 1-based
    
    result_invoice = apply_intent(deepcopy(initial_invoice), intent)
    
    assert result_invoice["positions"] == initial_invoice["positions"]
    assert result_invoice == initial_invoice

def test_apply_intent_edit_quantity_valid_numeric_value():
    """Test apply_intent with action 'edit_quantity' and a valid pre-converted numeric value."""
    from copy import deepcopy
    initial_invoice = deepcopy(SAMPLE_INVOICE_DATA)
    new_qty = 123.45
    intent = {"action": "edit_quantity", "line": 1, "value": new_qty} # line is 1-based
    
    result_invoice = apply_intent(deepcopy(initial_invoice), intent)
    
    assert result_invoice["positions"][0]["qty"] == new_qty # Position 0 for line 1
    assert result_invoice["positions"][0]["name"] == initial_invoice["positions"][0]["name"] # Ensure other parts are same

def test_apply_intent_edit_price_valid_numeric_value():
    """Test apply_intent with action 'edit_price' and a valid pre-converted numeric value."""
    from copy import deepcopy
    initial_invoice = deepcopy(SAMPLE_INVOICE_DATA)
    new_price = 99.99
    intent = {"action": "edit_price", "line": 2, "value": new_price} # line is 1-based
    
    result_invoice = apply_intent(deepcopy(initial_invoice), intent)
    
    assert result_invoice["positions"][1]["price"] == new_price # Position 1 for line 2
    assert result_invoice["positions"][1]["name"] == initial_invoice["positions"][1]["name"]

def test_apply_intent_edit_quantity_valid_string_value():
    """Test apply_intent with action 'edit_quantity' and a valid numeric string value."""
    from copy import deepcopy
    initial_invoice = deepcopy(SAMPLE_INVOICE_DATA)
    intent = {"action": "edit_quantity", "line": 1, "value": "12,34"} # line is 1-based
    
    result_invoice = apply_intent(deepcopy(initial_invoice), intent)
    
    assert result_invoice["positions"][0]["qty"] == 12.34 # Position 0 for line 1, converted

def test_apply_intent_edit_price_valid_string_value():
    """Test apply_intent with action 'edit_price' and a valid numeric string value."""
    from copy import deepcopy
    initial_invoice = deepcopy(SAMPLE_INVOICE_DATA)
    intent = {"action": "edit_price", "line": 2, "value": "300.50"} # line is 1-based
    
    result_invoice = apply_intent(deepcopy(initial_invoice), intent)
    
    assert result_invoice["positions"][1]["price"] == 300.50 # Position 1 for line 2, converted
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