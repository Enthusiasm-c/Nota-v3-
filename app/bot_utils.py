import logging
import re
from typing import Any, Dict

from aiogram.exceptions import TelegramBadRequest

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

    logger.debug("OUT >>> %s", text[:200])
    try:
        # Первая попытка: с HTML-форматированием
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text=text,
            reply_markup=kb,
            parse_mode="HTML",
        )
        # 3. Кэшируем успешный результат
        _edit_cache[cache_key] = {"text": text, "kb": kb_serialized}
    except TelegramBadRequest as e:
        error_msg = str(e)
        if "Message is not modified" in error_msg:
            logger.debug("Skip edit: not modified")
        elif "message to edit not found" in error_msg:
            logger.info(f"Message {msg_id} not found, skipping edit")
            return  # Просто выходим, не пытаясь продолжать редактирование
        elif "can't parse entities" in error_msg:
            logger.warning(
                "HTML parse error in edit_message_text_safe: %s - in chat_id=%s, msg_id=%s",
                error_msg,
                chat_id,
                msg_id,
            )

            # Найдем проблемную часть HTML
            entity_pos_match = re.search(
                r"can't parse entities: (.*) at byte offset (\d+)", error_msg
            )
            if entity_pos_match:
                error_type = entity_pos_match.group(1)
                offset = int(entity_pos_match.group(2))
                preview = text[max(0, offset - 30) : min(len(text), offset + 30)]
                logger.error(
                    f"Entity parse error: {error_type} at offset {offset}, preview: {preview}"
                )

            try:
                # Вторая попытка: без форматирования
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg_id,
                    text=text,
                    reply_markup=kb,
                    parse_mode=None,  # Отключаем форматирование
                )
                logger.info("Message edited without HTML formatting")
                _edit_cache[cache_key] = {"text": text, "kb": kb_serialized}
                return
            except TelegramBadRequest as e2:
                logger.warning("Second attempt failed: %s", e2.message)

                try:
                    # Третья попытка: очищаем текст от HTML-тегов
                    clean_text = re.sub(r"<[^>]+>", "", text)
                    await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=msg_id,
                        text=clean_text,
                        reply_markup=kb,
                        parse_mode=None,
                    )
                    logger.info("Message edited with stripped HTML tags")
                    _edit_cache[cache_key] = {"text": clean_text, "kb": kb_serialized}
                except Exception as e3:
                    logger.error("All attempts to edit message failed: %s", e3)
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
