"""
Тесты для проверки обработки массива actions в intent_adapter.
Проверяет, что IntentAdapter корректно обрабатывает формат {"actions": [{"action": "..."}]}.
"""

import json
import pytest
from app.assistants.intent_adapter import IntentAdapter, adapt_intent


def test_adapt_intent_with_actions_array():
    """Проверяет, что адаптер корректно обрабатывает массив actions."""
    # Тестовый JSON с массивом actions
    test_json = """{"actions":[{"action":"set_date","date":"26.04"}]}"""
    
    # Адаптация интента
    result = adapt_intent(test_json)
    
    # Проверяем, что адаптер корректно извлек action и date
    assert result["action"] == "set_date"
    assert result["value"] is not None  # Конкретное значение зависит от нормализации


def test_adapt_intent_with_multiple_actions():
    """Проверяет, что адаптер берет первое действие из массива actions."""
    # Тестовый JSON с несколькими действиями
    test_json = """{"actions":[
        {"action":"set_date","date":"26.04"},
        {"action":"set_price","line":1,"price":100}
    ]}"""
    
    # Адаптация интента
    result = adapt_intent(test_json)
    
    # Проверяем, что адаптер взял первое действие (set_date)
    assert result["action"] == "set_date"
    assert result["value"] is not None


def test_adapt_intent_with_single_action():
    """Проверяет, что адаптер по-прежнему корректно обрабатывает одиночное action."""
    # Тестовый JSON с одиночным action
    test_json = """{"action":"set_date","date":"26.04"}"""
    
    # Адаптация интента
    result = adapt_intent(test_json)
    
    # Проверяем, что адаптер корректно извлек action и date
    assert result["action"] == "set_date"
    assert result["value"] is not None


def test_extract_json_with_actions_array():
    """Проверяет, что _extract_json корректно извлекает JSON с массивом actions из текста."""
    # Текст с JSON внутри
    text = """Я изменил дату на 26.04, вот результат:
    {"actions":[{"action":"set_date","date":"26.04"}]}
    Готово!"""
    
    # Извлечение JSON
    result = IntentAdapter._extract_json(text)
    
    # Проверяем, что извлечение сработало корректно
    assert isinstance(result, dict)
    assert "actions" in result
    assert isinstance(result["actions"], list)
    assert len(result["actions"]) > 0
    assert result["actions"][0]["action"] == "set_date"


def test_intent_normalization_with_actions_array():
    """Проверяет нормализацию полей при использовании формата actions array."""
    # Создаем JSON с массивом actions в формате строки
    actions_json = """{"actions":[{"action":"set_price","line":2,"price":1500}]}"""
    
    # Адаптация интента
    result = adapt_intent(actions_json)
    
    # Проверяем, что поля нормализованы корректно
    assert result["action"] == "set_price"
    assert "line_index" in result  # line должен быть преобразован в line_index (индекс с 0)
    assert result["line_index"] == 1  # 2-1 = 1 (конвертация из 1-based в 0-based)
    assert "value" in result  # price должен быть преобразован в value