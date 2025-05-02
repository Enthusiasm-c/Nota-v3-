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
    default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN_V2),
)
dp = Dispatcher(storage=MemoryStorage())

@dp.message(Command("start"))
async def start_handler(message: Message):
    await message.answer("Привет! Отправьте фото накладной — я всё проверю.")

@dp.message(F.photo)
async def photo_handler(message: Message):
    try:
        photo = message.photo[-1]
        file_id = photo.file_id
        file = await bot.get_file(file_id)
        file_path = file.file_path
        image_bytes = await bot.download_file(file_path)
        # Save to tmp/ with uuid
        uid = str(uuid.uuid4())
        tmp_path = TMP_DIR / f"{uid}.jpg"
        with open(tmp_path, "wb") as f:
            f.write(image_bytes.read())
        # OCR (stub)
        try:
            parsed_data = await ocr.call_openai_ocr(image_bytes.getvalue())
        except NotImplementedError:
            # For dev: mock parsed_data
            parsed_data = {
                "supplier": "TESTSUPPLIER",
                "date": "26-Sep-2023",
                "positions": [{"name": "Product A", "qty": 1, "unit": "pcs"} for _ in range(17)] + [{"name": "Unknown", "qty": 1, "unit": "pcs"} for _ in range(3)]
            }
        # Load data
        suppliers = data_loader.load_suppliers("data/suppliers.csv")
        products = data_loader.load_products("data/products.csv")
        # Match
        match_results = matcher.match_positions(parsed_data["positions"], products)
        # Format report
        report = formatter.build_report(parsed_data, match_results)
        await message.answer(report)
    except Exception as e:
        logger.exception("Failed to process photo")
        await message.answer("⚠️ Sorry, something went wrong.")

if __name__ == "__main__":
    import asyncio
    async def main():
        logger.info("Bot polling started.")
        await dp.start_polling(bot)
    asyncio.run(main())
