import asyncio, types
from app import ocr
from bot import photo_handler
import pytest

@pytest.mark.asyncio
async def test_handler_runs_to_thread(monkeypatch):
    called = False
    async def fake_download(*_): return types.SimpleNamespace(getvalue=lambda: b"img")
    async def fake_file(*_): return types.SimpleNamespace(file_path="x")
    monkeypatch.setattr("bot.bot.get_file", fake_file)
    monkeypatch.setattr("bot.bot.download_file", fake_download)
    monkeypatch.setattr("app.formatter.build_report", lambda *_: "OK")

    def fake_ocr(_):
        nonlocal called
        called = True
        return ocr.ParsedData(supplier="X", date="2025-05-02", positions=[])
    monkeypatch.setattr("app.ocr.call_openai_ocr", fake_ocr)
    msg = types.SimpleNamespace(photo=[types.SimpleNamespace(file_id="id")], answer=lambda *_ , **__: None)
    await photo_handler(msg)
    assert called
