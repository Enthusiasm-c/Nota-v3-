"""
Optimized utilities for Telegram message editing.
"""

import time
import logging
from typing import Dict, Any, Optional, Union
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup

logger = logging.getLogger(__name__)

# Cache for sent messages to prevent duplicate edits
_message_cache: Dict[str, Dict[str, Any]] = {}

def is_inline_kb(kb):
    """Check if keyboard is an inline keyboard or None."""
    return kb is None or isinstance(kb, InlineKeyboardMarkup)

async def optimized_safe_edit(
    bot: Bot, 
    chat_id: int, 
    msg_id: int, 
    text: str, 
    kb: Optional[Union[InlineKeyboardMarkup, ReplyKeyboardMarkup]] = None,
    **kwargs
) -> bool:
    """
    Optimized message editing with caching and error handling.
    
    Args:
        bot: Bot instance
        chat_id: Chat ID
        msg_id: Message ID to edit
        text: New message text
        kb: Keyboard markup (optional)
        **kwargs: Additional parameters for edit_message_text
        
    Returns:
        bool: True if edit was successful, False otherwise
    """
    if not is_inline_kb(kb):
        kb = None
    
    # Create cache key from message parameters
    cache_key = f"{chat_id}:{msg_id}:{hash(text)}"
    
    # Для тестов пропускаем проверку кеша
    if 'skip_cache_check' in kwargs:
        skip_cache_check = kwargs.pop('skip_cache_check')
    else:
        skip_cache_check = False
    
    # Check cache to avoid duplicate edits
    if not skip_cache_check and cache_key in _message_cache and _message_cache[cache_key].get("timestamp", 0) > time.time() - 5:
        logger.debug("Skipping duplicate edit request (cache hit)")
        return True
    
    # Fix common HTML issues before sending
    if kwargs.get("parse_mode") == "HTML":
        # Fix unclosed tags
        html_tags = ["<b>", "<i>", "<u>", "<s>", "<pre>", "<code>"]
        for tag in html_tags:
            open_tag = tag
            close_tag = tag.replace("<", "</")
            if text.count(open_tag) > text.count(close_tag):
                text += close_tag * (text.count(open_tag) - text.count(close_tag))
    
    try:
        # Single edit attempt with proper parameters
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text=text,
            reply_markup=kb,
            **kwargs
        )
        
        # Update cache
        _message_cache[cache_key] = {
            "sent": True,
            "timestamp": time.time(),
            "msg_id": msg_id
        }
        
        # Clean up old cache entries
        if len(_message_cache) > 1000:
            _cleanup_cache()
            
        return True
    except Exception as e:
        logger.debug(f"Edit failed: {type(e).__name__} - {str(e)}")
        
        try:
            # Fallback to sending new message
            result = await bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=kb,
                **kwargs
            )
            
            # Update cache with new message ID
            _message_cache[cache_key] = {
                "sent": True,
                "timestamp": time.time(),
                "msg_id": result.message_id
            }
            
            logger.debug(f"Sent new message instead: {result.message_id}")
            return True
        except Exception as send_error:
            logger.error(f"Failed to send fallback message: {str(send_error)}")
            return False

def _cleanup_cache():
    """Remove old entries from the message cache."""
    global _message_cache
    
    now = time.time()
    # Keep only messages from the last 10 minutes
    _message_cache = {
        k: v for k, v in _message_cache.items() 
        if v.get("timestamp", 0) > now - 600
    }
    
    logger.debug(f"Cleaned message cache, {len(_message_cache)} entries remaining")