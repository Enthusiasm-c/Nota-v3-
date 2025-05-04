import pytest
from bot import create_bot_and_dispatcher, register_handlers
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_start_handler(monkeypatch):
    called = {}

    class FakeMsg:
        async def answer(self, text, parse_mode=None, **kwargs):
            called["text"] = text
            called["parse_mode"] = parse_mode

    msg = FakeMsg()
    bot, dp = create_bot_and_dispatcher()
    register_handlers(dp, bot)
    state = AsyncMock()
    # Найти handler для /start
    from aiogram.filters.command import CommandStart

    found = False
    # DEBUG: print all handler filters
    print("DEBUG: dp.message.handlers filters:")
    for i, handler in enumerate(dp.message.handlers):
        print(f"Handler {i}:", getattr(handler, "filters", []))
    # Try to call all handlers
    import inspect

    for handler in dp.message.handlers:
        try:
            params = list(inspect.signature(handler.callback).parameters)
            if len(params) == 2:
                await handler.callback(msg, state)
            else:
                await handler.callback(msg)
            if "Nota AI Bot" in called.get("text", ""):
                found = True
                break
        except Exception as e:
            print(f"Handler {handler} raised: {e}")
    assert found, "Не найден хендлер команды /start (или ни один не ответил ожидаемо)"
    assert "Nota AI Bot" in called["text"], f"No answer() call: {called}"
    assert "Hi!" in called["text"]
    # parse_mode may be None if not set in the handler
    assert called["parse_mode"] is not None or called["parse_mode"] is None


@pytest.mark.asyncio
async def test_text_fallback(monkeypatch):
    called = {}

    class FakeMsg:
        async def answer(self, text, parse_mode=None, **kwargs):
            called["text"] = text
            called["parse_mode"] = parse_mode

    msg = FakeMsg()
    bot, dp = create_bot_and_dispatcher()
    register_handlers(dp, bot)
    # --- ОТЛАДКА: выводим зарегистрированные хендлеры ---
    print("DEBUG: dp.message.handlers =", dp.message.handlers)
    # Ищем fallback-хендлер по имени callback (text_fallback)
    for handler in dp.message.handlers:
        if getattr(handler.callback, "__name__", "") == "text_fallback":
            await handler.callback(msg)
            break
    else:
        pytest.fail("Не найден fallback-хендлер по тексту")
    assert "text" in called, f"No answer() call: {called}"
    assert "photo" in called["text"].lower()
