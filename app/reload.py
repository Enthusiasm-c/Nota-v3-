from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from app import data_loader

router = Router()

@router.message(Command("reload"))
async def reload_data(message: Message):
    # This is a stub: real logic may cache or re-import CSVs
    data_loader.load_products.cache_clear() if hasattr(data_loader.load_products, 'cache_clear') else None
    await message.answer("Data reloaded from CSV files.")
