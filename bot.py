import asyncio
import os
import atexit
import shutil
from typing import Dict, Any, Tuple
from pathlib import Path
from json_trace_logger import setup_json_trace_logger
from app.handlers.tracing_log_middleware import TracingLogMiddleware
import argparse
from app.utils.file_manager import cleanup_temp_files, ensure_temp_dirs
import logging
import time
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from app.fsm.states import NotaStates
from app.keyboards import kb_main

# Aiogram imports
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message

# Import states

# App imports
from app.config import settings

# Import edit flow handlers

# Import optimized logging configuration
from app.utils.logger_config import configure_logging, get_buffered_logger

# Configure logging with optimized settings
configure_logging(environment=os.getenv("ENV", "development"), log_dir="logs")

# Get buffered logger for this module
logger = get_buffered_logger(__name__)

# Create tmp dir if not exists
TMP_DIR = Path("tmp")
TMP_DIR.mkdir(exist_ok=True)

# Create all temporary directories at startup
ensure_temp_dirs()

# Global storage for user matches
user_matches: Dict[Tuple[int, int], Dict[str, Any]] = {}

async def periodic_cleanup():
    """Periodically cleans up old temporary files."""
    while True:
        try:
            cleanup_count = await asyncio.to_thread(cleanup_temp_files)
            if cleanup_count > 0:
                print(f"Periodic cleanup: removed {cleanup_count} old temp files")
        except Exception as e:
            print(f"Error during periodic cleanup: {e}")
        await asyncio.sleep(3600)  # 1 hour

def cleanup_tmp():
    try:
        shutil.rmtree(TMP_DIR)
        TMP_DIR.mkdir(exist_ok=True)
        logger.info("Cleaned up tmp directory.")
    except Exception as e:
        logger.error(f"Failed to clean tmp/: {e}")

atexit.register(cleanup_tmp)

def create_bot_and_dispatcher():
    setup_json_trace_logger()
    storage = MemoryStorage()
    # Fixed for compatibility with aiogram 3.7.0+
    from aiogram.client.default import DefaultBotProperties
    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher(storage=storage)
    dp.message.middleware(TracingLogMiddleware())
    dp.callback_query.middleware(TracingLogMiddleware())
    return bot, dp

def register_handlers(dp, bot=None):
    """
    Registers handlers for the dispatcher.
    """
    try:
        # Import routers
        from app.handlers.edit_flow import router as edit_flow_router
        from app.handlers.syrve_handler import router as syrve_router
        from app.handlers.optimized_photo_handler import router as optimized_photo_router
        
        # Check if router was already added
        if not hasattr(dp, '_registered_routers'):
            dp._registered_routers = set()
            
        # Register edit flow router
        if 'edit_flow_router' not in dp._registered_routers:
            dp.include_router(edit_flow_router)
            dp._registered_routers.add('edit_flow_router')
            logger.info("Edit flow handler registered")
            
        # Register optimized photo router
        if 'optimized_photo_router' not in dp._registered_routers:
            dp.include_router(optimized_photo_router)
            dp._registered_routers.add('optimized_photo_router')
            logger.info("Optimized photo handler registered")
            
        # Register Syrve router
        if 'syrve_router' not in dp._registered_routers:
            dp.include_router(syrve_router)
            dp._registered_routers.add('syrve_router')
            logger.info("Syrve handler registered")
            
        # Register start command
        dp.message.register(cmd_start, CommandStart())
        
        # Register cancel:all callback
        dp.callback_query.register(handle_cancel_all, F.data == "cancel:all")
        
        logger.info("All handlers registered successfully")
    except Exception as e:
        logger.error(f"Error registering handlers: {e}")

async def cmd_start(message: Message):
    await message.answer("Welcome! I'm Nota AI Bot - a bot for processing invoices.\n\nJust send me a photo of an invoice, and I'll analyze it for you.")

