import pytest
import json
import os
import re
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch
import openai

from app.ocr import call_openai_ocr, ParsedData, INVOICE_FUNCTION_SCHEMA
from app.utils.ocr_cache import get_from_cache, save_to_cache
from app.utils.monitor import increment_counter
from app.imgprep import prepare_for_ocr
from app.config import get_ocr_client


class DummyMessage:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class DummyChoice:
    def __init__(self, message):
        self.message = message


class DummyResponse:
    def __init__(self, choices):
        self.choices = choices


class DummyFunctionCall:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments


class DummyToolCall:
    def __init__(self, function):
        self.function = function
        self.id = "call_123"
        self.type = "function"


def test_direct_vision_api(monkeypatch):
    # Мокаем ответ от Vision API с правильным JSON
    json_data = {
        "supplier": "Test Supplier",
        "date": "2025-01-01",
        "positions": [
            {
                "name": "Kacang",
                "qty": 1,
                "unit": "gr",
                "price": 10000,
                "total_price": 10000
            }
        ],
        "total_price": 10000
    }
    
    # Создаем моки для OpenAI клиента
    function_call = DummyFunctionCall(name="get_parsed_invoice", arguments=json.dumps(json_data))
    tool_call = DummyToolCall(function=function_call)
    dummy_message = DummyMessage(tool_calls=[tool_call])
    dummy_choice = DummyChoice(dummy_message)
    dummy_response = DummyResponse([dummy_choice])
    
    completions_create = MagicMock(return_value=dummy_response)
    chat = MagicMock()
    chat.completions.create = completions_create

    # Создаем мок клиента OpenAI
    client = MagicMock()
    client.chat = chat
    
    # Подменяем функцию получения клиента
    monkeypatch.setattr("app.ocr.get_ocr_client", lambda: client)
    
    # Мокаем остальные зависимости
    monkeypatch.setattr("app.ocr.time", type("T", (), {"time": lambda *a, **kw: 0})())
    monkeypatch.setattr(
        "app.ocr.base64", type("B", (), {"b64encode": lambda *a, **kw: b"xx", "decode": lambda *a, **kw: "xx"})()
    )
    
    # Запускаем тестируемую функцию
    res = call_openai_ocr(b"123")
    
    # Проверяем, что chat.completions.create вызван с правильными параметрами
    completions_create.assert_called_once()
    call_args = completions_create.call_args[1]
    assert call_args["model"] == "gpt-4o"
    assert call_args["temperature"] == 0.0
    assert call_args["tools"][0]["type"] == "function"
    assert call_args["tools"][0]["function"] == INVOICE_FUNCTION_SCHEMA
    assert call_args["tool_choice"]["type"] == "function"
    assert call_args["tool_choice"]["function"]["name"] == "get_parsed_invoice"
    
    # Проверяем результат
    assert isinstance(res, ParsedData)
    assert res.supplier == "Test Supplier"
    assert res.date == date(2025, 1, 1)
    assert len(res.positions) == 1
    assert res.positions[0].name == "Kacang"
    assert res.positions[0].qty == 1
    assert res.positions[0].unit == "gr"
    assert res.positions[0].price == 10000
    assert res.positions[0].total_price == 10000
    assert res.total_price == 10000


def test_json_extraction_with_nested_data(monkeypatch):
    # Тест для проверки извлечения данных с вложенной структурой
    json_data = {
        "supplier": "Test Supplier",
        "date": "2025-01-01",
        "positions": [
            {
                "name": "Product",
                "qty": 2,
                "unit": "kg",
                "price": 15000,
                "total_price": 30000
            }
        ],
        "total_price": 30000
    }

    # Создаем моки
    function_call = DummyFunctionCall(name="get_parsed_invoice", arguments=json.dumps(json_data))
    tool_call = DummyToolCall(function=function_call)
    dummy_message = DummyMessage(tool_calls=[tool_call])
    dummy_choice = DummyChoice(dummy_message)
    dummy_response = DummyResponse([dummy_choice])
    
    client = MagicMock()
    client.chat.completions.create = MagicMock(return_value=dummy_response)
    
    monkeypatch.setattr("app.ocr.get_ocr_client", lambda: client)
    monkeypatch.setattr("app.ocr.time", type("T", (), {"time": lambda *a, **kw: 0})())
    monkeypatch.setattr(
        "app.ocr.base64", type("B", (), {"b64encode": lambda *a, **kw: b"xx", "decode": lambda *a, **kw: "xx"})()
    )
    
    # Запускаем тестируемую функцию
    res = call_openai_ocr(b"123")
    
    # Проверяем результат
    assert isinstance(res, ParsedData)
    assert res.supplier == "Test Supplier"
    assert res.date == date(2025, 1, 1)
    assert len(res.positions) == 1
    assert res.positions[0].name == "Product"
    assert res.positions[0].qty == 2
    assert res.positions[0].unit == "kg"
    assert res.positions[0].price == 15000
    assert res.positions[0].total_price == 30000
    assert res.total_price == 30000


