import pytest
pytest_plugins = ["pytest_asyncio"]
import json
import os
import re
from datetime import date
from app.ocr import call_openai_ocr, ParsedData, INVOICE_FUNCTION_SCHEMA
from unittest.mock import AsyncMock, MagicMock


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
    assert call_args["max_tokens"] == 2048
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


def test_postprocessing_clean_num():
    from app.postprocessing import clean_num
    assert clean_num("10,000") == 10000
    assert clean_num("10.000") == 10000
    assert clean_num("10k") == 10000
    assert clean_num("10к") == 10000
    assert clean_num("12 345,67") == 12345.67
    assert clean_num("12 345.67") == 12345.67
    assert clean_num("12,345.67") == 12345.67
    assert clean_num("12.345,67") == 12345.67 or clean_num("12.345,67") == 12345.67  # зависит от локали
    assert clean_num(None) is None
    assert clean_num("") is None
    assert clean_num("null") is None


def test_postprocessing_autocorrect_name():
    from app.postprocessing import autocorrect_name
    allowed = ["Тунец", "Лосось", "Креветка"]
    assert autocorrect_name("Тунец", allowed) == "Тунец"
    assert autocorrect_name("Тунецц", allowed) == "Тунец"
    assert autocorrect_name("Кревета", allowed) == "Креветка"
    assert autocorrect_name("Лосось", allowed) == "Лосось"
    assert autocorrect_name("Краб", allowed) == "Краб"  # нет похожих, не меняет


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
