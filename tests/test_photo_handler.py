import pytest
from unittest.mock import AsyncMock
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
    fake_msg.chat = SimpleNamespace(id=123)  # Нужно для edit_message_text
    # --- Патчим методы get_file и download_file у нужного экземпляра бота ---
    bot.get_file = AsyncMock(
        return_value=type('File', (), {'file_path': 'x'})()
    )
    bot.download_file = AsyncMock(
        return_value=type('Obj', (), {'getvalue': lambda self: b'img'})()
    )
    # --- Мокаем edit_message_text, чтобы не было BadRequest ---
    bot.edit_message_text = AsyncMock(return_value=None)
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
        lambda pos, prod=None: [
            {"name": "A", "qty": 1, "unit": "kg", "price": 10, "status": "ok"},
            {"name": "B", "qty": 2, "unit": "l", "price": 20, "status": "ok"}
        ]
    )
    def fake_build_report(*args, **kwargs):
        return "OK"
    monkeypatch.setattr("app.formatter.build_report", fake_build_report)

    # Patch ParsedData to always have non-empty positions
    class FakeParsedData:
        positions = [
            {"name": "A", "qty": 1, "unit": "kg"},
            {"name": "B", "qty": 2, "unit": "l"}
        ]
        supplier = "Test"
        date = "2024-01-01"
    monkeypatch.setattr("app.models.ParsedData", FakeParsedData)
    # Mock OCR so it never fails and always returns valid data
    monkeypatch.setattr(
        "app.ocr.call_openai_ocr",
        lambda *a, **kw: type("ParsedData", (), {
            "positions": [
                {"name": "A", "qty": 1, "unit": "kg"},
                {"name": "B", "qty": 2, "unit": "l"}
            ],
            "supplier": "Test",
            "date": "2024-01-01"
        })()
    )

    await photo_handler(fake_msg)
    assert fake_msg.answer.call_count >= 1
    assert bot.edit_message_text.call_count >= 1
    edit_calls = bot.edit_message_text.call_args_list
    found = False
    for call in edit_calls:
        msg = call[1].get('text')
        if msg and "Supplier:" in msg and "Invoice date:" in msg and "A" in msg and "B" in msg:
            found = True
            break
    assert found, f"Expected formatted report in edit_message_text, got: {[c[1].get('text') for c in edit_calls]}"


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
    # --- Мокаем edit_message_text, чтобы не было BadRequest ---
    bot.edit_message_text = AsyncMock(return_value=None)
    # --- Мокаем OCR с выбрасыванием ошибки ---
    monkeypatch.setattr(
        "app.ocr.call_openai_ocr",
        lambda _: (_ for _ in ()).throw(Exception("fail"))
    )
    await photo_handler(fake_msg)
    assert fake_msg.answer.call_count >= 1
    calls = fake_msg.answer.call_args_list
    found = False
    for call in calls:
        msg = call[0][0]
        if isinstance(msg, str) and msg.startswith("⚠️ OCR failed"):
            found = True
            break
    assert found, f"Expected OCR error in answer, got: {[c[0][0] for c in calls]}"

# --- Добавляем перевод строки в конец файла ---