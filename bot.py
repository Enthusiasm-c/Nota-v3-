import asyncio
import logging
import atexit
import uuid
from aiogram import Bot, Dispatcher
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from app import ocr, matcher, data_loader
from app.utils.md import escape_v2
from app.config import settings
from pathlib import Path
from aiogram.types import CallbackQuery
import shutil

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


# Глобальные bot и dp убраны для тестируемости.
bot = None
dp = None



class NotaStates(StatesGroup):
    lang = State()
    main_menu = State()
    awaiting_file = State()
    progress = State()
    editing = State()
    help = State()


user_matches = {}


def is_inline_kb(kb):
    return kb is None or isinstance(kb, InlineKeyboardMarkup)


async def safe_edit(bot, chat_id, msg_id, text, kb=None, **kwargs):
    if not is_inline_kb(kb):
        kb = None
    parse_mode = kwargs.get("parse_mode")
    if parse_mode in ("MarkdownV2", ParseMode.MARKDOWN_V2):
        text = escape_v2(text)
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text=text,
            reply_markup=kb,
            **kwargs
        )
    except Exception as e:
        logger = logging.getLogger("bot")
        if isinstance(e, types.TelegramBadRequest) and (
            "can't parse entities" in str(e) or "parse_mode" in str(e)
        ):
            logger.warning(
                f"MarkdownV2 edit failed, retrying without parse_mode: {e}")
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text=text,
                reply_markup=kb,
                **{k: v for k, v in kwargs.items() if k != "parse_mode"}
            )
        else:
            raise


def register_handlers(dp, bot=None):
    dp["__unhandled__"] = _dummy
    logging.getLogger("aiogram.event").setLevel(logging.DEBUG)
    dp.message.register(cmd_start, CommandStart())
    dp.callback_query.register(cb_new_invoice, F.data == "action:new")
    dp.message.register(photo_handler, F.photo)
    dp.message.register(handle_nlu_text, NotaStates.editing)
    dp.callback_query.register(cb_set_supplier, F.data == "set_supplier")
    dp.callback_query.register(cb_unit_btn, F.data.startswith("unit:"))
    dp.message.register(cancel_action, Command("cancel"))
    dp.callback_query.register(cancel_action, F.data == "cancel")
    dp.callback_query.register(cb_help, F.data == "action:help")
    dp.message.register(help_back, NotaStates.help, F.text.casefold() == "back")
    dp.callback_query.register(cb_cancel, F.data == "cancel:all")
    dp.callback_query.register(cb_edit_line, F.data.startswith("edit:"))
    dp.callback_query.register(cb_cancel_row, F.data.startswith("cancel:"))
    dp.callback_query.register(cb_field, F.data.startswith("field:"))
    dp.message.register(handle_field_edit, F.reply_to_message, F.text)
    dp.callback_query.register(cb_confirm, F.data == "confirm:invoice")
    dp.message.register(help_command, Command("help"))
    dp.message.register(cancel_command, Command("cancel"))
    dp.message.register(handle_edit_reply, F.reply_to_message)

# Remove any handler registration from the module/global scope.

__all__ = ["create_bot_and_dispatcher", "register_handlers"]


async def cmd_start(message, state: FSMContext):
    global assistant_thread_id
    # Create a new thread for Assistant if not exists
    if assistant_thread_id is None:
        from openai import OpenAI
        client = OpenAI(api_key=settings.OPENAI_CHAT_KEY)
        thread = client.beta.threads.create()
        assistant_thread_id = thread.id
    await state.set_state(NotaStates.lang)
    await message.answer(
        "Hi! I’m Nota AI Bot. Choose interface language.",
        reply_markup=kb_main(),
    )




async def cb_new_invoice(callback: CallbackQuery, state: FSMContext):
    await state.set_state(NotaStates.awaiting_file)
    await safe_edit(
        bot,
        callback.message.chat.id,
        callback.message.message_id,
        "Please send a photo (JPG/PNG) or PDF of the invoice.",
        kb=kb_upload(),
    )
    await callback.answer()



async def photo_handler(message, state: FSMContext):
    # TODO: Реализовать обработку фото (оставлено для совместимости)
    pass


