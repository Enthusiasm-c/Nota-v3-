#!/usr/bin/env python3
"""
Debug Cancel Button - специальный бот для отладки проблемы с зависанием кнопки cancel.
"""
import os
import asyncio
import logging
import traceback
from aiogram import Bot, Dispatcher, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters.command import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("debug_cancel_button.log")
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN not found in environment variables")
    exit(1)

# Define states
class BotStates(StatesGroup):
    main_menu = State()
    processing = State()
    awaiting_input = State()

# Create bot instance with explicit parse mode to avoid caching issues
from aiogram.client.default import DefaultBotProperties
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=None))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Command handlers
@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Handle /start command"""
    logger.info(f"User {message.from_user.id} started the bot")
    
    # Clear state and set to main menu
    await state.clear()
    await state.set_state(BotStates.main_menu)
    
    # Send welcome message with test buttons
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Test Button 1", callback_data="test:1")],
        [InlineKeyboardButton(text="Test Button 2", callback_data="test:2")],
        [InlineKeyboardButton(text="❌ Cancel", callback_data="cancel:all")]
    ])
    
    await message.answer(
        "DEBUG BOT - CANCEL BUTTON TEST\n\n"
        "Press any button to test callback handling.\n"
        "Press Cancel button to test the fix.",
        reply_markup=keyboard
    )

@dp.message(Command("test"))
async def cmd_test(message: Message):
    """Send a test message with cancel button"""
    logger.info(f"User {message.from_user.id} requested test buttons")
    
    # Create keyboard with cancel button
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Action Button", callback_data="action:test")],
        [InlineKeyboardButton(text="❌ Cancel", callback_data="cancel:all")]
    ])
    
    await message.answer(
        "Test message with cancel button.\n"
        "Press Cancel to test the handler.",
        reply_markup=keyboard
    )

# Handle cancel callback - simplified version for testing
@dp.callback_query(F.data == "cancel:all")
async def handle_cancel_all(call: CallbackQuery, state: FSMContext):
    """Cancel button handler for debugging"""
    op_id = f"debug_cancel_{call.message.message_id}"
    
    # Log extensively at each step
    logger.info(f"[{op_id}] START: Processing cancel:all callback")
    
    # 1. Immediately answer the callback
    try:
        await call.answer("Canceling...")
        logger.info(f"[{op_id}] STEP 1: Callback answered successfully")
    except Exception as e:
        logger.error(f"[{op_id}] STEP 1 ERROR: Failed to answer callback: {e}")
    
    # 2. Get current state for debugging
    try:
        current_state = await state.get_state()
        logger.info(f"[{op_id}] STEP 2: Current state = {current_state}")
    except Exception as e:
        logger.error(f"[{op_id}] STEP 2 ERROR: Failed to get state: {e}")
        current_state = "unknown"
    
    # 3. Clear state
    try:
        await state.clear()
        logger.info(f"[{op_id}] STEP 3: State cleared successfully")
    except Exception as e:
        logger.error(f"[{op_id}] STEP 3 ERROR: Failed to clear state: {e}")
    
    # 4. Set new state
    try:
        await state.set_state(BotStates.main_menu)
        logger.info(f"[{op_id}] STEP 4: Set new state to main_menu")
    except Exception as e:
        logger.error(f"[{op_id}] STEP 4 ERROR: Failed to set state: {e}")
    
    # 5. Remove keyboard
    try:
        await call.message.edit_reply_markup(reply_markup=None)
        logger.info(f"[{op_id}] STEP 5: Removed keyboard successfully")
    except Exception as e:
        logger.error(f"[{op_id}] STEP 5 ERROR: Failed to remove keyboard: {e}")
    
    # 6. Send confirmation message
    try:
        result = await call.message.answer("✅ Operation canceled successfully!")
        logger.info(f"[{op_id}] STEP 6: Sent confirmation message, message_id={result.message_id}")
    except Exception as e:
        logger.error(f"[{op_id}] STEP 6 ERROR: Failed to send message: {e}\n{traceback.format_exc()}")
        try:
            # Alternative method to send message
            await bot.send_message(
                chat_id=call.message.chat.id,
                text="✅ Operation canceled (fallback method)"
            )
            logger.info(f"[{op_id}] STEP 6 FALLBACK: Sent message using fallback method")
        except Exception as e2:
            logger.error(f"[{op_id}] STEP 6 FALLBACK ERROR: Failed to send fallback message: {e2}")
    
    logger.info(f"[{op_id}] COMPLETE: Cancel handler finished")

# Handle all other callbacks
@dp.callback_query()
async def other_callback_handler(call: CallbackQuery):
    """Handler for all other callbacks"""
    logger.info(f"Received callback: {call.data}")
    await call.answer(f"You pressed: {call.data}")
    await call.message.answer(f"Callback '{call.data}' processed successfully!")

async def main():
    """Start the bot"""
    logger.info("Starting debug cancel button bot...")
    
    # Use explicit webhook deletion with drop_pending_updates
    await bot.delete_webhook(drop_pending_updates=True)
    
    # Start polling
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        traceback.print_exc()