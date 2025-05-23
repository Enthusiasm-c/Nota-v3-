#!/usr/bin/env python3
"""
Минимальный диагностический скрипт для бота.
Проверяет соединение с Telegram API и запускает простой бот
без дополнительного функционала для проверки работы основных компонентов.
"""

import asyncio
import logging
import sys

# Настройка логирования
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

async def main():
    """Запуск минимальной версии бота для диагностики"""
    try:
        logger.info("Запуск диагностики бота...")
        
        # 1. Импортируем aiogram
        from aiogram import Bot, Dispatcher, F
        from aiogram.types import Message
        from aiogram.fsm.storage.memory import MemoryStorage
        
        # 2. Проверяем доступ к конфигурации
        from app.config import settings
        token = settings.TELEGRAM_BOT_TOKEN
        logger.info(f"Telegram token: {token[:4]}...{token[-4:]}")
        
        # 3. Создаем бота
        bot = Bot(token=token)
        logger.info("Бот создан")
        
        # 4. Проверяем соединение с Telegram API
        bot_info = await bot.get_me()
        logger.info(f"Соединение установлено: @{bot_info.username} (ID: {bot_info.id})")
        
        # 5. Сбрасываем webhook и старые обновления
        logger.info("Сбрасываем webhook...")
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Webhook сброшен успешно")
        
        # 6. Создаем диспетчер
        dp = Dispatcher(storage=MemoryStorage())
        logger.info("Диспетчер создан")
        
        # 7. Регистрируем простой обработчик
        @dp.message(F.text)
        async def handle_text(message: Message):
            logger.info(f"Получено сообщение: {message.text}")
            await message.answer("Бот в отладочном режиме. Сообщение получено.")
        
        logger.info("Обработчик зарегистрирован")
        
        # 8. Запускаем поллинг
        logger.info("Запускаем поллинг...")
        await dp.start_polling(bot)
        
    except Exception as e:
        logger.exception(f"Ошибка при выполнении диагностики: {e}")
        return 1

    return 0

if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        logger.info("Выполнение прервано пользователем")
        sys.exit(0)
    except Exception as e:
        logger.exception(f"Необработанная ошибка: {e}")
        sys.exit(1)