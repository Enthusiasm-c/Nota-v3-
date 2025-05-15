import pytest
from app.assistants.intent_adapter import IntentAdapter


def test_fast_recognize_set_price():
    text = "строка 2 цена 150"
    result = IntentAdapter._fast_recognize(text)
    assert result == {"action": "set_price", "line_index": 1, "value": "150"}


def test_fast_recognize_set_date():
    text = "дата 15 мая"
    result = IntentAdapter._fast_recognize(text)
    assert result["action"] == "set_date"
    assert result["value"].endswith("-05-15")


def test_adapt_valid_json():
    response = {"action": "set_price", "line_index": 0, "value": "100"}
    result = IntentAdapter.adapt(response)
    assert result["action"] == "set_price"
    assert result["line_index"] == 0
    assert result["value"] == "100"


def test_adapt_invalid_action():
    response = {"action": "unknown_action", "foo": 1}
    result = IntentAdapter.adapt(response)
    assert result["action"] == "unknown"
    assert "unsupported_action" in result["error"]


def test_adapt_missing_fields():
    response = {"action": "set_price", "line_index": 0}
    result = IntentAdapter.adapt(response)
    assert result["action"] == "unknown"
    assert "missing_fields" in result["error"]


def test_adapt_extract_json():
    text = '{"action": "set_name", "line_index": 1, "value": "Apple"}'
    result = IntentAdapter.adapt(text)
    assert result["action"] == "set_name"
    assert result["line_index"] == 1
    assert result["value"] == "Apple"


def test_adapt_actions_array():
    response = {"actions": [{"action": "set_date", "value": "2024-05-15"}]}
    result = IntentAdapter.adapt(response)
    assert result["action"] == "set_date"
    assert result["value"] == "2024-05-15"


def test_adapt_not_a_dict():
    result = IntentAdapter.adapt([1, 2, 3])
    assert result["action"] == "unknown"
    assert result["error"] == "not_a_dict" 