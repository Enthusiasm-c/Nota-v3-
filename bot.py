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

@dp.message(Command("start"))
async def start_handler(message):
    await message.answer("Привет! Отправьте фото накладной — я всё проверю.")

@dp.message(Command("photo"))
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

if __name__ == "__main__":
    async def main():
        logger.info("Bot polling started.")
        await dp.start_polling(bot)

    asyncio.run(main())
