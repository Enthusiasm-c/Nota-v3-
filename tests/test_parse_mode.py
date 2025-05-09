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

    # Проверяем отсутствие "сырых" HTML-тегов или их обрывков в отправляемом тексте
    sent_args = bot.edit_message_text.await_args.kwargs
    sent_text = sent_args['text']
    # Не должно быть обрывков вида 'bSupplier', '/b', '&lt;b&gt;', '&lt;/b&gt;', '&lt;br&gt;'
    assert not any(
        pattern in sent_text
        for pattern in [
            "bSupplier", "/b", "&lt;b&gt;", "&lt;/b&gt;", "&lt;br&gt;"
        ]
    ), f"Message contains unformatted HTML: {sent_text}"
    # Должны остаться корректные HTML-теги
    assert "<b>" in sent_text and "</b>" in sent_text and "<br>" in sent_text
