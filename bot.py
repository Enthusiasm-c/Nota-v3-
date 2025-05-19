import asyncio
import concurrent.futures
import logging
import re
import os
from app.formatters.report import build_report
import atexit
import uuid
import json
import time
import shutil
from typing import Dict, Any, Tuple
from pathlib import Path
import signal
import sys
from json_trace_logger import setup_json_trace_logger
from app.handlers.tracing_log_middleware import TracingLogMiddleware
import argparse
from app.utils.file_manager import cleanup_temp_files, ensure_temp_dirs

# Aiogram imports
from aiogram import Bot, Dispatcher, F
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command, CommandStart
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramBadRequest
from aiogram.enums import ParseMode
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message

# Import states
from app.fsm.states import EditFree, NotaStates

# App imports
from app import ocr, matcher, data_loader
from app.utils.md import escape_html, clean_html
from app.config import settings
from app.i18n import t

# Import edit flow handlers
from app.handlers.edit_flow import router as edit_flow_router

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
        
        logger.info("All handlers registered successfully")
    except Exception as e:
        logger.error(f"Error registering handlers: {e}")

async def cmd_start(message: Message):
    await message.answer("Welcome! I'm Nota AI Bot - a bot for processing invoices.\n\nJust send me a photo of an invoice, and I'll analyze it for you.")

async def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Nota Telegram Bot')
    parser.add_argument('--test-mode', action='store_true', help='Run in test mode')
    parser.add_argument('--force-restart', action='store_true', help='Force reset Telegram API session')
    args = parser.parse_args()
    
    # Create logs directory if it doesn't exist
    os.makedirs("logs", exist_ok=True)
    
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