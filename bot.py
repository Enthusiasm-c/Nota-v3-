import asyncio
import logging
from app.formatter import build_report
import atexit
import uuid
import json
import time
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramBadRequest
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
# assistant_thread_id убран из глобальных переменных и перенесен в FSMContext


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
        if isinstance(e, TelegramBadRequest) and (
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


from app.utils.api_decorators import with_async_retry_backoff, ErrorType

@with_async_retry_backoff(max_retries=2, initial_backoff=1.0, backoff_factor=2.0)
async def ask_assistant(thread_id, message):
    """
    Send a message to the OpenAI Assistant and get the response.
    Использует декоратор with_async_retry_backoff для автоматической обработки ошибок и повторных попыток.
    
    Args:
        thread_id: ID потока в OpenAI Assistant
        message: Сообщение для обработки
        
    Returns:
        str: Ответ от ассистента или сообщение об ошибке
    """
    from app.config import get_chat_client
    client = get_chat_client()
    if not client or not settings.OPENAI_ASSISTANT_ID:
        logging.error("Assistant unavailable: missing client or assistant ID")
        return "Sorry, the assistant is unavailable at the moment. Please try again later."
    
    # Add the user's message to the thread
    client.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=message
    )
    
    # Run the assistant on the thread
    run = client.beta.threads.runs.create(
        thread_id=thread_id,
        assistant_id=settings.OPENAI_ASSISTANT_ID
    )

    # Wait for the run to complete (with timeout)
    start_time = time.time()
    timeout = 30  # 30 seconds timeout
    while True:
        if time.time() - start_time > timeout:
            # Timeout error - raise exception to trigger retry in decorator
            raise RuntimeError("The assistant took too long to respond.")
        
        run_status = client.beta.threads.runs.retrieve(
            thread_id=thread_id,
            run_id=run.id
        )
        
        if run_status.status == "completed":
            # Success path
            # Get the latest message from the assistant
            messages = client.beta.threads.messages.list(
                thread_id=thread_id
            )
            
            # Return the content of the last message from the assistant
            for msg in messages.data:
                if msg.role == "assistant":
                    # Get the text content from the message
                    if hasattr(msg, "content") and msg.content:
                        for content_part in msg.content:
                            if hasattr(content_part, "text") and content_part.text:
                                return content_part.text.value
                    return "Assistant responded with no text content."
            
            return "No response from the assistant."
            
        elif run_status.status in ["failed", "cancelled", "expired"]:
            # Fatal error in run - raise exception to trigger retry in decorator
            raise RuntimeError(f"Assistant response failed with status: {run_status.status}")
        
        await asyncio.sleep(1)  # Poll every second


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
    # Получаем текущие данные состояния пользователя
    user_data = await state.get_data()
    
    # Проверяем, есть ли уже thread_id в состоянии
    if "assistant_thread_id" not in user_data:
        # Создаем новый поток для пользователя если нет
        from openai import OpenAI
        from app.config import get_chat_client
        
        client = get_chat_client()
        if not client:
            client = OpenAI(api_key=settings.OPENAI_CHAT_KEY)
            
        thread = client.beta.threads.create()
        # Сохраняем thread_id в состоянии пользователя
        await state.update_data(assistant_thread_id=thread.id)
        logger.info(f"Created new assistant thread for user {message.from_user.id}")
    
    await state.set_state(NotaStates.lang)
    await message.answer(
        "Hi! I'm Nota AI Bot. Choose interface language.",
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



from app.utils.api_decorators import with_progress_stages, update_stage

# Определение стадий для обработки фото
PHOTO_STAGES = {
    "download": "Получение изображения",
    "ocr": "Распознавание текста инвойса",  
    "matching": "Сопоставление позиций",
    "report": "Формирование отчета"
}

@with_progress_stages(stages=PHOTO_STAGES)
async def photo_handler(message, state: FSMContext, **kwargs):
    """
    Обрабатывает загруженные фото инвойсов с продвинутой обработкой ошибок.
    Использует декоратор with_progress_stages для отслеживания этапов выполнения.
    
    Ход работы:
    1. Отображает индикатор прогресса
    2. Загружает и анализирует фото через OCR
    3. Сопоставляет найденные позиции с базой продуктов
    4. Формирует отчет и отображает его с кнопками редактирования
    """
    # Данные для отладки
    user_id = message.from_user.id
    photo_id = message.photo[-1].file_id if message.photo else None
    
    # Получаем _stages и _req_id из контекста декоратора
    stages = kwargs.get('_stages', {})
    stages_names = kwargs.get('_stages_names', {})
    req_id = kwargs.get('_req_id', uuid.uuid4().hex[:8])
    
    # Шаг 1: Показываем пользователю, что обрабатываем запрос
    progress_msg = await message.answer(
        "🔄 Загрузка и анализ фото...",
        parse_mode=None
    )
    progress_msg_id = progress_msg.message_id
    
    # Функция для обновления сообщения о прогрессе
    async def update_progress_message(stage=None, stage_name=None, error_message=None):
        """Вспомогательная функция для обновления сообщения о прогрессе"""
        if error_message:
            await safe_edit(
                bot, message.chat.id, progress_msg_id,
                f"⚠️ {error_message}",
                parse_mode=None
            )
        elif stage and stage_name:
            await safe_edit(
                bot, message.chat.id, progress_msg_id,
                f"🔄 {stage_name}...",
                parse_mode=None
            )
    
    # Передаем функцию обновления прогресса
    kwargs['_update_progress'] = update_progress_message
    
    try:
        # Шаг 2: Загрузка фото
        # Получаем информацию о файле
        file = await bot.get_file(message.photo[-1].file_id)
        
        # Загружаем содержимое файла
        img_bytes = await bot.download_file(file.file_path)
        
        # Обновляем статус стадии
        update_stage("download", kwargs, update_progress_message)
        logger.info(f"[{req_id}] Downloaded photo from user {user_id}, size {len(img_bytes.getvalue())} bytes")
        
        # Шаг 3: OCR изображения
        # Запуск OCR в отдельном потоке
        ocr_result = await asyncio.to_thread(ocr.call_openai_ocr, img_bytes.getvalue())
        
        # Обновляем статус стадии
        update_stage("ocr", kwargs, update_progress_message)
        logger.info(f"[{req_id}] OCR successful for user {user_id}, found {len(ocr_result.positions)} positions")
        
        # Шаг 4: Сопоставление с продуктами
        # Загрузка базы продуктов
        products = data_loader.load_products("data/base_products.csv")
        
        # Сопоставляем позиции
        match_results = matcher.match_positions(ocr_result.positions, products)
        
        # Сохраняем данные в user_matches для доступа в других обработчиках
        user_matches[(user_id, progress_msg_id)] = {
            "parsed_data": ocr_result,
            "match_results": match_results,
            "photo_id": photo_id,
            "req_id": req_id
        }
        
        # Обновляем статус стадии
        update_stage("matching", kwargs, update_progress_message)
        logger.info(f"[{req_id}] Matching complete for user {user_id}")
        
        # Шаг 5: Формирование отчета
        # Создаем отчет
        report = build_report(ocr_result, match_results)
        
        # Строим клавиатуру для редактирования
        keyboard_rows = []
        edit_needed = False
        
        for idx, pos in enumerate(match_results):
            if pos["status"] != "ok":
                edit_needed = True
                keyboard_rows.append([
                    InlineKeyboardButton(text=f"✏️ Ред. {idx+1}: {pos['name'][:15]}", callback_data=f"edit:{idx}")
                ])
        
        if keyboard_rows:
            keyboard_rows.append([
                InlineKeyboardButton(
                    text="✅ Подтвердить", callback_data="confirm:invoice"
                ),
                InlineKeyboardButton(
                    text="🚫 Отмена", callback_data="cancel:all"
                )
            ])
            inline_kb = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
        else:
            # Если все позиции OK, добавляем только кнопку подтверждения
            inline_kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text="✅ Подтвердить", callback_data="confirm:invoice"
                )
            ]])
        
        # Обновляем статус стадии
        update_stage("report", kwargs, update_progress_message)
        
        # Отображаем финальный отчет
        await safe_edit(
            bot,
            message.chat.id,
            progress_msg_id,
            escape_v2(report),
            kb=inline_kb,
            parse_mode="MarkdownV2"
        )
        
        # Добавляем подсказку при необходимости редактирования
        if edit_needed:
            await message.answer(
                "⚠️ Некоторые позиции не удалось определить. Используйте кнопки «Ред.» для корректировки.",
                parse_mode=None
            )
        
        # Обновляем состояние пользователя
        await state.set_state(NotaStates.editing)
        logger.info(f"[{req_id}] Invoice processing complete for user {user_id}")
            
    except Exception as e:
        # Обработка исключений делегируется декоратору with_progress_stages
        # Он автоматически определит, на какой стадии произошла ошибка
        # и вернет пользователю дружественное сообщение
        
        # Удаляем сообщение о прогрессе, так как будет показано сообщение об ошибке
        try:
            await bot.delete_message(message.chat.id, progress_msg_id)
        except Exception:
            pass
            
        # Пробрасываем ошибку дальше для обработки декоратором
        raise


