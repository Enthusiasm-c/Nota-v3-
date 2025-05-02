import pytest
from bot import photo_handler
from app.models import ParsedData, Position

@pytest.mark.asyncio
async def test_photo_ok(monkeypatch, fake_msg):
    monkeypatch.setattr("app.ocr.call_openai_ocr", lambda _: ParsedData(
        supplier="S", date=None,
        positions=[Position(name="A", qty=1, unit="kg")]
    ))
    monkeypatch.setattr("app.matcher.match_positions", lambda pos, prod=None: [])
    monkeypatch.setattr("bot.build_report", lambda *_: "OK")
    await photo_handler(fake_msg)
    fake_msg.answer.assert_called_once_with("OK", parse_mode=None)

@pytest.mark.asyncio
async def test_photo_error(monkeypatch, fake_msg):
    monkeypatch.setattr("app.ocr.call_openai_ocr", lambda _: (_ for _ in ()).throw(RuntimeError))
    await photo_handler(fake_msg)
    fake_msg.answer.assert_called_once()
    _, kwargs = fake_msg.answer.call_args
    assert kwargs.get("parse_mode") is None

from bot import photo_handler
from app.models import ParsedData, Position

@pytest.mark.asyncio
async def test_photo_ok(monkeypatch, fake_msg):
    monkeypatch.setattr("app.ocr.call_openai_ocr", lambda _: ParsedData(
        supplier="S", date=None,
        positions=[Position(name="A", qty=1, unit="kg")]
    ))
    monkeypatch.setattr("app.matcher.match_positions", lambda pos, prod=None: [])
    monkeypatch.setattr("bot.build_report", lambda *_: "OK")
    await photo_handler(fake_msg)
    fake_msg.answer.assert_called_once_with("OK", parse_mode=None)

@pytest.mark.asyncio
async def test_photo_error(monkeypatch, fake_msg):
    monkeypatch.setattr("app.ocr.call_openai_ocr", lambda _: (_ for _ in ()).throw(RuntimeError))
    await photo_handler(fake_msg)
    fake_msg.answer.assert_called_once()
    _, kwargs = fake_msg.answer.call_args
    assert kwargs.get("parse_mode") is None