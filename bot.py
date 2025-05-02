import asyncio
import logging
import atexit
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from app import ocr, matcher, data_loader
from app.formatter import build_report
from app.config import settings
from pathlib import Path
import shutil
import uuid

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create tmp dir if not exists
TMP_DIR = Path("tmp")
TMP_DIR.mkdir(exist_ok=True)

def cleanup_tmp():
    try:
        shutil.rmtree(TMP_DIR)
        TMP_DIR.mkdir(exist_ok=True)
        logger.info("Cleaned up tmp directory.")
    except Exception as e:
        logger.error(f"Failed to clean tmp/: {e}")

atexit.register(cleanup_tmp)

def create_bot_and_dispatcher():
    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    return bot, dp


from aiogram.filters import CommandStart
from aiogram.enums import ParseMode
from aiogram import F
from aiogram.types import InlineKeyboardMarkup, CallbackQuery
from app.keyboards import kb_edit

# In-memory store for match_results keyed by user_id and message_id
user_matches = {}

def register_handlers(dp, bot):
    @dp.message(CommandStart())
    async def cmd_start(message):
        await message.answer(
            "👋 Hi! Send me a *photo* of your supplier invoice — I’ll parse and validate it.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    @dp.callback_query(lambda c: c.data.startswith("ok:") or c.data.startswith("del:") or c.data.startswith("edit:"))
    async def handle_position_callback(callback: CallbackQuery):
        user_id = callback.from_user.id
        orig_msg_id = callback.message.reply_to_message.message_id if callback.message.reply_to_message else callback.message.message_id
        key = (user_id, orig_msg_id)
        if key not in user_matches:
            await callback.answer("Session expired or not found.", show_alert=True)
            return
        data = callback.data
        idx = int(data.split(":")[1])
        action = data.split(":")[0]
        entry = user_matches[key]
        match_results = entry["match_results"]
        parsed_data = entry["parsed_data"]
        if action == "ok":
            match_results[idx]["status"] = "ok"
            await callback.message.edit_reply_markup(reply_markup=None)
            # Re-render main report
            report = build_report(parsed_data, match_results)
            await callback.message.reply(f"✅ Marked line {idx+1} as OK.\n" + report)
        elif action == "del":
            match_results[idx]["status"] = "removed"
            await callback.message.edit_reply_markup(reply_markup=None)
            report = build_report(parsed_data, match_results)
            await callback.message.reply(f"🗑 Deleted line {idx+1}.\n" + report)
        elif action == "edit":
            await callback.message.reply(f"✏️ Please reply with the corrected text for line {idx+1}.")
            # Store edit context for next text reply
            entry["edit_idx"] = idx
        await callback.answer()

    @dp.message(F.reply_to_message)
    async def handle_edit_reply(message):
        user_id = message.from_user.id
        orig_msg_id = message.reply_to_message.reply_to_message.message_id if message.reply_to_message.reply_to_message else message.reply_to_message.message_id
        key = (user_id, orig_msg_id)
        if key not in user_matches:
            return
        entry = user_matches[key]
        if "edit_idx" not in entry:
            return
        idx = entry.pop("edit_idx")
        # Update name (simplest: replace name, keep other fields)
        match_results = entry["match_results"]
        match_results[idx]["name"] = message.text.strip()
        match_results[idx]["status"] = "unknown"  # Or re-match if needed
        parsed_data = entry["parsed_data"]
        report = build_report(parsed_data, match_results)
        await message.reply(f"✏️ Updated line {idx+1}.\n" + report)

    @dp.message(F.photo)
    async def photo_handler(message):
        try:
            file = await bot.get_file(message.photo[-1].file_id)
            img_bytes = await bot.download_file(file.file_path)
            parsed_data = await asyncio.to_thread(ocr.call_openai_ocr, img_bytes.getvalue())
            products = data_loader.load_products("data/base_products.csv")
            match_results = matcher.match_positions(parsed_data.positions, products)
            # Store in-memory by user and message
            user_matches[(message.from_user.id, message.message_id)] = {
                "parsed_data": parsed_data,
                "match_results": match_results
            }
            report = build_report(parsed_data, match_results)
            # Send main report
            await message.answer(report, parse_mode=None)
            # Send inline keyboards for each unknown/unit_mismatch
            for idx, pos in enumerate(match_results):
                if pos["status"] != "ok":
                    kb = kb_edit(idx)  # Single edit button for problematic row
                    if kb:
                        await message.answer(
                            f"Line {idx+1}: {pos['name']} — needs review",
                            reply_markup=kb
                        )
        except Exception:
            err_id = uuid.uuid4().hex[:8]
            logger = logging.getLogger("bot")
            logger.exception(f"Photo failed <{err_id}>")
            await message.answer(
                f"⚠️ OCR failed. Logged as {err_id}. "
                "Please retake the photo or send it to the developer.",
                parse_mode=None,
            )

    @dp.message(F.text & ~F.command)
    async def text_fallback(message):
        await message.answer("📸 Please send an invoice photo (image only).", parse_mode=None)

    # Silence unhandled update logs
    async def _dummy(update, data):
        pass

    dp["__unhandled__"] = _dummy
    import logging
    logging.getLogger("aiogram.event").setLevel(logging.DEBUG)

if __name__ == "__main__":
    async def main():
        bot, dp = create_bot_and_dispatcher()
        register_handlers(dp, bot)
        logger.info("Bot polling started.")
        await dp.start_polling(bot)

    asyncio.run(main())