async def handle_nlu_text(message, state: FSMContext):
    text = message.text
    chat_id = message.chat.id
    msg_id = message.message_id
    
    # Send "thinking" status
    processing_msg = await message.answer("🤔 Processing your request...")
    
    try:
        # Получаем данные состояния пользователя
        user_data = await state.get_data()
        
        # Проверяем, есть ли thread_id в состоянии
        if "assistant_thread_id" not in user_data:
            # Создаем новый поток для ассистента
            from openai import OpenAI
            from app.config import get_chat_client
            
            client = get_chat_client()
            if not client:
                client = OpenAI(api_key=settings.OPENAI_CHAT_KEY)
                
            thread = client.beta.threads.create()
            # Сохраняем thread_id в состоянии пользователя
            await state.update_data(assistant_thread_id=thread.id)
            assistant_thread_id = thread.id
            logger.info(f"Created new assistant thread for user {message.from_user.id}")
        else:
            # Используем существующий thread_id
            assistant_thread_id = user_data["assistant_thread_id"]
            
        # Pass user message to Assistant with timeout handling
        assistant_response = await ask_assistant(assistant_thread_id, text)
        
        # Try to extract JSON-tool-call edit_line
        try:
            data = json.loads(assistant_response)
            if isinstance(data, dict) and data.get('tool_call') == 'edit_line':
                # Apply edit_line logic here (update local state, etc.)
                # For now, just acknowledge
                await safe_edit(
                    bot, chat_id, msg_id,
                    escape_v2("Изменения применены (edit_line)"),
                    parse_mode=ParseMode.MARKDOWN_V2
                )
                await state.set_state(NotaStates.editing)
                await bot.delete_message(chat_id, processing_msg.message_id)
                return
        except json.JSONDecodeError:
            # Not JSON data, continue with text response
            pass
            
        # Otherwise, reply with assistant's text
        await safe_edit(
            bot, chat_id, msg_id,
            escape_v2(assistant_response),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        await state.set_state(NotaStates.editing)
        
    except Exception as e:
        logger.error(f"Assistant error: {e}", exc_info=True)
        await safe_edit(
            bot, chat_id, msg_id,
            escape_v2(f"Sorry, I couldn't process that request. Error: {str(e)}"),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        
    finally:
        # Clean up processing message
        try:
            await bot.delete_message(chat_id, processing_msg.message_id)
        except Exception:
            pass



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



from app.utils.api_decorators import with_async_retry_backoff

@with_async_retry_backoff(max_retries=2, initial_backoff=1.0, backoff_factor=2.0)
async def handle_field_edit(message, state: FSMContext):
    """
    Обрабатывает редактирование полей инвойса с использованием ассистента.
    Использует декоратор with_async_retry_backoff для автоматической обработки ошибок.
    """
    data = await state.get_data()
    idx = data.get("edit_idx")
    field = data.get("edit_field")
    msg_id = data.get("msg_id")
    if idx is None or field is None or msg_id is None:
        logger.warning("Missing required field edit data in state")
        return
    
    user_id = message.from_user.id
    key = (user_id, msg_id)
    if key not in user_matches:
        logger.warning(f"No matches found for user {user_id}, message {msg_id}")
        return
    
    entry = user_matches[key]
    text = message.text.strip()
    
    # Получаем thread_id из состояния
    user_data = await state.get_data()
    
    if "assistant_thread_id" not in user_data:
        # Создаем новый поток если не существует
        from openai import OpenAI
        from app.config import get_chat_client
        
        client = get_chat_client()
        if not client:
            client = OpenAI(api_key=settings.OPENAI_CHAT_KEY)
            
        thread = client.beta.threads.create()
        await state.update_data(assistant_thread_id=thread.id)
        assistant_thread_id = thread.id
        logger.info(f"Created new assistant thread for field edit (user {user_id})")
    else:
        assistant_thread_id = user_data["assistant_thread_id"]
    
    # Показываем пользователю, что обрабатываем запрос
    processing_msg = await message.answer("🔄 Processing edit...")
    
    try:
        # Отправляем запрос ассистенту с использованием нового декоратора
        assistant_response = await ask_assistant(thread_id=assistant_thread_id, message=text)
        
        # Пробуем распарсить как JSON для tool_call
        try:
            data = json.loads(assistant_response)
            if isinstance(data, dict) and data.get('tool_call') == 'edit_line':
                # Обновляем данные инвойса
                for k, v in data.get('fields', {}).items():
                    entry["match_results"][idx][k] = v
                
                # Запускаем матчер заново для обновленной строки
                products = data_loader.load_products("data/base_products.csv")
                entry["match_results"][idx] = matcher.match_positions([entry["match_results"][idx]], products)[0]
                parsed_data = entry["parsed_data"]
                report = build_report(parsed_data, entry["match_results"])
                
                await safe_edit(
                    bot,
                    message.chat.id,
                    msg_id,
                    escape_v2(report),
                    kb=kb_report(entry["match_results"]),
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
                await state.set_state(NotaStates.editing)
                return
        except json.JSONDecodeError:
            # Не JSON, продолжаем как с обычным текстом
            pass
            
        # Отвечаем текстом от ассистента
        await safe_edit(
            bot,
            message.chat.id,
            msg_id,
            escape_v2(assistant_response),
            kb=kb_report(entry["match_results"]),
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        await state.set_state(NotaStates.editing)
        
    finally:
        # Удаляем сообщение о загрузке
        try:
            await bot.delete_message(message.chat.id, processing_msg.message_id)
        except Exception:
            pass



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


async def text_fallback(message):
    await message.answer("📸 Please send an invoice photo (image only).", parse_mode=None)


# Silence unhandled update logs
async def _dummy(update, data):
    pass


logging.getLogger("aiogram.event").setLevel(logging.DEBUG)


from aiogram.filters import CommandStart
from aiogram.enums import ParseMode
from aiogram import F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from app.keyboards import kb_main, kb_upload, kb_help_back, kb_report, kb_field_menu

# Remove duplicate NotaStates class
# In-memory store for user sessions: {user_id: {msg_id: {...}}}
user_matches = {}

# Removed duplicate safe_edit function

async def text_fallback(message):
    await message.answer("📸 Please send an invoice photo (image only).", parse_mode=None)


if __name__ == "__main__":
    async def main():
        global bot, dp
        bot, dp = create_bot_and_dispatcher()
        register_handlers(dp, bot)
        await dp.start_polling(bot)
    asyncio.run(main())