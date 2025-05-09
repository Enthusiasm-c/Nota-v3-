"""
Тесты для проверки обработки массива actions в parse_assistant_output.
"""

import json
import pytest
from app.assistants.client import parse_assistant_output, EditCommand


def test_parse_assistant_output_with_actions_array():
    """Проверяет, что parse_assistant_output корректно обрабатывает массив actions."""
    # Тестовый JSON с массивом actions
    test_json = """{"actions":[{"action":"set_date","date":"26.04"}]}"""
    
    # Парсинг ответа ассистента
    result = parse_assistant_output(test_json)
    
    # Проверяем, что парсинг сработал корректно
    assert isinstance(result, list)
    assert len(result) == 1
    assert isinstance(result[0], EditCommand)
    assert result[0].action == "set_date"
    assert result[0].date == "26.04"


def test_parse_assistant_output_with_multiple_actions():
    """Проверяет, что parse_assistant_output корректно обрабатывает несколько действий в массиве."""
    # Тестовый JSON с несколькими действиями
    test_json = """{"actions":[
        {"action":"set_date","date":"26.04"},
        {"action":"set_price","row":1,"price":100}
    ]}"""
    
    # Парсинг ответа ассистента
    result = parse_assistant_output(test_json)
    
    # Проверяем, что парсинг сработал корректно и вернул оба действия
    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0].action == "set_date"
    assert result[1].action == "set_price"
    assert result[1].row == 1
    assert result[1].price == 100


def test_parse_assistant_output_with_single_action():
    """Проверяет, что parse_assistant_output по-прежнему корректно обрабатывает одиночное action."""
    # Тестовый JSON с одиночным action
    test_json = """{"action":"set_date","date":"26.04"}"""
    
    # Парсинг ответа ассистента
    result = parse_assistant_output(test_json)
    
    # Проверяем, что парсинг сработал корректно
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0].action == "set_date"
    assert result[0].date == "26.04"


def test_parse_assistant_output_with_invalid_actions():
    """Проверяет обработку массива actions с невалидными элементами."""
    # Тестовый JSON с невалидными элементами
    test_json = """{"actions":[
        {"not_an_action":"something"},
        {"action":"set_price","row":1,"price":100}
    ]}"""
    
    # Парсинг ответа ассистента
    result = parse_assistant_output(test_json)
    
    # Проверяем, что парсинг вернул только валидное действие
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0].action == "set_price"
    

def test_parse_assistant_output_with_no_valid_actions():
    """Проверяет обработку случая, когда нет валидных действий."""
    # Тестовый JSON без валидных действий
    test_json = """{"actions":[
        {"not_an_action":"something"},
        {"another_field":"value"}
    ]}"""
    
    # Парсинг ответа ассистента
    result = parse_assistant_output(test_json)
    
    # Проверяем, что парсинг вернул ошибку
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0].action == "clarification_needed"