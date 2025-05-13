#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тестовый бот для проверки работы без предобработки изображений
"""

import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.client.default import DefaultBotProperties

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Получение токена из .env файла
import os
from dotenv import load_dotenv
load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("Не задан TELEGRAM_BOT_TOKEN в файле .env")

# Создание бота и диспетчера
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Обработчик команды /start
@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Обработчик команды /start"""
    user_data = await state.get_data()
    lang = user_data.get("lang", "ru")  # Русский язык по умолчанию
    
    # Сохраняем язык пользователя
    await state.update_data(lang=lang)
    
    # Отправляем приветственное сообщение
    await message.answer(
        "👋 Привет! Я бот для OCR-распознавания инвойсов.\n\n"
        "Просто отправь мне фото накладной, и я распознаю данные.\n\n"
        "❗️ <b>Важная информация:</b> Модуль предобработки изображений был удалён из проекта. "
        "Теперь я работаю с исходными изображениями."
    )

# Обработчик фотографий
@dp.message(F.photo)
async def handle_photo(message: Message, state: FSMContext):
    """Обработчик входящих фотографий"""
    # Отправляем сообщение о получении изображения
    await message.answer("🖼 Получил ваше изображение!")
    
    # Имитируем обработку изображения
    processing_msg = await message.answer("⏳ Обрабатываю изображение... Это может занять некоторое время.")
    
    # Имитируем задержку обработки
    await asyncio.sleep(2)
    
    # Информируем пользователя об отсутствии предобработки
    await processing_msg.delete()
    await message.answer(
        "ℹ️ <b>Информация о работе:</b>\n\n"
        "✅ Функциональность предобработки изображений (app.imgprep) была удалена из проекта.\n"
        "✅ Теперь изображения передаются в OCR без предварительной обработки.\n"
        "✅ Это позволяет уменьшить количество зависимостей и упростить процесс развертывания.\n\n"
        "В реальном режиме работы здесь бы происходило распознавание данных с использованием OCR."
    )

# Обработчик текстовых сообщений
@dp.message(F.text)
async def handle_text(message: Message, state: FSMContext):
    """Обработчик текстовых сообщений"""
    # Отвечаем на текстовое сообщение
    await message.answer(
        "📝 Я работаю с фотографиями накладных. Пожалуйста, отправьте фото для OCR-распознавания.\n\n"
        "Используйте команду /start для получения инструкций."
    )

async def main():
    """Запуск бота"""
    # Настройка диспетчера и запуск поллинга
    try:
        logger.info("Бот запущен")
        # Удаляем все предыдущие обновления и запускаем бота
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        logger.info("Бот остановлен")
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен") 