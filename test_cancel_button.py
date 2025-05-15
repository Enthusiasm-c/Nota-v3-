#!/usr/bin/env python3
"""
Тестовый скрипт для проверки исправления кнопки Cancel.
"""
import os
import sys
import random
import asyncio
import logging
from aiogram import Bot
from dotenv import load_dotenv
from datetime import datetime

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    logger.error("BOT_TOKEN not found in environment variables")
    sys.exit(1)

# ID чата для тестирования
CHAT_ID = os.getenv("TEST_CHAT_ID")
if not CHAT_ID:
    logger.error("TEST_CHAT_ID not found in environment variables. Please set it to your Telegram user ID.")
    logger.error("You can get it by sending /start to @userinfobot")
    sys.exit(1)
    
try:
    CHAT_ID = int(CHAT_ID)
except ValueError:
    logger.error(f"TEST_CHAT_ID must be an integer, got {CHAT_ID}")
    sys.exit(1)


async def test_cancel_button():
    """
    Тестирует исправленный обработчик кнопки Cancel.
    """
    bot = Bot(token=BOT_TOKEN)
    
    try:
        logger.info(f"Starting test with chat_id={CHAT_ID}")
        
        # 1. Отправляем приветственное сообщение
        message_id = None
        try:
            msg = await bot.send_message(
                chat_id=CHAT_ID,
                text=f"🧪 Тестирование кнопки Cancel\nStart time: {datetime.now().strftime('%H:%M:%S')}"
            )
            message_id = msg.message_id
            logger.info(f"Sent test message, id={message_id}")
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return
        
        # 2. Ждем немного
        await asyncio.sleep(1)
        
        # 3. Отправляем сообщение с инлайн-клавиатурой, как в боте
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        
        # Создаем тестовую клавиатуру с кнопкой Cancel
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            InlineKeyboardButton(text="Test Button 1", callback_data=f"test:{random.randint(1, 100)}"),
            InlineKeyboardButton(text="Test Button 2", callback_data=f"test:{random.randint(1, 100)}"),
            InlineKeyboardButton(text="❌ Cancel", callback_data="cancel:all")
        )
        
        try:
            msg = await bot.send_message(
                chat_id=CHAT_ID,
                text="Please press the Cancel button below to test fix:",
                reply_markup=keyboard
            )
            logger.info(f"Sent keyboard message, id={msg.message_id}")
        except Exception as e:
            logger.error(f"Error sending keyboard: {e}")
            return
        
        # 4. Выводим инструкции
        logger.info("Test message sent with Cancel button.")
        logger.info("Instructions:")
        logger.info("1. Press the ❌ Cancel button")
        logger.info("2. Observe that the bot quickly responds without hanging")
        logger.info("3. The button should disappear and you should receive confirmation")
        logger.info("4. Check the bot logs for any errors")
        
        # 5. Конец теста
        logger.info("Test setup complete. Manual verification required.")
        
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    logger.info("Starting Cancel button test script")
    asyncio.run(test_cancel_button())
    logger.info("Test script completed")