async def handle_nlu_text(message, state: FSMContext):
    global assistant_thread_id
    text = message.text
    chat_id = message.chat.id
    msg_id = message.message_id
    if assistant_thread_id is None:
        from openai import OpenAI
        client = OpenAI(api_key=settings.OPENAI_CHAT_KEY)
        thread = client.beta.threads.create()
        assistant_thread_id = thread.id
    # Pass user message to Assistant
    assistant_response = ask_assistant(assistant_thread_id, text)
    # Try to extract JSON-tool-call edit_line
    import json
    try:
        data = json.loads(assistant_response)
        if isinstance(data, dict) and data.get('tool_call') == 'edit_line':
            # Apply edit_line logic here (update local state, etc.)
            # For now, just acknowledge
            await safe_edit(
                bot, chat_id, msg_id,
                escape_v2("Изменения применены (edit_line)", version=2),
                parse_mode=ParseMode.MARKDOWN_V2
            )
            await state.set_state(NotaStates.editing)

            return
    except Exception:
        pass
    # Otherwise, reply with assistant's text
    await safe_edit(
        bot, chat_id, msg_id,
        escape_v2(assistant_response, version=2),
        parse_mode=ParseMode.MARKDOWN_V2
    )
    await state.set_state(NotaStates.editing)



async def cb_set_supplier(callback: CallbackQuery, state: FSMContext):
    await safe_edit(
        bot,
        callback.message.chat.id,
        callback.message.message_id,
        "Введите название поставщика:",
    )
    await callback.answer()

    await state.set_state(NotaStates.editing)



async def cb_unit_btn(callback: CallbackQuery, state: FSMContext):
    unit = callback.data.split(":", 1)[1]
    await safe_edit(
        bot,
        callback.message.chat.id,
        callback.message.message_id,
        f"Единица изм. выбрана: {unit}",
    )
    await callback.answer()

    await state.set_state(NotaStates.editing)



async def cancel_action(event, state: FSMContext):
    chat_id = event.message.chat.id if hasattr(event, "message") else event.chat.id
    msg_id = event.message.message_id if hasattr(event, "message") else event.message_id
    await safe_edit(bot, chat_id, msg_id, "Действие отменено.", kb=kb_main())
    await state.set_state(NotaStates.main_menu)



async def cb_help(callback: CallbackQuery, state: FSMContext):
    await state.set_state(NotaStates.help)
    await safe_edit(
        bot,
        callback.message.chat.id,
        callback.message.message_id,
        (
            "Nota AI helps you digitize invoices in one tap. "
            "Upload a photo or PDF, edit any field, and confirm. All in one message!"
        ),
        kb=kb_help_back(),
    )
    await callback.answer()



async def help_back(message, state: FSMContext):
    await state.set_state(NotaStates.main_menu)

    await message.answer(
        "Ready to work. What would you like to do?",
        reply_markup=kb_main(),
    )




async def cb_cancel(callback: CallbackQuery, state: FSMContext):
    await state.set_state(NotaStates.main_menu)

    await safe_edit(
        bot,
        callback.message.chat.id,
        callback.message.message_id,
        "Ready to work. What would you like to do?",
        kb=kb_main(),
    )
    await callback.answer()



async def cb_edit_line(callback: CallbackQuery, state: FSMContext):
    idx = int(callback.data.split(":")[1])
    await callback.message.edit_reply_markup(
        reply_markup=kb_field_menu(idx)
    )
    await callback.answer()



async def cb_cancel_row(callback: CallbackQuery, state: FSMContext):
    if callback.data == "cancel:all":
        await callback.message.edit_reply_markup(reply_markup=None)
        await safe_edit(
            bot,
            callback.message.chat.id,
            callback.message.message_id,
            "Editing cancelled. All keyboards removed.",
            kb=None,
        )
        await state.set_state(NotaStates.main_menu)

    else:
        idx = int(callback.data.split(":")[1])
        await callback.message.edit_reply_markup(reply_markup=None)
        await safe_edit(
            bot,
            callback.message.chat.id,
            callback.message.message_id,
            f"Editing for row {idx+1} cancelled.",
            kb=None,
        )
        await state.set_state(NotaStates.editing)

    await callback.answer()



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
    await state.update_data(
        edit_idx=idx, edit_field=field, msg_id=callback.message.message_id
    )
    await callback.answer()



