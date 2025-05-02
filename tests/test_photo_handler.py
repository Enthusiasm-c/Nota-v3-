import pytest
from bot import create_bot_and_dispatcher, register_handlers
from app.models import ParsedData, Position


def get_photo_handler(dp):
    # Ищем хендлер по имени callback (photo_handler)
    for handler in dp.message.handlers:
        if getattr(handler.callback, '__name__', '') == 'photo_handler':
            return handler.callback
    return None


@pytest.mark.asyncio
async def test_photo_ok(monkeypatch, fake_msg):
    bot, dp = create_bot_and_dispatcher()
    register_handlers(dp, bot)
    photo_handler = get_photo_handler(dp)
    assert photo_handler is not None, "photo_handler not found in dispatcher"
    # --- Добавляем недостающие атрибуты в fake_msg ---
    from types import SimpleNamespace
    fake_msg.from_user = SimpleNamespace(id=42)  # Любой id пользователя
    fake_msg.message_id = 1  # Любой message_id
    # --- Патчим методы get_file и download_file у нужного экземпляра бота ---
    from unittest.mock import AsyncMock
    bot.get_file = AsyncMock(
        return_value=type('File', (), {'file_path': 'x'})()
    )
    bot.download_file = AsyncMock(
        return_value=type('Obj', (), {'getvalue': lambda self: b'img'})()
    )
    # --- Мокаем OCR и остальные функции ---
    monkeypatch.setattr(
        "app.ocr.call_openai_ocr",
        lambda _: ParsedData(
            supplier="S", date=None,
            positions=[Position(name="A", qty=1, unit="kg")]
        )
    )
    monkeypatch.setattr(
        "app.matcher.match_positions",
        lambda pos, prod=None: []
    )
    monkeypatch.setattr(
        "bot.build_report",
        lambda *_: "OK"
    )
    await photo_handler(fake_msg)
    fake_msg.answer.assert_called_once_with(
        "OK",
        parse_mode=None
    )


@pytest.mark.asyncio
async def test_photo_error(monkeypatch, fake_msg):
    bot, dp = create_bot_and_dispatcher()
    register_handlers(dp, bot)
    photo_handler = get_photo_handler(dp)
    assert photo_handler is not None, "photo_handler not found in dispatcher"
    # --- Добавляем недостающие атрибуты в fake_msg ---
    from types import SimpleNamespace
    fake_msg.from_user = SimpleNamespace(id=42)
    fake_msg.message_id = 1
    # --- Патчим методы get_file и download_file у нужного экземпляра бота ---
    from unittest.mock import AsyncMock
    bot.get_file = AsyncMock(
        return_value=type('File', (), {'file_path': 'x'})()
    )
    bot.download_file = AsyncMock(
        return_value=type('Obj', (), {'getvalue': lambda self: b'img'})()
    )
    # --- Мокаем OCR с выбрасыванием ошибки ---
    monkeypatch.setattr(
        "app.ocr.call_openai_ocr",
        lambda _: (_ for _ in ()).throw(Exception("fail"))
    )
    await photo_handler(fake_msg)
    fake_msg.answer.assert_called_once()
    _, kwargs = fake_msg.answer.call_args
    # --- Удаляем дублирующуюся проверку на 'OCR failed' ---
    assert "OCR failed" in fake_msg.answer.call_args[0][0]
    # --- Разбиваем длинную строку на две ---
    assert kwargs.get("parse_mode") is None

# --- Добавляем перевод строки в конец файла ---