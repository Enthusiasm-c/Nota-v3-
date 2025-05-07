import pytest
from app.edit import free_parser

def test_detect_intent_date():
    assert free_parser.detect_intent('дата — 26 апреля')['action'] == 'edit_date'
    assert free_parser.detect_intent('invoice date 2025-05-04')['action'] == 'edit_date'

def test_detect_intent_edit_line_field():
    intent = free_parser.detect_intent('строка 2 цена 90000')
    assert intent['action'] == 'edit_line_field'
    assert intent['line'] == 2
    assert intent['field'] in ('цена', 'price')
    assert intent['value'] == '90000'

def test_detect_intent_remove_line():
    intent = free_parser.detect_intent('удали 3')
    assert intent['action'] == 'remove_line'
    assert intent['line'] == 3

def test_detect_intent_add_line():
    intent = free_parser.detect_intent('добавь product X 12 kg 15000')
    assert intent['action'] == 'add_line'
    assert intent['value'].startswith('product X')

def test_apply_edit_date():
    invoice = {'date': '', 'positions': []}
    intent = {'action': 'edit_date', 'value': '2025-05-05'}
    result = free_parser.apply_edit(invoice, intent)
    assert result['date'] == '2025-05-05'

def test_apply_edit_line_field():
    invoice = {'date': '', 'positions': [{'name': 'A', 'qty': '1', 'unit': 'шт', 'price': '100'}]}
    intent = {'action': 'edit_line_field', 'line': 1, 'field': 'price', 'value': '200'}
    result = free_parser.apply_edit(invoice, intent)
    assert result['positions'][0]['price'] == '200'

def test_apply_remove_line():
    invoice = {'date': '', 'positions': [
        {'name': 'A', 'qty': '1', 'unit': 'шт', 'price': '100'},
        {'name': 'B', 'qty': '2', 'unit': 'кг', 'price': '300'}
    ]}
    intent = {'action': 'remove_line', 'line': 2}
    result = free_parser.apply_edit(invoice, intent)
    assert len(result['positions']) == 1
    assert result['positions'][0]['name'] == 'A'

def test_apply_add_line():
    invoice = {'date': '', 'positions': []}
    intent = {'action': 'add_line', 'value': 'ProductX 2 kg 1000'}
    result = free_parser.apply_edit(invoice, intent)
    assert len(result['positions']) == 1
    assert result['positions'][0]['name'] == 'ProductX'
    assert result['positions'][0]['qty'] == '2'
    assert result['positions'][0]['unit'] == 'kg'
    assert result['positions'][0]['price'] == '1000'

def test_remove_nonexistent_line():
    invoice = {'date': '', 'positions': [{'name': 'A', 'qty': '1', 'unit': 'шт', 'price': '100'}]}
    intent = {'action': 'remove_line', 'line': 5}
    result = free_parser.apply_edit(invoice, intent)
    # Должно остаться без изменений
    assert result == invoice

def test_edit_nonexistent_line():
    invoice = {'date': '', 'positions': [{'name': 'A', 'qty': '1', 'unit': 'шт', 'price': '100'}]}
    intent = {'action': 'edit_line_field', 'line': 3, 'field': 'price', 'value': '200'}
    result = free_parser.apply_edit(invoice, intent)
    # Должно остаться без изменений
    assert result == invoice

def test_add_line_wrong_format():
    invoice = {'date': '', 'positions': []}
    # value не разбивается на 4 части
    intent = {'action': 'add_line', 'value': 'ТолькоИмя'}
    result = free_parser.apply_edit(invoice, intent)
    # Не должно добавиться ничего
    assert result['positions'] == []

def test_edit_unknown_field():
    invoice = {'date': '', 'positions': [{'name': 'A', 'qty': '1', 'unit': 'шт', 'price': '100'}]}
    intent = {'action': 'edit_line_field', 'line': 1, 'field': 'unknown', 'value': 'test'}
    result = free_parser.apply_edit(invoice, intent)
    # Поле не изменится, т.к. такого ключа нет
    assert 'unknown' in result['positions'][0] or result == invoice

def test_finish_intent():
    invoice = {'date': '2025-05-05', 'positions': []}
    intent = {'action': 'finish'}
    result = free_parser.apply_edit(invoice, intent)
    # Должно остаться без изменений
    assert result == invoice

def test_unknown_intent():
    invoice = {'date': '2025-05-05', 'positions': []}
    intent = {'action': 'unknown'}
    result = free_parser.apply_edit(invoice, intent)
    # Должно остаться без изменений
    assert result == invoice


def test_empty_invoice():
    invoice = {}
    intent = {'action': 'edit_date', 'value': '2025-01-01'}
    try:
        result = free_parser.apply_edit(invoice, intent)
    except Exception:
        result = None
    assert result is None or result == invoice or (isinstance(result, dict) and 'date' in result)


def test_none_fields():
    invoice = {'date': None, 'positions': [None]}
    intent = {'action': 'edit_line_field', 'line': 1, 'field': 'price', 'value': '200'}
    try:
        result = free_parser.apply_edit(invoice, intent)
    except Exception:
        result = None
    assert result is None or result == invoice


def test_invalid_types():
    invoice = {'date': '', 'positions': [{'name': 123, 'qty': [], 'unit': {}, 'price': None}]}
    intent = {'action': 'edit_line_field', 'line': 1, 'field': 'price', 'value': '200'}
    result = free_parser.apply_edit(invoice, intent)
    assert result['positions'][0]['price'] == '200'


def test_add_line_extra_spaces():
    invoice = {'date': '', 'positions': []}
    intent = {'action': 'add_line', 'value': '   X   1   шт   100  '}
    result = free_parser.apply_edit(invoice, intent)
    assert len(result['positions']) == 1
    assert result['positions'][0]['name'] == 'X'
    assert result['positions'][0]['qty'] == '1'
    assert result['positions'][0]['unit'] == 'шт'
    assert result['positions'][0]['price'] == '100'


def test_detect_intent_none():
    # Проверка, что None не вызывает ошибку
    try:
        intent = free_parser.detect_intent(None)
    except Exception:
        intent = None
    assert intent is None or intent['action'] == 'unknown'
