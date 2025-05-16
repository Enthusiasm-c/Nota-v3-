import pytest
from app.edit.multi_edit_parser import parse_multi_edit_command, apply_multi_edit

@pytest.fixture
def sample_invoice():
    return {
        "date": "01.01.2025",
        "positions": [
            {"name": "Товар 1", "qty": "1", "unit": "шт", "price": "100"},
            {"name": "Товар 2", "qty": "2", "unit": "кг", "price": "200"},
            {"name": "Товар 3", "qty": "3", "unit": "л", "price": "300"}
        ]
    }

def test_parse_multi_edit_command():
    # Тест парсинга мультистрочной команды
    command = "строка 1 цена 150 ; строка 2 qty 3 ; дата 05.08.2025"
    intents = parse_multi_edit_command(command)
    
    assert len(intents) == 3
    assert intents[0] == {"action": "edit_line_field", "line": 1, "field": "price", "value": "150"}
    assert intents[1] == {"action": "edit_line_field", "line": 2, "field": "qty", "value": "3"}
    assert intents[2] == {"action": "edit_date", "value": "05.08.2025"}

def test_parse_multi_edit_with_invalid_commands():
    # Тест обработки невалидных команд в мультистрочном режиме
    command = "строка 1 цена 150 ; неправильная команда ; дата 05.08.2025"
    intents = parse_multi_edit_command(command)
    
    assert len(intents) == 2  # Невалидная команда должна быть пропущена
    assert intents[0] == {"action": "edit_line_field", "line": 1, "field": "price", "value": "150"}
    assert intents[1] == {"action": "edit_date", "value": "05.08.2025"}

def test_apply_multi_edit(sample_invoice):
    # Тест применения нескольких изменений
    intents = [
        {"action": "edit_line_field", "line": 1, "field": "price", "value": "150"},
        {"action": "edit_line_field", "line": 2, "field": "qty", "value": "3"},
        {"action": "edit_date", "value": "05.08.2025"}
    ]
    
    new_invoice, applied_changes = apply_multi_edit(sample_invoice, intents)
    
    assert len(applied_changes) == 3
    assert new_invoice["date"] == "05.08.2025"
    assert new_invoice["positions"][0]["price"] == "150"
    assert new_invoice["positions"][1]["qty"] == "3"

def test_apply_multi_edit_with_errors(sample_invoice):
    # Тест обработки ошибок при применении изменений
    intents = [
        {"action": "edit_line_field", "line": 1, "field": "price", "value": "150"},
        {"action": "edit_line_field", "line": 10, "field": "qty", "value": "3"},  # Несуществующая строка
        {"action": "edit_date", "value": "05.08.2025"}
    ]
    
    new_invoice, applied_changes = apply_multi_edit(sample_invoice, intents)
    
    assert len(applied_changes) == 2  # Только два изменения должны быть применены
    assert new_invoice["date"] == "05.08.2025"
    assert new_invoice["positions"][0]["price"] == "150"

def test_empty_multi_edit_command():
    # Тест пустой команды
    command = "  ;  ;  "
    intents = parse_multi_edit_command(command)
    
    assert len(intents) == 0

def test_multi_edit_with_spaces():
    # Тест обработки пробелов в командах
    command = " строка 1 цена 150;   строка 2 qty 3  ;дата 05.08.2025 "
    intents = parse_multi_edit_command(command)
    
    assert len(intents) == 3
    assert intents[0] == {"action": "edit_line_field", "line": 1, "field": "price", "value": "150"}
    assert intents[1] == {"action": "edit_line_field", "line": 2, "field": "qty", "value": "3"}
    assert intents[2] == {"action": "edit_date", "value": "05.08.2025"}

def test_multi_field_edit():
    # Тест множественных изменений в одной строке и между строками
    command = "line 1 qty 5 unit kg ; line 6 price 55000 qty 2"
    intents = parse_multi_edit_command(command)
    
    # Проверяем первую часть команды (строка 1)
    assert len(intents) == 4  # Должно быть 4 изменения
    assert intents[0] == {"action": "edit_line_field", "line": 1, "field": "qty", "value": "5"}
    assert intents[1] == {"action": "edit_line_field", "line": 1, "field": "unit", "value": "kg"}
    
    # Проверяем вторую часть команды (строка 6)
    assert intents[2] == {"action": "edit_line_field", "line": 6, "field": "price", "value": "55000"}
    assert intents[3] == {"action": "edit_line_field", "line": 6, "field": "qty", "value": "2"} 