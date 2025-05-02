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
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from app.keyboards import kb_main, kb_upload, kb_help_back, kb_report, kb_field_menu
from app.formatter import build_report
import uuid

# FSM States
class NotaStates(StatesGroup):
    lang = State()
    main_menu = State()
    awaiting_file = State()
    progress = State()
    editing = State()
    help = State()

# In-memory store for user sessions: {user_id: {msg_id: {...}}}
user_matches = {}

# Handler registration

def register_handlers(dp, bot):
    @dp.message(CommandStart())
    async def cmd_start(message, state: FSMContext):
        await state.set_state(NotaStates.lang)
        await message.answer(
            "Hi! I’m Nota AI Bot. Choose interface language.",
            reply_markup=kb_main(),
        )

    @dp.callback_query(F.data == "action:new")
    async def cb_new_invoice(callback: CallbackQuery, state: FSMContext):
        await state.set_state(NotaStates.awaiting_file)
        await callback.message.edit_text(
            "Please send a photo (JPG/PNG) or PDF of the invoice.",
            reply_markup=kb_upload(),
        )
        await callback.answer()

    @dp.message(NotaStates.awaiting_file, F.photo)
    async def handle_photo(message, state: FSMContext):
        try:
            await state.set_state(NotaStates.progress)
            progress_msg = await message.answer(
                "✅ File received. Analysing invoice photo…",
                reply_markup=None,
            )
            progress_msg_id = progress_msg.message_id
            user_id = message.from_user.id
            # Download photo
            file = await bot.get_file(message.photo[-1].file_id)
            img_bytes = await bot.download_file(file.file_path)
            # Progress cycling
            progress_phrases = [
                "🔄 Comparing with database…",
                "⏳ Almost done…"
            ]
            import asyncio
            task = asyncio.create_task(asyncio.to_thread(ocr.call_openai_ocr, img_bytes.getvalue()))
            idx = 0
            while not task.done():
                await asyncio.sleep(7)
                idx = (idx + 1) % len(progress_phrases)
                await bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=progress_msg_id,
                    text=progress_phrases[idx],
                )
            ocr_result = await task
            await bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=progress_msg_id,
                text=progress_phrases[0],
            )
            # Matcher
            from app import data_loader, matcher
            products = data_loader.load_products("data/base_products.csv")
            match_results = matcher.match_positions(ocr_result.positions, products)
            user_matches[(user_id, progress_msg_id)] = {
                "parsed_data": ocr_result,
                "match_results": match_results
            }
            # Final report
            report = build_report(ocr_result, match_results)
            await bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=progress_msg_id,
                text=report,
                reply_markup=kb_report(match_results),
                parse_mode="MarkdownV2",
            )
            await state.set_state(NotaStates.editing)
        except Exception:
            err_id = uuid.uuid4().hex[:8]
            import logging
            logger = logging.getLogger("bot")
            logger.exception(f"Photo failed <{err_id}>")
            await message.answer(
                f"⚠️ OCR failed. Logged as {err_id}. Please retake the photo or send it to the developer.",
            )
            await state.set_state(NotaStates.main_menu)

    @dp.callback_query(F.data == "action:help")
    async def cb_help(callback: CallbackQuery, state: FSMContext):
        await state.set_state(NotaStates.help)
        await callback.message.edit_text(
            "Nota AI helps you digitize invoices in one tap. Upload a photo or PDF, edit any field, and confirm. All in one message!",
            reply_markup=kb_help_back(),
        )
        await callback.answer()

    @dp.message(NotaStates.help, F.text.casefold() == "back")
    async def help_back(message, state: FSMContext):
        await state.set_state(NotaStates.main_menu)
        await message.answer(
            "Ready to work. What would you like to do?",
            reply_markup=kb_main(),
        )

    @dp.callback_query(F.data == "cancel:all")
    async def cb_cancel(callback: CallbackQuery, state: FSMContext):
        await state.set_state(NotaStates.main_menu)
        await callback.message.edit_text(
            "Ready to work. What would you like to do?",
            reply_markup=kb_main(),
        )
        await callback.answer()

    @dp.callback_query(F.data.startswith("edit:"))
    async def cb_edit_line(callback: CallbackQuery, state: FSMContext):
        idx = int(callback.data.split(":")[1])
        await callback.message.edit_reply_markup(
            reply_markup=kb_field_menu(idx)
        )
        await callback.answer()

    @dp.callback_query(F.data.startswith("field:"))
    async def cb_field(callback: CallbackQuery, state: FSMContext):
        _, field, idx = callback.data.split(":")
        idx = int(idx)
        # prompt force-reply
        await callback.message.bot.send_message(
            callback.from_user.id,
            f"Enter new value for {field} (line {idx+1}):",
            reply_markup={"force_reply": True},
        )
        # Store context in FSM
        await state.update_data(edit_idx=idx, edit_field=field, msg_id=callback.message.message_id)
        await callback.answer()

    @dp.message(F.reply_to_message, F.text)
    async def handle_field_edit(message, state: FSMContext):
        data = await state.get_data()
        idx = data.get("edit_idx")
        field = data.get("edit_field")
        msg_id = data.get("msg_id")
        if idx is None or field is None or msg_id is None:
            return
        user_id = message.from_user.id
        key = (user_id, msg_id)
        if key not in user_matches:
            return
        entry = user_matches[key]
        match_results = entry["match_results"]
        match_results[idx][field] = message.text.strip()
        # Re-run matcher for this line if field is 'name', 'unit', etc.
        from app import matcher, data_loader
        products = data_loader.load_products("data/base_products.csv")
        match_results[idx] = matcher.match_positions([match_results[idx]], products)[0]
        # Пересчитать summary/статус
        parsed_data = entry["parsed_data"]
        report = build_report(parsed_data, match_results)
        # Обновить сообщение (editMessage)
        await message.bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=msg_id,
            text=report,
            reply_markup=kb_report(match_results),
            parse_mode=ParseMode.MARKDOWN,
        )
        await state.set_state(NotaStates.editing)

    @dp.callback_query(F.data == "confirm:invoice")
    async def cb_confirm(callback: CallbackQuery, state: FSMContext):
        await callback.message.edit_text(
            "✅ Invoice #123 saved to Syrve. Thank you!",
            reply_markup=kb_main(),
        )
        await state.set_state(NotaStates.main_menu)
        await callback.answer()

    @dp.message(Command("help"))
    async def help_command(message, state: FSMContext):
        await state.set_state(NotaStates.help)
        await message.answer(
            "Nota AI helps you digitize invoices in one tap. Upload a photo or PDF, edit any field, and confirm. All in one message!",
            reply_markup=kb_help_back(),
        )

    @dp.message(Command("cancel"))
    async def cancel_command(message, state: FSMContext):
        await state.set_state(NotaStates.main_menu)
        await message.answer(
            "Ready to work. What would you like to do?",
            reply_markup=kb_main(),
        )

    @dp.message(F.reply_to_message)
    async def handle_edit_reply(message):
        user_id = message.from_user.id
        orig_msg_id = message.reply_to_message.message_id
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
            # Step 1: Send progress message
            progress_msg = await message.answer(
                "🔄 Analysing invoice photo…",
                parse_mode=None
            )
            progress_msg_id = progress_msg.message_id
            user_id = message.from_user.id
            start_time = asyncio.get_event_loop().time()
            last_update = start_time
            # Download photo bytes
            file = await bot.get_file(message.photo[-1].file_id)
            img_bytes = await bot.download_file(file.file_path)
            # Step 2: OCR (simulate long-running with progress updates)
            ocr_task = asyncio.create_task(asyncio.to_thread(ocr.call_openai_ocr, img_bytes.getvalue()))
            progress_phrases = [
                "🔄 Analysing invoice photo…",
                "🔄 Comparing with database…",
                "⏳ Almost done…",
                "⏳ Few more seconds…"
            ]
            progress_idx = 0
            while not ocr_task.done():
                now = asyncio.get_event_loop().time()
                elapsed = now - start_time
                if elapsed > 15 and now - last_update > 7:
                    progress_idx = (progress_idx + 1) % 2 + 2  # cycle between 2 and 3
                    await bot.edit_message_text(
                        chat_id=message.chat.id,
                        message_id=progress_msg_id,
                        text=progress_phrases[progress_idx],
                        parse_mode=None
                    )
                    last_update = now
                await asyncio.sleep(0.5)
            ocr_result = await ocr_task
            # Step 3: After OCR, update progress
            await bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=progress_msg_id,
                text=progress_phrases[1],
                parse_mode=None
            )
            # Step 4: Matcher
            products = data_loader.load_products("data/base_products.csv")
            match_results = matcher.match_positions(ocr_result.positions, products)
            user_matches[(user_id, progress_msg_id)] = {
                "parsed_data": ocr_result,
                "match_results": match_results
            }
            # Step 5: Final report (single message)
            from app.keyboards import kb_edit, kb_cancel_all
            report = build_report(ocr_result, match_results)
            # Build inline keyboard: one Edit button per not-ok row, plus global Cancel
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            keyboard_rows = []
            for idx, pos in enumerate(match_results):
                if pos["status"] != "ok":
                    keyboard_rows.append([
                        InlineKeyboardButton(text="✏️ Edit", callback_data=f"edit:{idx}")
                    ])
            if keyboard_rows:
                keyboard_rows.append([
                    InlineKeyboardButton(text="🚫 Cancel edit", callback_data="cancel:all")
                ])
                inline_kb = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
            else:
                inline_kb = None
            await bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=progress_msg_id,
                text=report,
                reply_markup=inline_kb,
                parse_mode="MarkdownV2"
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
