import pytest
from unittest.mock import AsyncMock, MagicMock
from app import bot_utils
from aiogram.exceptions import TelegramBadRequest

@pytest.mark.asyncio
async def test_edit_message_text_safe_success():
    bot = AsyncMock()
    bot.edit_message_text = AsyncMock()
    await bot_utils.clear_edit_cache()
    await bot_utils.edit_message_text_safe(bot, 1, 2, "hello", kb=None)
    bot.edit_message_text.assert_awaited_once_with(chat_id=1, message_id=2, text="hello", reply_markup=None, parse_mode="HTML")

@pytest.mark.asyncio
async def test_edit_message_text_safe_not_modified():
    bot = AsyncMock()
    bot.edit_message_text = AsyncMock(side_effect=TelegramBadRequest(method="editMessageText", message="Message is not modified"))
    await bot_utils.clear_edit_cache()
    await bot_utils.edit_message_text_safe(bot, 1, 2, "hello", kb=None)
    bot.edit_message_text.assert_awaited_once()

@pytest.mark.asyncio
async def test_edit_message_text_safe_parse_error_then_success():
    bot = AsyncMock()
    # Первая попытка — ошибка парсинга HTML, вторая — успех
    bot.edit_message_text = AsyncMock(side_effect=[
        TelegramBadRequest(method="editMessageText", message="can't parse entities: tag at byte offset 5"),
        MagicMock()
    ])
    await bot_utils.clear_edit_cache()
    await bot_utils.edit_message_text_safe(bot, 1, 2, "<b>hello</b>", kb=None)
    assert bot.edit_message_text.await_count == 2
    # Вторая попытка без parse_mode
    args, kwargs = bot.edit_message_text.await_args_list[1]
    assert kwargs["parse_mode"] is None

@pytest.mark.asyncio
async def test_edit_message_text_safe_parse_error_all_fail():
    bot = AsyncMock()
    # Все попытки — ошибка
    bot.edit_message_text = AsyncMock(side_effect=[
        TelegramBadRequest(method="editMessageText", message="can't parse entities: tag at byte offset 5"),
        TelegramBadRequest(method="editMessageText", message="Second fail"),
        MagicMock()
    ])
    await bot_utils.clear_edit_cache()
    await bot_utils.edit_message_text_safe(bot, 1, 2, "<b>hello</b>", kb=None)
    assert bot.edit_message_text.await_count == 3

@pytest.mark.asyncio
async def test_edit_message_text_safe_message_not_found():
    bot = AsyncMock()
    bot.edit_message_text = AsyncMock(side_effect=TelegramBadRequest(method="editMessageText", message="message to edit not found"))
    await bot_utils.clear_edit_cache()
    result = await bot_utils.edit_message_text_safe(bot, 1, 2, "hello", kb=None)
    assert result is None

@pytest.mark.asyncio
async def test_edit_message_text_safe_unexpected_error():
    bot = AsyncMock()
    bot.edit_message_text = AsyncMock(side_effect=Exception("unexpected"))
    await bot_utils.clear_edit_cache()
    with pytest.raises(Exception):
        await bot_utils.edit_message_text_safe(bot, 1, 2, "hello", kb=None)

@pytest.mark.asyncio
async def test_edit_message_text_safe_cache():
    bot = AsyncMock()
    bot.edit_message_text = AsyncMock()
    await bot_utils.clear_edit_cache()
    # Первый вызов — редактирование
    await bot_utils.edit_message_text_safe(bot, 1, 2, "hello", kb="kb1")
    # Второй вызов с теми же данными — не должно быть нового вызова
    await bot_utils.edit_message_text_safe(bot, 1, 2, "hello", kb="kb1")
    assert bot.edit_message_text.await_count == 1 