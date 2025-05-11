import pytest
import vcr
from app import ocr
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

CASSETTE_PATH = str(Path(__file__).parent / "vcr_cassettes" / "ocr_function_call.yaml")
SAMPLE_IMAGE = str(Path(__file__).parent / "sample_invoice.jpg")


@pytest.mark.asyncio
async def test_openai_function_call(monkeypatch):
    # Patch API key and model for test
    monkeypatch.setattr("app.config.settings.OPENAI_API_KEY", "sk-test-123")
    monkeypatch.setattr("app.config.settings.OPENAI_MODEL", "gpt-4o")
    monkeypatch.setattr(
        "app.ocr.settings",
        type("S", (), {
            "OPENAI_API_KEY": "sk-test-123",
            "OPENAI_MODEL": "gpt-4o",
            "OPENAI_VISION_ASSISTANT_ID": "test-assistant-id"
        })(),
    )
    # Prepare a valid mock OpenAI response
    # Мокаем структуру клиента OpenAI Vision Assistant
    thread = AsyncMock()
    thread.id = "thread-id"
    threads = AsyncMock()
    threads.create = AsyncMock(return_value=thread)
    message_create = AsyncMock()
    threads.messages = AsyncMock()
    threads.messages.create = message_create
    run = AsyncMock()
    run.id = "run-id"
    runs = AsyncMock()
    runs.create = AsyncMock(return_value=run)
    runs.retrieve = AsyncMock(return_value=AsyncMock(status='completed'))
    threads.runs = runs
    threads.runs.create = runs.create
    threads.runs.retrieve = runs.retrieve
    threads.runs.cancel = AsyncMock()
    message = AsyncMock()
    message.role = "assistant"
    message.content = [type("C", (), {"type": "text", "text": '{"supplier": "Test Supplier", "positions": [{"name": "Tuna loin", "qty": 1, "unit": "kg", "price": 100.0}]}'})()]
    messages = AsyncMock()
    messages.data = [message]
    threads.messages.list = AsyncMock(return_value=messages)
    beta = AsyncMock()
    beta.threads = threads
    client = AsyncMock()
    client.beta = beta
    monkeypatch.setattr("app.ocr.get_ocr_client", lambda: client)
    with open(SAMPLE_IMAGE, "rb") as f:
        img_bytes = f.read()
    with vcr.use_cassette(CASSETTE_PATH):
        parsed = await ocr.call_openai_ocr(img_bytes)
        assert hasattr(parsed, "positions")
        assert parsed.supplier is None or isinstance(parsed.supplier, str)
        assert (
            parsed.date is None
            or isinstance(parsed.date, str)
            or hasattr(parsed.date, "isoformat")
        )
        assert isinstance(parsed.positions, list)
