import pytest
from bot import dp
from types import SimpleNamespace

@pytest.mark.asyncio
async def test_start_handler(monkeypatch):
    called = {}
    class FakeMsg:
        async def answer(self, text, parse_mode=None):
            called['text'] = text
            called['parse_mode'] = parse_mode
    msg = FakeMsg()
    # Find the handler registered for CommandStart
    for handler in dp.message.handlers:
        if getattr(handler.filter, 'commands', None) == ['start']:
            await handler.callback(msg)
            break
    assert 'Hi!' in called['text']
    assert called['parse_mode'] is not None

@pytest.mark.asyncio
async def test_text_fallback(monkeypatch):
    called = {}
    class FakeMsg:
        async def answer(self, text, parse_mode=None):
            called['text'] = text
            called['parse_mode'] = parse_mode
    msg = FakeMsg()
    # Find the handler for F.text & ~F.command
    for handler in dp.message.handlers:
        if hasattr(handler.filter, 'text'):
            await handler.callback(msg)
            break
    assert 'photo' in called['text'].lower()
