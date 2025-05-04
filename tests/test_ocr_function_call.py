import pytest
import vcr
from app import ocr
from pathlib import Path
from unittest.mock import MagicMock

CASSETTE_PATH = str(Path(__file__).parent / "vcr_cassettes" / "ocr_function_call.yaml")
SAMPLE_IMAGE = str(Path(__file__).parent / "sample_invoice.jpg")


def test_openai_function_call(monkeypatch):
    # Patch API key and model for test
    monkeypatch.setattr("app.config.settings.OPENAI_API_KEY", "sk-test-123")
    monkeypatch.setattr("app.config.settings.OPENAI_MODEL", "gpt-4o")
    # Prepare a valid mock OpenAI response
    mock_function = MagicMock()
    mock_function.arguments = '{"supplier": "Test Supplier", "date": null, "positions": [{"name": "Tuna loin", "qty": 1, "unit": "kg", "price": 100.0}]}'
    mock_tool_call = MagicMock()
    mock_tool_call.function = mock_function
    mock_message = MagicMock()
    mock_message.tool_calls = [mock_tool_call]
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_completions_create = MagicMock(return_value=MagicMock(choices=[mock_choice]))
    mock_openai_client = MagicMock(
        chat=MagicMock(completions=MagicMock(create=mock_completions_create))
    )
    monkeypatch.setattr(
        "app.ocr.openai", MagicMock(OpenAI=MagicMock(return_value=mock_openai_client))
    )
    with open(SAMPLE_IMAGE, "rb") as f:
        img_bytes = f.read()
    with vcr.use_cassette(CASSETTE_PATH):
        parsed = ocr.call_openai_ocr(img_bytes)
        assert hasattr(parsed, "positions")
        assert parsed.supplier is None or isinstance(parsed.supplier, str)
        assert (
            parsed.date is None
            or isinstance(parsed.date, str)
            or hasattr(parsed.date, "isoformat")
        )
        assert isinstance(parsed.positions, list)
