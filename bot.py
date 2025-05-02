import logging
import uuid
import os
import shutil
import atexit
from pathlib import Path
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.enums.parse_mode import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.markdown import hbold
from app.config import settings
from app import data_loader, ocr, matcher, formatter

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

from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

bot = Bot(
    token=settings.TELEGRAM_BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=None),
)
dp = Dispatcher(storage=MemoryStorage())

@dp.message(Command("start"))
async def start_handler(message: Message):
    await message.answer("Привет! Отправьте фото накладной — я всё проверю.")

import asyncio

@dp.message(F.photo)
async def photo_handler(message: Message):
    try:
        file = await bot.get_file(message.photo[-1].file_id)
        img_bytes = await bot.download_file(file.file_path)
        parsed_data = await asyncio.to_thread(
            ocr.call_ocr, img_bytes.getvalue()
        )
        products = data_loader.load_products("data/base_products.csv")
        match_results = matcher.match_positions(parsed_data.positions, products)
        report = formatter.build_report(parsed_data, match_results)
        await message.answer(report, parse_mode=None)
    except Exception as exc:
        import uuid
        err_id = uuid.uuid4().hex[:8]
        logger.exception(f"Photo failed <{err_id}>")
        await message.answer(
            f"⚠️ OCR failed. Logged as {err_id}. "
            "Please retake the photo or send it to the developer.",
            parse_mode=None,
        )

if __name__ == "__main__":
    import asyncio
    async def main():
        logger.info("Bot polling started.")
        await dp.start_polling(bot)
    asyncio.run(main())
