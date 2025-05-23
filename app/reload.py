from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from app import data_loader
from app.i18n import t

router = Router()


@router.message(Command("reload"))
async def reload_data(message: Message, state: FSMContext):
    # Get language from state
    data = await state.get_data()
    lang = data.get("lang", "en")
    
    # This is a stub: real logic may cache or re-import CSVs
    (
        data_loader.load_products.cache_clear()
        if hasattr(data_loader.load_products, "cache_clear")
        else None
    )
    await message.answer(t("status.data_reloaded", lang=lang))
