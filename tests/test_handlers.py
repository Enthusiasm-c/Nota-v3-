import pytest
from bot import create_bot_and_dispatcher, register_handlers


@pytest.mark.asyncio
async def test_start_handler(monkeypatch):

    called = {}
    class FakeMsg:
        async def answer(self, text, parse_mode=None):
            called['text'] = text
            called['parse_mode'] = parse_mode

    msg = FakeMsg()
    bot, dp = create_bot_and_dispatcher()
    register_handlers(dp, bot)
    # --- ОТЛАДКА: выводим зарегистрированные хендлеры ---
    print('DEBUG: dp.message.handlers =', dp.message.handlers)
    # Ищем хендлер по команде /start через flags['commands']
    from aiogram.filters.command import CommandStart
    for handler in dp.message.handlers:
        commands = handler.flags.get('commands', [])
        if any(isinstance(cmd, CommandStart) for cmd in commands):
            await handler.callback(msg)
            break
    else:
        pytest.fail('Не найден хендлер команды /start')
    assert 'text' in called, f"No answer() call: {called}"
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
    bot, dp = create_bot_and_dispatcher()
    register_handlers(dp, bot)
    # --- ОТЛАДКА: выводим зарегистрированные хендлеры ---
    print('DEBUG: dp.message.handlers =', dp.message.handlers)
    # Ищем fallback-хендлер по имени callback (text_fallback)
    for handler in dp.message.handlers:
        if getattr(handler.callback, '__name__', '') == 'text_fallback':
            await handler.callback(msg)
            break
    else:
        pytest.fail('Не найден fallback-хендлер по тексту')
    assert 'text' in called, f"No answer() call: {called}"
    assert 'photo' in called['text'].lower()