def test_call_openai_ocr_no_client(monkeypatch):
    # Мокаем отсутствие клиента
    monkeypatch.setattr("app.ocr.get_ocr_client", lambda: None)
    with pytest.raises(RuntimeError):
        call_openai_ocr(b"123")


def test_call_openai_ocr_invalid_api_response(monkeypatch):
    # Мокаем клиента, который возвращает некорректный ответ
    class DummyResponse:
        def __init__(self):
            self.choices = [type("C", (), {"message": type("M", (), {"tool_calls": []})()})]
    client = type("Client", (), {"chat": type("Chat", (), {"completions": type("Comp", (), {"create": lambda *a, **k: DummyResponse()})()})()})()
    monkeypatch.setattr("app.ocr.get_ocr_client", lambda: client)
    with pytest.raises(Exception):
        call_openai_ocr(b"123")


def test_call_openai_ocr_cache_error(monkeypatch):
    # Мокаем ошибку при чтении из кеша
    monkeypatch.setattr("app.ocr.get_from_cache", lambda x: (_ for _ in ()).throw(Exception("cache error")))
    # Мокаем клиента, чтобы не доходить до реального вызова
    class DummyResponse:
        def __init__(self):
            self.choices = [type("C", (), {"message": type("M", (), {"tool_calls": [type("T", (), {"function": type("F", (), {"name": "get_parsed_invoice", "arguments": "{}"})()})]})()})]
    client = type("Client", (), {"chat": type("Chat", (), {"completions": type("Comp", (), {"create": lambda *a, **k: DummyResponse()})()})()})()
    monkeypatch.setattr("app.ocr.get_ocr_client", lambda: client)
    monkeypatch.setattr("app.ocr.time", type("T", (), {"time": lambda *a, **kw: 0})())
    monkeypatch.setattr("app.ocr.base64", type("B", (), {"b64encode": lambda *a, **kw: b"xx", "decode": lambda *a, **kw: "xx"})())
    # Ошибка кеша не должна приводить к падению OCR
    call_openai_ocr(b"123", use_cache=True)


def test_call_openai_ocr_image_opt_error(monkeypatch):
    # Мокаем ошибку оптимизации изображения
    monkeypatch.setattr("app.ocr.prepare_for_ocr", lambda *a, **k: (_ for _ in ()).throw(Exception("prep error")))
    # Мокаем клиента
    class DummyResponse:
        def __init__(self):
            self.choices = [type("C", (), {"message": type("M", (), {"tool_calls": [type("T", (), {"function": type("F", (), {"name": "get_parsed_invoice", "arguments": "{}"})()})]})()})]
    client = type("Client", (), {"chat": type("Chat", (), {"completions": type("Comp", (), {"create": lambda *a, **k: DummyResponse()})()})()})()
    monkeypatch.setattr("app.ocr.get_ocr_client", lambda: client)
    monkeypatch.setattr("app.ocr.time", type("T", (), {"time": lambda *a, **kw: 0})())
    monkeypatch.setattr("app.ocr.base64", type("B", (), {"b64encode": lambda *a, **kw: b"xx", "decode": lambda *a, **kw: "xx"})())
    # Ошибка оптимизации не должна приводить к падению OCR
    call_openai_ocr(b"123")


def test_call_openai_cache_hit(monkeypatch):
    # Проверяем, что при наличии результата в кеше, он используется и API не вызывается
    cached_result = ParsedData(
        supplier="Cached Supplier",
        date=date(2025, 1, 1),
        positions=[],
        total_price=1000
    )
    
    # Мокаем функцию получения из кеша
    monkeypatch.setattr("app.ocr.get_from_cache", lambda x: cached_result)
    
    # Мокаем счетчик кеш-хитов
    mock_increment = MagicMock()
    monkeypatch.setattr("app.ocr.increment_counter", mock_increment)
    
    # Мокаем OpenAI клиент и убедимся, что он не вызывается
    mock_client = MagicMock()
    monkeypatch.setattr("app.ocr.get_ocr_client", lambda: mock_client)
    
    # Запускаем функцию с использованием кеша
    result = call_openai_ocr(b"test_image", use_cache=True)
    
    # Проверяем, что результат взят из кеша
    assert result == cached_result
    
    # Проверяем, что счетчик хитов кеша был увеличен
    mock_increment.assert_called_once_with("nota_ocr_cache_hits")
    
    # Проверяем, что API не вызывался
    assert not mock_client.chat.completions.create.called


