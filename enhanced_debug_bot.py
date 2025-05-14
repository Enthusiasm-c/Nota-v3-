#!/usr/bin/env python3
"""
Расширенный отладочный бот для изоляции проблемы с зависанием кнопок.
Специально создан для тщательного отслеживания каждого шага обработки callback-запросов.
"""
import os
import sys
import asyncio
import logging
import traceback
import time
import json
from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters.command import Command
from aiogram.types import (
    Message, 
    CallbackQuery, 
    InlineKeyboardMarkup, 
    InlineKeyboardButton,
    BotCommand
)
from dotenv import load_dotenv

# Настройка расширенного логирования
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("enhanced_debug_bot.log")
    ]
)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN не найден в переменных окружения")
    sys.exit(1)

# Определение состояний FSM
class DebugStates(StatesGroup):
    main_menu = State()
    waiting = State()
    processing = State()
    completed = State()

# Middleware для трассировки всех событий
class TracingMiddleware:
    async def __call__(self, handler, event, data):
        start_time = time.time()
        event_type = type(event).__name__
        
        # Генерируем уникальный trace_id
        trace_id = f"TRACE-{int(time.time() * 1000)}"
        
        # Логируем входящее событие
        event_data = {}
        if isinstance(event, CallbackQuery):
            event_data["callback_data"] = event.data
            event_data["message_id"] = event.message.message_id if event.message else None
            event_data["user_id"] = event.from_user.id if event.from_user else None
        elif isinstance(event, Message):
            event_data["message_text"] = event.text
            event_data["message_id"] = event.message_id
            event_data["user_id"] = event.from_user.id if event.from_user else None
        
        logger.debug(f"[{trace_id}] START {event_type}: {json.dumps(event_data)}")
        
        # Добавляем trace_id в контекст
        data["trace_id"] = trace_id
        
        # Обрабатываем событие с тайм-аутом для выявления зависаний
        try:
            # Используем wait_for с таймаутом для выявления потенциальных блокировок
            result = await asyncio.wait_for(
                handler(event, data),
                timeout=10.0  # Устанавливаем таймаут в 10 секунд
            )
            
            # Логируем успешное завершение
            elapsed = time.time() - start_time
            logger.debug(f"[{trace_id}] COMPLETE {event_type}: время выполнения {elapsed:.3f}s")
            return result
        except asyncio.TimeoutError:
            # Логируем случай превышения таймаута (потенциальное зависание)
            logger.error(f"[{trace_id}] TIMEOUT {event_type}: превышен таймаут 10s")
            # Возвращаем None, чтобы предотвратить дальнейшие ошибки
            return None
        except Exception as e:
            # Логируем любые другие ошибки
            elapsed = time.time() - start_time
            logger.error(f"[{trace_id}] ERROR {event_type}: {type(e).__name__}: {str(e)}, время {elapsed:.3f}s")
            logger.error(f"[{trace_id}] {traceback.format_exc()}")
            # Пробрасываем ошибку дальше
            raise

# Создаем бота и диспетчер
bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Регистрируем middleware для трассировки
dp.message.middleware(TracingMiddleware())
dp.callback_query.middleware(TracingMiddleware())

# Основной роутер
main_router = Router(name="main_router")

# Дополнительный роутер для тестирования приоритетов
test_router = Router(name="test_router")

# Обработчик команды /start
@main_router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext, trace_id: str):
    """Обработчик команды /start с подробным логированием"""
    logger.info(f"[{trace_id}] Пользователь {message.from_user.id} запустил бота")
    
    # Сбрасываем состояние и устанавливаем начальное
    await state.clear()
    await state.set_state(DebugStates.main_menu)
    
    # Создаем клавиатуру с тестовыми кнопками
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Тестовая кнопка 1", callback_data="test:1")],
        [InlineKeyboardButton(text="Тестовая кнопка 2", callback_data="test:2")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel:all")]
    ])
    
    # Отправляем сообщение с кнопками
    await message.answer(
        f"<b>ENHANCED DEBUG BOT</b>\n\n"
        f"Трассировка: <code>{trace_id}</code>\n\n"
        f"Нажмите любую кнопку для проверки обработки callback.\n"
        f"Нажмите кнопку <b>Отмена</b> для тестирования исправления.",
        reply_markup=keyboard
    )

