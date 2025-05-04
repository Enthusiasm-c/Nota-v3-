import logging
from aiogram.exceptions import TelegramBadRequest
from aiogram.enums import ParseMode
from typing import Any, Dict
import asyncio

# In-memory cache for message edits (can be replaced with Redis)
_edit_cache: Dict[str, Dict[str, Any]] = {}

logger = logging.getLogger("nota.bot_utils")


def serialize_kb(kb) -> str:
    """Serialize keyboard for cache comparison. Simple str() for most cases."""
    return str(kb)


async def edit_message_text_safe(bot, chat_id, msg_id, text, kb):
    cache_key = f"msg:{chat_id}:{msg_id}"
    cached = _edit_cache.get(cache_key)
    kb_serialized = serialize_kb(kb)
    # 1. Не редактируем, если текст и клавиатура неизменны
    if cached and cached.get("text") == text and cached.get("kb") == kb_serialized:
        return

    # 2. Гарантируем длину ≤ 4096
    if len(text) > 4096:
        text = text[:4090] + "…"

    try:
        await bot.edit_message_text(
        parse_mode="MarkdownV2",
            chat_id=chat_id,
            message_id=msg_id,
            text=text,
            reply_markup=kb,
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        # 3. Кэшируем успешный результат
        _edit_cache[cache_key] = {"text": text, "kb": kb_serialized}
    except TelegramBadRequest as e:
        if "Message is not modified" in str(e):
            logger.debug("Skip edit: not modified")
        elif "can't parse entities" in str(e):
            logger.error("MD parse error: %s", e.message)
        else:
            logger.error("Unexpected BadRequest: %s", e.message)
        logger.warning("Edit failed: %s", e.message)
        # Не пробрасываем ошибку дальше, чтобы не дублировать в логах
    except Exception as e:
        logger.error("Unexpected exception in edit_message_text_safe: %s", e, exc_info=True)
        raise

# Для тестов и замены на Redis
async def clear_edit_cache():
    _edit_cache.clear()