def test_call_openai_ocr_api_timeout(monkeypatch):
    # Проверяем обработку таймаута API
    client = MagicMock()
    client.chat.completions.create.side_effect = openai.APITimeoutError(
        "Request timed out", 
        request="dummy request"
    )
    
    monkeypatch.setattr("app.ocr.get_ocr_client", lambda: client)
    monkeypatch.setattr("app.ocr.time", type("T", (), {"time": lambda *a, **kw: 0})())
    monkeypatch.setattr(
        "app.ocr.base64", type("B", (), {"b64encode": lambda *a, **kw: b"xx", "decode": lambda *a, **kw: "xx"})()
    )
    
    # Проверяем, что функция выбрасывает RuntimeError при таймауте
    with pytest.raises(RuntimeError) as excinfo:
        call_openai_ocr(b"test_image")
    
    # Проверяем сообщение об ошибке
    assert "timed out" in str(excinfo.value)


def test_call_openai_ocr_api_error(monkeypatch):
    # Проверяем обработку API ошибки
    client = MagicMock()
    client.chat.completions.create.side_effect = openai.APIError(
        "API error occurred",
        request="dummy request",
        http_status=500
    )
    
    monkeypatch.setattr("app.ocr.get_ocr_client", lambda: client)
    monkeypatch.setattr("app.ocr.time", type("T", (), {"time": lambda *a, **kw: 0})())
    monkeypatch.setattr(
        "app.ocr.base64", type("B", (), {"b64encode": lambda *a, **kw: b"xx", "decode": lambda *a, **kw: "xx"})()
    )
    
    # Проверяем, что функция выбрасывает RuntimeError при ошибке API
    with pytest.raises(RuntimeError) as excinfo:
        call_openai_ocr(b"test_image")
    
    # Проверяем сообщение об ошибке
    assert "API error" in str(excinfo.value)


def test_call_openai_ocr_invalid_function_name(monkeypatch):
    # Мокаем ответ с неправильным именем функции
    function_call = DummyFunctionCall(name="wrong_function", arguments="{}")
    tool_call = DummyToolCall(function=function_call)
    dummy_message = DummyMessage(tool_calls=[tool_call])
    dummy_choice = DummyChoice(dummy_message)
    dummy_response = DummyResponse([dummy_choice])
    
    client = MagicMock()
    client.chat.completions.create = MagicMock(return_value=dummy_response)
    
    monkeypatch.setattr("app.ocr.get_ocr_client", lambda: client)
    monkeypatch.setattr("app.ocr.time", type("T", (), {"time": lambda *a, **kw: 0})())
    monkeypatch.setattr(
        "app.ocr.base64", type("B", (), {"b64encode": lambda *a, **kw: b"xx", "decode": lambda *a, **kw: "xx"})()
    )
    
    # Проверяем, что функция выбрасывает исключение при неправильном имени функции
    with pytest.raises(RuntimeError) as excinfo:
        call_openai_ocr(b"test_image")
    
    # Проверяем сообщение об ошибке
    assert "Неожиданное имя функции" in str(excinfo.value)


def test_call_openai_ocr_invalid_json(monkeypatch):
    # Мокаем ответ с невалидным JSON
    function_call = DummyFunctionCall(name="get_parsed_invoice", arguments="invalid json")
    tool_call = DummyToolCall(function=function_call)
    dummy_message = DummyMessage(tool_calls=[tool_call])
    dummy_choice = DummyChoice(dummy_message)
    dummy_response = DummyResponse([dummy_choice])
    
    client = MagicMock()
    client.chat.completions.create = MagicMock(return_value=dummy_response)
    
    monkeypatch.setattr("app.ocr.get_ocr_client", lambda: client)
    monkeypatch.setattr("app.ocr.time", type("T", (), {"time": lambda *a, **kw: 0})())
    monkeypatch.setattr(
        "app.ocr.base64", type("B", (), {"b64encode": lambda *a, **kw: b"xx", "decode": lambda *a, **kw: "xx"})()
    )
    
    # Проверяем, что функция выбрасывает исключение при невалидном JSON
    with pytest.raises(RuntimeError) as excinfo:
        call_openai_ocr(b"test_image")
    
    # Проверяем сообщение об ошибке
    assert "Не удалось распарсить JSON" in str(excinfo.value)


def test_strip_code_fence():
    from app.ocr import _strip_code_fence
    
    # Проверяем удаление fence
    assert _strip_code_fence("```json\n{\"data\": 123}\n```") == "{\"data\": 123}"
    
    # Проверяем удаление fence без указания языка
    assert _strip_code_fence("```\n{\"data\": 123}\n```") == "{\"data\": 123}"
    
    # Проверяем с пробелами
    assert _strip_code_fence("  ```json\n{\"data\": 123}\n```  ") == "{\"data\": 123}"
    
    # Проверяем без fence
    assert _strip_code_fence("{\"data\": 123}") == "{\"data\": 123}"