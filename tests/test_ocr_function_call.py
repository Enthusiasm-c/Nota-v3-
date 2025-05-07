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
    # Prepare a valid mock OpenAI response (sync mocks for run_in_executor)
    from unittest.mock import MagicMock
    thread = MagicMock()
    thread.id = "thread-id"
    run = MagicMock()
    run.id = "run-id"
    run_status = MagicMock()
    run_status.status = 'completed'
    message = MagicMock()
    message.role = "assistant"
    message.content = [type("C", (), {"type": "text", "text": '{"supplier": "Test Supplier", "positions": [{"name": "Tuna loin", "qty": 1, "unit": "kg", "price": 100.0}]}'})()]
    messages = MagicMock()
    messages.data = [message]

    # Мокаем клиент и все нужные методы
    class DummyThreads:
        def create(self):
            return thread
        class messages:
            @staticmethod
            def create(**kwargs):
                return None
            @staticmethod
            def list(**kwargs):
                return messages
        class runs:
            @staticmethod
            def create(**kwargs):
                return run
            @staticmethod
            def retrieve(**kwargs):
                return run_status
            @staticmethod
            def cancel(**kwargs):
                return None
    class DummyBeta:
        threads = DummyThreads()
    class DummyClient:
        beta = DummyBeta()
    monkeypatch.setattr("app.ocr.get_ocr_client", lambda: DummyClient())

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
