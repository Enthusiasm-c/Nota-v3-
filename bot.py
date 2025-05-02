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

bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

from aiogram.filters import CommandStart
from aiogram.enums import ParseMode
from aiogram import F

@dp.message(CommandStart())
async def cmd_start(message):
    await message.answer(
        "👋 Hi! Send me a *photo* of your supplier invoice — I’ll parse and validate it.",
        parse_mode=ParseMode.MARKDOWN_V2,
    )

@dp.message(F.photo)
async def photo_handler(message):
    try:
        file = await bot.get_file(message.photo[-1].file_id)
        img_bytes = await bot.download_file(file.file_path)
        parsed_data = await asyncio.to_thread(ocr.call_openai_ocr, img_bytes.getvalue())
        products = data_loader.load_products("data/base_products.csv")
        match_results = matcher.match_positions(parsed_data.positions, products)
        report = build_report(parsed_data, match_results)
        await message.answer(report, parse_mode=None)
    except Exception:
        err_id = uuid.uuid4().hex[:8]
        logger = logging.getLogger("bot")
        logger.exception(f"Photo failed <{err_id}>")
        await message.answer(
            f"⚠️ OCR failed. Logged as {err_id}. "
            "Please retake the photo or send it to the developer.",
            parse_mode=None,
        )

# Fallback for any text message that is not a command
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
        logger.info("Bot polling started.")
        await dp.start_polling(bot)

    asyncio.run(main())