async def handle_cancel_all(call: CallbackQuery, state: FSMContext):
    """Обработчик кнопки Cancel с улучшенной обработкой ошибок"""
    # Используем более уникальный ID для трассировки в логах
    op_id = f"cancel_{call.message.message_id}_{int(time.time() * 1000)}"
    
    logger.info(f"[{op_id}] START: получен cancel:all callback")
    
    # Шаг 1: Немедленно отвечаем на callback (самый критический шаг)
    async def step1_answer_callback():
        try:
            await call.answer("Отмена", cache_time=1)
            return True
        except Exception as e:
            logger.error(f"[{op_id}] STEP1 ERROR: {str(e)}")
            return False
            
    # Запускаем первый шаг с коротким таймаутом (2 секунды)
    try:
        answered = await asyncio.wait_for(step1_answer_callback(), timeout=2)
        if answered:
            logger.info(f"[{op_id}] STEP1: callback answered successfully")
        else:
            logger.warning(f"[{op_id}] STEP1: failed to answer callback")
    except asyncio.TimeoutError:
        logger.error(f"[{op_id}] STEP1 TIMEOUT: callback answer timed out")
    
    # Шаг 2: Очищаем состояние
    try:
        await state.clear()
        await state.set_state(NotaStates.main_menu)
        logger.info(f"[{op_id}] STEP2: состояние очищено")
    except Exception as e:
        logger.error(f"[{op_id}] STEP2 ERROR: {str(e)}")
    
    # Шаг 3: Очищаем блокировки пользователя
    try:
        from app.utils.processing_guard import set_processing_photo
        await set_processing_photo(call.from_user.id, False)
        logger.info(f"[{op_id}] STEP3: блокировки пользователя сняты")
    except Exception as e:
        logger.error(f"[{op_id}] STEP3 ERROR: {str(e)}")
    
    # Шаг 4: Удаляем клавиатуру
    try:
        await call.message.edit_reply_markup(reply_markup=None)
        logger.info(f"[{op_id}] STEP4: клавиатура удалена")
    except Exception as e:
        logger.warning(f"[{op_id}] STEP4 WARNING: не удалось удалить клавиатуру: {str(e)}")
    
    # Шаг 5: Отправляем подтверждение пользователю
    try:
        # Получаем язык пользователя
        data = await state.get_data()
        lang = data.get("lang", "en")
        
        # Простое сообщение без форматирования для максимальной надежности
        result = await call.message.answer(
            "✅ Обработка отменена. Пожалуйста, отправьте новое фото.",
            reply_markup=kb_main(lang=lang)
        )
        logger.info(f"[{op_id}] STEP5: сообщение отправлено, message_id={result.message_id}")
    except Exception as e:
        logger.error(f"[{op_id}] STEP5 ERROR: не удалось отправить сообщение: {str(e)}")
        try:
            # Последняя попытка отправить самое простое сообщение
            await call.message.answer(
                "Операция отменена.",
                reply_markup=None
            )
            logger.info(f"[{op_id}] STEP5 FALLBACK: отправлено резервное сообщение")
        except Exception as e2:
            logger.error(f"[{op_id}] STEP5 FALLBACK ERROR: {str(e2)}")
    
    # Конец обработчика
    logger.info(f"[{op_id}] COMPLETE: обработка cancel:all завершена")

async def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Nota Telegram Bot')
    parser.add_argument('--test-mode', action='store_true', help='Run in test mode')
    parser.add_argument('--force-restart', action='store_true', help='Force reset Telegram API session')
    args = parser.parse_args()
    
    # Create logs directory if it doesn't exist
    os.makedirs('logs', exist_ok=True)
    
    # Configure logging based on test mode
    if args.test_mode:
        logging.basicConfig(level=logging.DEBUG)
        logger.info("Running in test mode")
    
    # Force restart if requested
    if args.force_restart:
        logger.info("Force restarting Telegram session")
        # Add your force restart logic here
    
    # Create bot and dispatcher
    bot, dp = create_bot_and_dispatcher()
    
    # Register handlers
    register_handlers(dp, bot)
    
    try:
        # Start polling in main thread
        logger.critical("Starting polling...")
        await dp.start_polling(
            bot,
            allowed_updates=["message", "callback_query"],
            drop_pending_updates=True
        )
        logger.critical("Polling started successfully!")
    except Exception as e:
        logger.critical(f"Failed to start polling: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())