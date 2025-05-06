"""
Модуль обработчиков для Telegram Bot.
"""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from app.config import settings

# Create router for admin commands
admin_router = Router()

@admin_router.message(Command("toggle_preprocessing"))
async def toggle_preprocessing(message: Message):
    """Toggle image preprocessing for OCR"""
    # Toggle setting
    settings.USE_IMAGE_PREPROCESSING = not settings.USE_IMAGE_PREPROCESSING
    
    # Report new status
    status = "enabled" if settings.USE_IMAGE_PREPROCESSING else "disabled"
    await message.answer(f"Image preprocessing is now {status}. This setting will reset when the bot restarts.")

# Export routers
__all__ = ["admin_router"]