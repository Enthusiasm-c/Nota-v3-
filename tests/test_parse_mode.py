import pytest
from unittest.mock import AsyncMock
from app.bot_utils import edit_message_text_safe

@pytest.mark.asyncio
async def test_edit_message_text_safe_parse_mode_html():
    bot = AsyncMock()
    chat_id = 123
    msg_id = 456
    text = '<b>Supplier:</b> Guna<br>'
    kb = None

    await edit_message_text_safe(bot, chat_id, msg_id, text, kb)
    
    # Проверяем, что edit_message_text вызван с parse_mode='HTML'
    bot.edit_message_text.assert_awaited_with(
        chat_id=chat_id,
        message_id=msg_id,
        text=text,
        reply_markup=kb,
        parse_mode='HTML',
    )
