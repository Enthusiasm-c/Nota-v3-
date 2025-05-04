import pytest
import json
import os
from app.ocr import call_openai_ocr, ParsedData


class DummyMsg:
    tool_calls = [
        type(
            "F",
            (),
            {
                "function": type(
                    "A", (), {"arguments": '[{"name":"Kacang","qty":1,"unit":"gr"}]'}
                )()
            },
        )()
    ]


class DummyRsp:
    def __init__(self):
        self.choices = [type("msg", (), {"message": DummyMsg()})()]


@pytest.mark.asyncio
async def test_top_level_list(monkeypatch):
    # Patch app.config.ocr_client to a dummy so get_ocr_client() returns not None
    import app.config

    class DummyComp:
        def create(self, **kw):
            return DummyRsp()

    class DummyChat:
        completions = DummyComp()

    class DummyOpenAI:
        def __init__(self, api_key=None):
            self.chat = DummyChat()

    app.config.ocr_client = DummyOpenAI()

    # Patch openai and settings
    monkeypatch.setattr(
        "app.ocr.settings",
        type("S", (), {"OPENAI_API_KEY": "k", "OPENAI_MODEL": "m"})(),
    )

    class DummyComp:
        def create(self, **kw):
            return DummyRsp()

    class DummyChat:
        completions = DummyComp()

    class DummyOpenAI:
        def __init__(self, api_key=None):
            self.chat = DummyChat()

    class DummyOpenAIModule:
        OpenAI = DummyOpenAI

    monkeypatch.setattr("app.ocr.openai", DummyOpenAIModule())

    class DummyUuid4:
        hex = "abc12345"

    class DummyUuid:
        @staticmethod
        def uuid4():
            return DummyUuid4()

    monkeypatch.setattr("app.ocr.uuid", DummyUuid)
    monkeypatch.setattr("app.ocr.time", type("T", (), {"time": lambda *a, **kw: 0})())
    monkeypatch.setattr(
        "app.ocr.base64", type("B", (), {"b64encode": lambda *a, **kw: b"xx"})()
    )

    # Run
    res = call_openai_ocr(b"123")
    assert isinstance(res, ParsedData)
    assert len(res.positions) == 1
    assert res.positions[0].name == "Kacang"
    assert res.positions[0].qty == 1
    assert res.positions[0].unit == "gr"
