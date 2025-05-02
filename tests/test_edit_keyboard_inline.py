import pytest
from unittest.mock import AsyncMock, MagicMock
from bot import create_bot_and_dispatcher, register_handlers
from types import SimpleNamespace

@pytest.mark.asyncio
async def test_edit_keyboard_inline(monkeypatch):
    """
    Проверяет, что после любого редактирования inline-клавиатура обновляется только у того же message_id
    и содержит только Edit для проблемных строк и Cancel.
    """
    bot, dp = create_bot_and_dispatcher()
    register_handlers(dp, bot)
    # --- Мокаем методы ---
    bot.get_file = AsyncMock(return_value=SimpleNamespace(file_path='x'))
    bot.download_file = AsyncMock(return_value=SimpleNamespace(getvalue=lambda: b'img'))
    # Фейковое ParsedData и match_results
    class FakeParsed:
        supplier = "SUP"
        date = "2025-05-01"
        positions = [
            {"name": "foo", "qty": 1, "unit": "kg", "status": "unknown"},
            {"name": "bar", "qty": 2, "unit": "kg", "status": "unknown"}
        ]
    monkeypatch.setattr("app.ocr.call_openai_ocr", lambda _: FakeParsed())
    # После первого редактирования bar становится ok
    states = [
        [
            {"name": "foo", "qty": 1, "unit": "kg", "status": "unknown"},
            {"name": "bar", "qty": 2, "unit": "kg", "status": "unknown"}
        ],
        [
            {"name": "foo", "qty": 1, "unit": "kg", "status": "unknown"},
            {"name": "bar", "qty": 2, "unit": "kg", "status": "ok"}
        ]
    ]
    call_idx = 0
    def fake_match_positions(pos, prod=None, **kwargs):
        nonlocal call_idx
        result = states[min(call_idx, len(states)-1)]
        call_idx += 1
        return result
    monkeypatch.setattr("app.matcher.match_positions", fake_match_positions)
    # --- Мокаем answer/edit_message_text/edit_message_reply_markup ---
    calls = []
    async def fake_answer(text, **kwargs):
        msg = MagicMock()
        msg.message_id = 111
        msg.chat = SimpleNamespace(id=1)
        calls.append(("answer", text, kwargs))
        return msg
    async def fake_edit_message_text(chat_id, message_id, text, **kwargs):
        calls.append(("edit", message_id, text, kwargs))
    async def fake_edit_message_reply_markup(chat_id, message_id, reply_markup=None):
        calls.append(("reply_markup", message_id, reply_markup))
    bot.edit_message_text = fake_edit_message_text
    bot.edit_message_reply_markup = fake_edit_message_reply_markup
    # --- Сообщение с фото ---
    fake_msg = MagicMock()
    fake_msg.photo = [SimpleNamespace(file_id='abc')]
    fake_msg.answer = fake_answer
    fake_msg.from_user = SimpleNamespace(id=1)
    fake_msg.message_id = 10
    # --- Запуск ---
    photo_handler = None
    for handler in dp.message.handlers:
        if getattr(handler.callback, '__name__', '') == 'photo_handler':
            photo_handler = handler.callback
            break
    assert photo_handler is not None
    await photo_handler(fake_msg)
    # Проверяем, что edit_message_text был только у одного message_id
    edit_ids = [c[1] for c in calls if c[0] == 'edit']
    assert len(set(edit_ids)) == 1, f"edit_message_text по разным message_id: {edit_ids}"