async def handle_field_edit(message, state: FSMContext):
    global assistant_thread_id
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
    # Send user input to Assistant for dialog edit
    text = message.text.strip()
    if assistant_thread_id is None:
        from openai import OpenAI
        client = OpenAI(api_key=settings.OPENAI_CHAT_KEY)
        thread = client.beta.threads.create()
        assistant_thread_id = thread.id
    assistant_response = ask_assistant(assistant_thread_id, text)
    import json
    try:
        data = json.loads(assistant_response)
        if isinstance(data, dict) and data.get('tool_call') == 'edit_line':
            # Apply edit_line: update invoice data
            for k, v in data.get('fields', {}).items():
                entry["match_results"][idx][k] = v
            # Re-run matcher for this line
            products = data_loader.load_products("data/base_products.csv")
            entry["match_results"][idx] = matcher.match_positions([entry["match_results"][idx]], products)[0]
            parsed_data = entry["parsed_data"]
            report = build_report(parsed_data, entry["match_results"])
            await safe_edit(
                bot,
                message.chat.id,
                msg_id,
                escape_v2(report, version=2),
                kb=kb_report(entry["match_results"]),
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            await state.set_state(NotaStates.editing)

            return
    except Exception:
        pass
    # Otherwise, reply with assistant's text
    await safe_edit(
        bot,
        message.chat.id,
        msg_id,
        escape_v2(assistant_response, version=2),
        kb=kb_report(entry["match_results"]),
        parse_mode=ParseMode.MARKDOWN_V2,
    )
    await state.set_state(NotaStates.editing)



async def cb_confirm(callback: CallbackQuery, state: FSMContext):
    await safe_edit(
        bot,
        callback.message.chat.id,
        callback.message.message_id,
        "✅ Invoice #123 saved to Syrve. Thank you!",
        kb=kb_main(),
    )
    await state.set_state(NotaStates.main_menu)

    await callback.answer()



async def help_command(message, state: FSMContext):
    await state.set_state(NotaStates.help)
    await message.answer(
        (
            "Nota AI helps you digitize invoices in one tap. "
            "Upload a photo or PDF, edit any field, and confirm. All in one message!"
        ),
        reply_markup=kb_help_back(),
    )


async def cancel_command(message, state: FSMContext):
    await state.set_state(NotaStates.main_menu)

    await message.answer(
        "Ready to work. What would you like to do?",
        reply_markup=kb_main(),
    )




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


async def photo_handler(message):
    try:
        # Step 1: Send progress message
        progress_msg = await message.answer(
            "🔄 Analysing invoice photo…",
            parse_mode=None
        )
        progress_msg_id = progress_msg.message_id
        user_id = message.from_user.id
        # Download photo bytes
        file = await bot.get_file(message.photo[-1].file_id)
        img_bytes = await bot.download_file(file.file_path)
        # Step 2: OCR (no progress cycling)
        ocr_result = await asyncio.to_thread(ocr.call_openai_ocr, img_bytes.getvalue())
        # Step 3: Matcher
        products = data_loader.load_products("data/base_products.csv")
        match_results = matcher.match_positions(ocr_result.positions, products)
        user_matches[(user_id, progress_msg_id)] = {
            "parsed_data": ocr_result,
            "match_results": match_results
        }
        # Step 4: Final report (single message)
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
                InlineKeyboardButton(
                    text="🚫 Cancel edit", callback_data="cancel:all"
                )
            ])
            inline_kb = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
        else:
            inline_kb = None
        await safe_edit(
            bot,
            message.chat.id,
            progress_msg_id,
            escape_v2(report, version=2),
            kb=inline_kb,
            parse_mode="MarkdownV2"
        )
    except Exception:
        err_id = uuid.uuid4().hex[:8]
        logger = logging.getLogger("bot")
        logger.exception(f"Photo failed <{err_id}>")
        await message.answer(
            (
                f"⚠️ OCR failed. Logged as {err_id}. "
                "Please retake the photo or send it to the developer."
            ),
            parse_mode=None,
        )


async def text_fallback(message):
    await message.answer("📸 Please send an invoice photo (image only).", parse_mode=None)


# Silence unhandled update logs

async def _dummy(update, data):
    pass


logging.getLogger("aiogram.event").setLevel(logging.DEBUG)


from aiogram.filters import CommandStart
from aiogram.enums import ParseMode
from aiogram import F
from aiogram.types import InlineKeyboardMarkup, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from app.keyboards import kb_main, kb_upload, kb_help_back, kb_report, kb_field_menu

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

# --- Safe edit function ---
async def safe_edit(bot, chat_id, msg_id, text, kb=None, **kwargs):
    if kb is not None and not isinstance(kb, InlineKeyboardMarkup):
        kb = None
    await bot.edit_message_text(
        chat_id=chat_id,
        message_id=msg_id,
        text=text,
        reply_markup=kb,
        **kwargs
    )


async def text_fallback(message):
    await message.answer("📸 Please send an invoice photo (image only).", parse_mode=None)


async def _dummy(update, data):
    pass



logging.getLogger("aiogram.event").setLevel(logging.DEBUG)


if __name__ == "__main__":
    async def main():
        global bot, dp
        bot, dp = create_bot_and_dispatcher()
        register_handlers(dp, bot)
        await dp.start_polling(bot)
    asyncio.run(main())