# Обработчик команды /test
@main_router.message(Command("test"))
async def cmd_test(message: Message, trace_id: str):
    """Отправляет тестовое сообщение с кнопкой отмены"""
    logger.info(f"[{trace_id}] Пользователь {message.from_user.id} запросил тестовые кнопки")
    
    # Создаем клавиатуру с кнопкой отмены
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Кнопка действия", callback_data="action:test")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel:all")]
    ])
    
    await message.answer(
        f"Тестовое сообщение с кнопкой отмены.\n"
        f"Трассировка: <code>{trace_id}</code>\n\n"
        f"Нажмите Отмена для тестирования обработчика.",
        reply_markup=keyboard
    )

# Команда для тестирования производительности
@main_router.message(Command("load"))
async def cmd_load(message: Message, trace_id: str):
    """Тестирует производительность бота при большой нагрузке"""
    logger.info(f"[{trace_id}] Пользователь {message.from_user.id} запустил тест нагрузки")
    
    # Сообщаем о начале теста
    status_msg = await message.answer("⏳ Запуск теста нагрузки...")
    
    # Эмулируем тяжелые вычисления
    start_time = time.time()
    
    # Эмуляция неблокирующей нагрузки с помощью asyncio.sleep
    for i in range(5):
        await status_msg.edit_text(f"⏳ Выполнение тяжелой задачи... {i+1}/5")
        await asyncio.sleep(0.5)  # Неблокирующая задержка
    
    elapsed = time.time() - start_time
    
    # Создаем клавиатуру с кнопкой отмены для теста
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel:all")]
    ])
    
    # Отправляем результат
    await status_msg.edit_text(
        f"✅ Тест нагрузки завершен за {elapsed:.2f}s\n\n"
        f"Трассировка: <code>{trace_id}</code>\n\n"
        f"Нажмите кнопку отмены для проверки обработчика после нагрузки.",
        reply_markup=keyboard
    )

# Обработчик кнопки отмены - полностью переработанная версия
@dp.callback_query(F.data == "cancel:all")
async def handle_cancel_all(call: CallbackQuery, state: FSMContext, trace_id: str):
    """Оптимизированный обработчик кнопки отмены для отладки"""
    logger.info(f"[{trace_id}] CANCEL: Начало обработки cancel:all callback")
    
    # Шаг 1: Немедленно отвечаем на callback
    try:
        await call.answer("Отмена", cache_time=1)
        logger.info(f"[{trace_id}] CANCEL STEP 1: Callback answered successfully")
    except Exception as e:
        logger.error(f"[{trace_id}] CANCEL STEP 1 ERROR: {str(e)}")
    
    # Шаг 2: Диагностика текущего состояния
    try:
        current_state = await state.get_state()
        logger.info(f"[{trace_id}] CANCEL STEP 2: Текущее состояние: {current_state}")
    except Exception as e:
        logger.error(f"[{trace_id}] CANCEL STEP 2 ERROR: {str(e)}")
        current_state = "unknown"
    
    # Шаг 3: Сбрасываем состояние
    try:
        await state.clear()
        logger.info(f"[{trace_id}] CANCEL STEP 3: Состояние очищено")
    except Exception as e:
        logger.error(f"[{trace_id}] CANCEL STEP 3 ERROR: {str(e)}")
    
    # Шаг 4: Устанавливаем новое состояние
    try:
        await state.set_state(DebugStates.main_menu)
        logger.info(f"[{trace_id}] CANCEL STEP 4: Установлено состояние main_menu")
    except Exception as e:
        logger.error(f"[{trace_id}] CANCEL STEP 4 ERROR: {str(e)}")
    
    # Шаг 5: Удаляем клавиатуру
    try:
        await call.message.edit_reply_markup(reply_markup=None)
        logger.info(f"[{trace_id}] CANCEL STEP 5: Клавиатура удалена")
    except Exception as e:
        logger.error(f"[{trace_id}] CANCEL STEP 5 ERROR: {str(e)}")
    
    # Шаг 6: Отправляем подтверждение
    try:
        result = await bot.send_message(
            chat_id=call.message.chat.id,
            text=f"✅ Операция отменена!\n\nTraceID: {trace_id}",
            parse_mode=ParseMode.HTML
        )
        logger.info(f"[{trace_id}] CANCEL STEP 6: Сообщение отправлено, ID: {result.message_id}")
    except Exception as e:
        logger.error(f"[{trace_id}] CANCEL STEP 6 ERROR: {str(e)}")
        try:
            # Резервный метод с минимальным форматированием
            await bot.send_message(
                chat_id=call.message.chat.id,
                text="Операция отменена.",
                parse_mode=None
            )
        except Exception as e2:
            logger.error(f"[{trace_id}] CANCEL STEP 6 FALLBACK ERROR: {str(e2)}")
    
    logger.info(f"[{trace_id}] CANCEL: Обработка завершена")

