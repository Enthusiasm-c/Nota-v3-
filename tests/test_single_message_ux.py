from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot import create_bot_and_dispatcher, register_handlers


@pytest.mark.asyncio
async def test_progress_edit_single_msg(monkeypatch):
    """
    Проверяет, что весь UX (progress, отчёт, inline-редактирование) происходит в одном message_id.
    """
    bot, dp = create_bot_and_dispatcher()
    register_handlers(dp, bot)
    # --- Мокаем методы ---
    bot.get_file = AsyncMock(return_value=SimpleNamespace(file_path="x"))
    bot.download_file = AsyncMock(return_value=SimpleNamespace(getvalue=lambda: b"img"))

    # Фейковое ParsedData и match_results
    class FakeParsed:
        supplier = "SUP"
        date = "2025-05-01"
        positions = [
            {"name": "foo", "qty": 1, "unit": "kg", "status": "unknown"},
            {"name": "bar", "qty": 2, "unit": "kg", "status": "ok"},
        ]

    monkeypatch.setattr("app.ocr.call_openai_ocr", lambda _: FakeParsed())
    monkeypatch.setattr(
        "app.matcher.match_positions", lambda pos, prod=None: FakeParsed().positions
    )
    # --- Мокаем answer/edit_message_text ---
    calls = []

    async def fake_answer(text, **kwargs):
        calls.append(("answer", text, kwargs))
        msg = MagicMock()
        msg.message_id = 111
        msg.chat = SimpleNamespace(id=1)
        return msg

    async def fake_edit_message_text(chat_id, message_id, text, **kwargs):
        calls.append(("edit", message_id, text, kwargs))

    bot.edit_message_text = fake_edit_message_text
    # --- Сообщение с фото ---
    fake_msg = MagicMock()
    fake_msg.photo = [SimpleNamespace(file_id="abc")]
    fake_msg.answer = fake_answer
    fake_msg.from_user = SimpleNamespace(id=1)
    fake_msg.message_id = 10
    # --- Запуск ---
    photo_handler = None
    for handler in dp.message.handlers:
        if getattr(handler.callback, "__name__", "") == "photo_handler":
            photo_handler = handler.callback
            break
    assert photo_handler is not None
    await photo_handler(fake_msg)
    # Проверяем, что answer был только 1 раз (progress)
    assert sum(1 for c in calls if c[0] == "answer") == 1
    # Проверяем, что все edit_message_text идут по одному message_id
    edit_ids = [c[1] for c in calls if c[0] == "edit"]
    assert len(set(edit_ids)) == 1, f"edit_message_text по разным message_id: {edit_ids}"
