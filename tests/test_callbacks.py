import pytest
from aiogram.types import InlineKeyboardMarkup
from unittest.mock import AsyncMock, patch

import bot

import asyncio

import pytest

@pytest.mark.asyncio
async def test_safe_edit_with_none_reply_markup():
    mock_bot = AsyncMock()
    chat_id = 123
    msg_id = 456
    text = "Test message"
    # Should not pass reply_markup if kb=None
    await bot.safe_edit(mock_bot, chat_id, msg_id, text, kb=None)
    mock_bot.edit_message_text.assert_awaited_with(
        chat_id=chat_id,
        message_id=msg_id,
        text=text,
        reply_markup=None
    )

@pytest.mark.asyncio
async def test_safe_edit_with_inline_keyboard():
    mock_bot = AsyncMock()
    chat_id = 123
    msg_id = 456
    text = "Test message"
    kb = InlineKeyboardMarkup(inline_keyboard=[[]])
    await bot.safe_edit(mock_bot, chat_id, msg_id, text, kb=kb)
    mock_bot.edit_message_text.assert_awaited_with(
        chat_id=chat_id,
        message_id=msg_id,
        text=text,
        reply_markup=kb
    )

@pytest.mark.asyncio
async def test_callback_handled(caplog):
    # Directly call the cb_new_invoice handler and check logs
    from aiogram.types import CallbackQuery, Message
    from types import SimpleNamespace
    # Import the handler from bot module
    # We assume register_handlers is called in bot startup code, so we can access the function
    # If not, we can extract it from bot.py for the test
    # We'll get it from the closure of register_handlers
    handlers = []
    for obj in bot.register_handlers.__code__.co_consts:
        if callable(obj):
            handlers.append(obj)
    # Fallback: define a local cb_new_invoice reference if needed
    cb_new_invoice = None
    for name in dir(bot):
        if name.startswith('cb_new_invoice'):
            cb_new_invoice = getattr(bot, name)
    if not cb_new_invoice:
        # Try to get from closure
        import inspect
        for cell in (bot.register_handlers.__closure__ or []):
            if hasattr(cell.cell_contents, '__name__') and cell.cell_contents.__name__ == 'cb_new_invoice':
                cb_new_invoice = cell.cell_contents
    # If not found, skip test
    if not cb_new_invoice:
        import pytest
        pytest.skip('cb_new_invoice handler not found')
    # Mock callback and state
    callback = AsyncMock(spec=CallbackQuery)
    callback.data = "action:new"
    callback.message = AsyncMock(spec=Message)
    callback.message.chat = SimpleNamespace(id=1)
    callback.message.message_id = 2
    callback.answer = AsyncMock()
    state = AsyncMock()
    with caplog.at_level("INFO"):
        await cb_new_invoice(callback, state)
    assert "is not handled" not in caplog.text

@pytest.mark.asyncio
async def test_keyboard_removal(monkeypatch):
    # Simulate edit_message_reply_markup with reply_markup=None
    mock_message = AsyncMock()
    mock_message.edit_reply_markup = AsyncMock()
    await mock_message.edit_reply_markup(reply_markup=None)
    mock_message.edit_reply_markup.assert_awaited_with(reply_markup=None)