# Обработчик тестовых callback-запросов
@test_router.callback_query(F.data.startswith("test:"))
async def test_callback_handler(call: CallbackQuery, trace_id: str):
    """Обработчик тестовых callback-запросов"""
    logger.info(f"[{trace_id}] Получен тестовый callback: {call.data}")
    
    # Отвечаем на callback
    await call.answer(f"Вы нажали: {call.data}")
    
    # Отправляем сообщение с информацией о callback
    await call.message.answer(
        f"Callback <code>{call.data}</code> обработан успешно!\n\n"
        f"Трассировка: <code>{trace_id}</code>"
    )

# Обработчик действий
@test_router.callback_query(F.data.startswith("action:"))
async def action_callback_handler(call: CallbackQuery, state: FSMContext, trace_id: str):
    """Обработчик callback-запросов действий"""
    logger.info(f"[{trace_id}] Получен callback действия: {call.data}")
    
    # Отвечаем на callback
    await call.answer("Обработка...")
    
    # Переходим в состояние обработки
    await state.set_state(DebugStates.processing)
    
    # Имитируем обработку
    status_msg = await call.message.answer("⏳ Обработка запроса...")
    
    # Имитируем работу неблокирующим способом
    for i in range(3):
        await asyncio.sleep(0.5)
        await status_msg.edit_text(f"⏳ Обработка запроса... {i+1}/3")
    
    # Завершаем обработку
    await state.set_state(DebugStates.completed)
    
    # Отправляем результат
    await status_msg.edit_text(
        f"✅ Действие <code>{call.data}</code> выполнено!\n\n"
        f"Трассировка: <code>{trace_id}</code>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel:all")]
        ])
    )

# Обработчик всех остальных callback-запросов
@dp.callback_query()
async def default_callback_handler(call: CallbackQuery, trace_id: str):
    """Обработчик по умолчанию для всех неопознанных callback-запросов"""
    logger.info(f"[{trace_id}] Получен неопознанный callback: {call.data}")
    await call.answer(f"Получен callback: {call.data}")
    await call.message.answer(f"Неизвестный callback: {call.data}")

# Команда для отображения справки
@main_router.message(Command("help"))
async def cmd_help(message: Message):
    """Показывает справку по командам бота"""
    await message.answer(
        "<b>Справка по командам</b>\n\n"
        "/start - Запустить бота\n"
        "/test - Отправить тестовое сообщение с кнопками\n"
        "/load - Запустить тест нагрузки\n"
        "/help - Показать эту справку\n"
        "/status - Показать статус бота"
    )

# Команда для отображения статуса
@main_router.message(Command("status"))
async def cmd_status(message: Message, trace_id: str):
    """Показывает текущий статус бота"""
    # Получаем информацию о боте
    bot_info = await bot.get_me()
    
    await message.answer(
        f"<b>Статус бота</b>\n\n"
        f"Имя: {bot_info.first_name}\n"
        f"Username: @{bot_info.username}\n"
        f"ID: {bot_info.id}\n"
        f"Trace ID: <code>{trace_id}</code>\n"
        f"Время работы: {time.strftime('%H:%M:%S', time.gmtime(time.time() - start_time))}"
    )

# Функция инициализации команд бота
async def set_commands():
    """Устанавливает список команд для бота в меню"""
    commands = [
        BotCommand(command="start", description="Запустить бота"),
        BotCommand(command="test", description="Отправить тестовое сообщение"),
        BotCommand(command="load", description="Запустить тест нагрузки"),
        BotCommand(command="help", description="Показать справку"),
        BotCommand(command="status", description="Показать статус бота")
    ]
    await bot.set_my_commands(commands)

# Обработчик запуска бота
async def on_startup():
    """Выполняется при запуске бота"""
    logger.info("Запуск отладочного бота...")
    
    # Устанавливаем команды
    await set_commands()
    
    # Регистрируем роутеры
    dp.include_router(main_router)
    dp.include_router(test_router)
    
    logger.info("Бот запущен и готов к работе!")

# Точка входа
async def main():
    """Запускает бота"""
    # Сохраняем время запуска
    global start_time
    start_time = time.time()
    
    # Инициализация бота
    await on_startup()
    
    # Удаляем webhook и сбрасываем ожидающие обновления
    await bot.delete_webhook(drop_pending_updates=True)
    
    # Запускаем поллинг
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        # Запускаем бота
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен")
    except Exception as e:
        logger.error(f"Неожиданная ошибка: {e}")
        traceback.print_exc()