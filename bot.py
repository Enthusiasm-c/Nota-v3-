import asyncio
import concurrent.futures
import logging
import re
import os
from app.formatters.report import build_report
import atexit
import uuid
import json
import time
import shutil
from typing import Dict, Any
from pathlib import Path
import signal
import sys
from json_trace_logger import setup_json_trace_logger
from app.handlers.tracing_log_middleware import TracingLogMiddleware
import argparse
from app.utils.file_manager import cleanup_temp_files, ensure_temp_dirs

# Aiogram импорты
from aiogram import Bot, Dispatcher, F
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command, CommandStart
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramBadRequest
from aiogram.enums import ParseMode
from aiogram.types import CallbackQuery, InlineKeyboardMarkup

# Импортируем состояния
from app.fsm.states import EditFree, NotaStates

# Импорты приложения
from app import ocr, matcher, data_loader
from app.utils.md import escape_html, clean_html
from app.config import settings

# Импортируем обработчики для свободного редактирования
from app.handlers.edit_flow import router as edit_flow_router

# Import optimized logging configuration
from app.utils.logger_config import configure_logging, get_buffered_logger

# Configure logging with optimized settings
configure_logging(environment=os.getenv("ENV", "development"), log_dir="logs")

# Get buffered logger for this module
logger = get_buffered_logger(__name__)

# Create tmp dir if not exists
TMP_DIR = Path("tmp")
TMP_DIR.mkdir(exist_ok=True)

# Создаем все временные директории при запуске
ensure_temp_dirs()

async def periodic_cleanup():
    """Периодически очищает старые временные файлы."""
    while True:
        try:
            cleanup_count = await asyncio.to_thread(cleanup_temp_files)
            if cleanup_count > 0:
                print(f"Periodic cleanup: removed {cleanup_count} old temp files")
        except Exception as e:
            print(f"Error during periodic cleanup: {e}")
        await asyncio.sleep(3600)  # 1 час

def cleanup_tmp():
    try:
        shutil.rmtree(TMP_DIR)
        TMP_DIR.mkdir(exist_ok=True)
        logger.info("Cleaned up tmp directory.")
    except Exception as e:
        logger.error(f"Failed to clean tmp/: {e}")


atexit.register(cleanup_tmp)


def create_bot_and_dispatcher():
    setup_json_trace_logger()
    storage = MemoryStorage()
    # Исправлено для совместимости с aiogram 3.7.0+
    from aiogram.client.default import DefaultBotProperties
    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=storage)
    dp.message.middleware(TracingLogMiddleware())
    dp.callback_query.middleware(TracingLogMiddleware())
    # Регистрация роутеров теперь только в register_handlers
    return bot, dp


# Глобальные bot и dp убраны для тестируемости.
bot = None
dp = None
# Глобальный кэш для отредактированных сообщений
_edit_cache: Dict[str, Dict[str, Any]] = {}
# assistant_thread_id убран из глобальных переменных и перенесен в FSMContext


user_matches = {}


def is_inline_kb(kb):
    return kb is None or isinstance(kb, InlineKeyboardMarkup)


# Import the optimized version of safe_edit
from app.utils.optimized_safe_edit import optimized_safe_edit

async def safe_edit(bot, chat_id, msg_id, text, kb=None, **kwargs):
    """
    Безопасное редактирование сообщения с обработкой ошибок форматирования.
    Использует оптимизированную реализацию с кэшированием и обработкой ошибок.
    
    Args:
        bot: Экземпляр бота
        chat_id: ID чата
        msg_id: ID сообщения для редактирования
        text: Текст сообщения
        kb: Клавиатура (опционально)
        **kwargs: Дополнительные параметры для edit_message_text
    """
    # Не экранируем HTML-теги, если используется HTML режим
    # Экранируем только для Markdown
    parse_mode = kwargs.get("parse_mode")
    if parse_mode in ("MarkdownV2", ParseMode.MARKDOWN_V2) and not (
        text and text.startswith("\\")
    ):
        text = escape_html(text)
    
    # Вызываем оптимизированную версию функции
    return await optimized_safe_edit(bot, chat_id, msg_id, text, kb, **kwargs)


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
        return (
            "Sorry, the assistant is unavailable at the moment. Please try again later."
        )

    # Add the user's message to the thread
    client.beta.threads.messages.create(
        thread_id=thread_id, role="user", content=message
    )

    # Run the assistant on the thread
    run = client.beta.threads.runs.create(
        thread_id=thread_id, assistant_id=settings.OPENAI_ASSISTANT_ID
    )

    # Wait for the run to complete (with timeout)
    start_time = time.time()
    timeout = 30  # 30 seconds timeout
    while True:
        if time.time() - start_time > timeout:
            # Timeout error - raise exception to trigger retry in decorator
            raise RuntimeError("The assistant took too long to respond.")

        run_status = client.beta.threads.runs.retrieve(
            thread_id=thread_id, run_id=run.id
        )

        if run_status.status == "completed":
            # Success path
            # Get the latest message from the assistant
            messages = client.beta.threads.messages.list(thread_id=thread_id)

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
            raise RuntimeError(
                f"Assistant response failed with status: {run_status.status}"
            )

        await asyncio.sleep(1)  # Poll every second


async def cb_select_language(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора языка"""
    lang = callback.data.split(":")[1]
    
    # Сохраняем язык в состоянии пользователя
    await state.update_data(lang=lang)
    
    # Переходим в главное меню
    await state.set_state(NotaStates.main_menu)
    
    # Отправляем приветствие на выбранном языке
    from app.i18n import t
    await callback.message.edit_text(
        t("status.welcome", lang=lang),
        reply_markup=kb_main(lang)
    )
    
    await callback.answer()

def register_handlers(dp, bot=None):
    dp["__unhandled__"] = _dummy
    logging.getLogger("aiogram.event").setLevel(logging.DEBUG)
    dp.message.register(cmd_start, CommandStart())
    dp.callback_query.register(cb_select_language, F.data.startswith("lang:"))  # Добавлен обработчик выбора языка
    dp.callback_query.register(cb_new_invoice, F.data == "action:new")
    # dp.message.register(photo_handler, F.photo)  # Заменено на incremental_photo_handler
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
    
    # Подключаем роутер для GPT-ассистента (только если не был зарегистрирован ранее)
    if not hasattr(dp, '_registered_routers'):
        dp._registered_routers = set()
    if 'edit_flow_router' not in dp._registered_routers:
        dp.include_router(edit_flow_router)
        dp._registered_routers.add('edit_flow_router')
    
    # Подключаем роутер для улучшенного обработчика фото с IncrementalUI
    from app.handlers.incremental_photo_handler import router as incremental_photo_router
    if 'incremental_photo_router' not in dp._registered_routers:
        dp.include_router(incremental_photo_router)
        dp._registered_routers.add('incremental_photo_router')
        
    # Подключаем роутер для административных команд
    from app.handlers import admin_router
    if 'admin_router' not in dp._registered_routers:
        dp.include_router(admin_router)
        dp._registered_routers.add('admin_router')
    
    # Включаем обработчики fuzzy matching (ранее были отключены)
    # dp.message.register(handle_free_edit_text, EditFree.awaiting_input)  # Остается закомментированным
    dp.callback_query.register(confirm_fuzzy_name, F.data.startswith("fuzzy:confirm:"))
    dp.callback_query.register(reject_fuzzy_name, F.data.startswith("fuzzy:reject:"))


# Remove any handler registration from the module/global scope.

__all__ = ["create_bot_and_dispatcher", "register_handlers"]


from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

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

    # Создаем клавиатуру выбора языка
    lang_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇬🇧 English", callback_data="lang:en"),
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru")
        ]
    ])
    
    await state.set_state(NotaStates.lang)
    await message.answer(
        "Hi! I'm Nota AI Bot. Choose interface language.\n\nПривет! Я Nota AI Бот. Выберите язык интерфейса.",
        reply_markup=lang_keyboard
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
    "report": "Формирование отчета",
}

from app.utils.debug_logger import ocr_logger

@with_progress_stages(stages=PHOTO_STAGES)
async def photo_handler(message, state: FSMContext, **kwargs):
    """
    Обрабатывает загруженные фото инвойсов с продвинутой обработкой ошибок.
    Использует декоратор with_progress_stages для отслеживания этапов выполнения.
    2. Загружает и анализирует фото через OCR (с таймаутом 15 секунд и подробным логированием)
    """
    user_id = message.from_user.id
    photo_id = message.photo[-1].file_id if message.photo else None
    stages = kwargs.get('_stages', {})
    stages_names = kwargs.get('_stages_names', {})
    req_id = kwargs.get('_req_id', uuid.uuid4().hex[:8])
    progress_msg = await message.answer(
        "🔄 Загрузка и анализ фото...",
        parse_mode=None
    )
    progress_msg_id = progress_msg.message_id
    async def update_progress_message(stage=None, stage_name=None, error_message=None):
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
    kwargs['_update_progress'] = update_progress_message
    try:
        file = await bot.get_file(message.photo[-1].file_id)
        img_bytes = await bot.download_file(file.file_path)
        update_stage("download", kwargs, update_progress_message)
        logger.info(f"[{req_id}] Downloaded photo from user {user_id}, size {len(img_bytes.getvalue())} bytes")
        # --- OCR с таймаутом и логированием ---
        try:
            img_size = len(img_bytes.getvalue())
            logger.info(f"[{req_id}] Запускаю OCR для фото от пользователя {user_id}, размер {img_size} байт")
            ocr_logger.info(f"[{req_id}] BOT: Начинаю OCR-обработку изображения от пользователя {user_id} с таймаутом")
            await safe_edit(
                bot, message.chat.id, progress_msg_id,
                "🔍 Распознаю текст на фото... Это может занять до 15 секунд.",
                parse_mode=None
            )
            ocr_task = asyncio.create_task(asyncio.to_thread(ocr.call_openai_ocr, img_bytes.getvalue(), _req_id=req_id))
            ocr_result = await asyncio.wait_for(ocr_task, timeout=20.0)
            update_stage("ocr", kwargs, update_progress_message)
            logger.info(f"[{req_id}] OCR successful for user {user_id}, found {len(ocr_result.positions)} positions")
            ocr_logger.info(f"[{req_id}] BOT: OCR успешно завершен с {len(ocr_result.positions)} позициями")
        except asyncio.TimeoutError:
            logger.error(f"[{req_id}] OCR timeout for user {user_id}")
            ocr_logger.error(f"[{req_id}] BOT: Таймаут OCR для пользователя {user_id}")
            await safe_edit(bot, message.chat.id, progress_msg_id,
                            "⏱️ Распознавание заняло слишком много времени. Пожалуйста, попробуйте использовать фото с лучшим освещением или контрастом.")
            return
        except Exception as ocr_err:
            error_msg = str(ocr_err)
            if "timed out" in error_msg.lower():
                error_msg = "Превышено время ожидания ответа от сервиса. Пожалуйста, попробуйте еще раз."
            logger.error(f"[{req_id}] OCR error for user {user_id}: {error_msg}")
            ocr_logger.error(f"[{req_id}] BOT: Ошибка OCR для пользователя {user_id}: {error_msg}")
            await safe_edit(bot, message.chat.id, progress_msg_id,
                           f"⚠️ Ошибка распознавания: {error_msg}")
            return
        # ... остальной код обработчика photo_handler без изменений ...

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
    """
    Обрабатывает все текстовые сообщения в зависимости от текущего состояния.
    Это может быть:
    1. Редактирование поля в инвойсе (если editing_mode='field_edit')
    2. Обычный диалог с ассистентом
    """
    # Skip empty messages
    if not message.text or not message.text.strip():
        logger.debug(f"Skipping empty message from user {message.from_user.id}")
        return
        
    text = message.text
    chat_id = message.chat.id
    user_id = message.from_user.id

    # Получаем данные состояния пользователя для определения режима
    user_data = await state.get_data()
    
    # Получаем язык пользователя
    lang = user_data.get("lang", "en")
    
    # Проверяем команды для специальной обработки
    if text and text.lower() in ["отправить фото", "send photo", "нова накладна", "новый инвойс", "new invoice"]:
        logger.info(f"Detected command to start new invoice process: '{text}'")
        # Переключаем состояние на ожидание файла для загрузки нового инвойса
        await state.set_state(NotaStates.awaiting_file)
        from app.i18n import t
        await message.answer(
            t("status.send_photo", lang=lang) or "Please send a photo of your invoice.",
            parse_mode=None
        )
        return

    # Проверяем, находимся ли мы в режиме редактирования поля
    if user_data.get("editing_mode") == "field_edit":
        logger.debug(f"BUGFIX: Handling message as field edit for user {user_id}")
        # Вызываем обработчик редактирования поля напрямую
        await handle_field_edit(message, state)
        return
    
    # Проверяем, не обрабатывается ли уже фото
    if user_data.get("processing_photo"):
        logger.warning(f"Already processing a photo for user {user_id}, ignoring text message")
        from app.i18n import t
        await message.answer(
            t("status.wait_for_processing", lang=lang) or "Please wait while I finish processing your photo.", 
            parse_mode=None
        )
        return

    # Если не в режиме редактирования, считаем запрос обычным диалогом с ассистентом
    # Отправляем индикатор обработки (используем t для мультиязычности)
    from app.i18n import t
    processing_msg = await message.answer(
        t("status.processing_request", lang=lang) or "🤔 Processing your request..."
    )

    try:
        logger.debug(
            f"BUGFIX: Processing text message as assistant dialog for user {user_id}"
        )

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
            logger.info(f"Created new assistant thread for user {user_id}")
        else:
            # Используем существующий thread_id
            assistant_thread_id = user_data["assistant_thread_id"]

        # Получаем ответ от ассистента
        assistant_response = await ask_assistant(assistant_thread_id, text)

        # Проверяем на JSON-команду
        try:
            data = json.loads(assistant_response)
            if isinstance(data, dict) and data.get("tool_call") == "edit_line":
                # Apply edit_line logic here (update local state, etc.)
                # For now, just acknowledge with NEW message
                await message.answer(
                    t("status.changes_applied", lang=lang) or "✅ Changes applied",
                    parse_mode=None
                )
                await state.set_state(NotaStates.editing)
                return
        except json.JSONDecodeError:
            # Not JSON data, continue with text response
            pass

        # Отвечаем новым сообщением
        # Не экранируем HTML-теги для HTML режима
        logger.debug("TELEGRAM OUT >>> %s", assistant_response[:300])
        logger.debug("TELEGRAM parse_mode: %s", ParseMode.HTML)
        logger.debug("TELEGRAM OUT (assistant) >>> %s", assistant_response[:500])
        try:
            await message.answer(assistant_response, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error("Telegram error (assistant): %s\nText: %s", str(e), assistant_response[:500])
            # Если ошибка с HTML-форматированием, попробуем без него
            await message.answer(assistant_response, parse_mode=None)

        # Сохраняем состояние редактирования инвойса
        await state.set_state(NotaStates.editing)

    except Exception as e:
        logger.error(f"Assistant error: {str(e)}")
        # Отправляем ошибку как новое сообщение
        await message.answer(
            t("error.request_failed", lang=lang) or "Sorry, could not process your request. Please try again.",
            parse_mode=None,
        )

    finally:
        # Удаляем сообщение о загрузке
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
    """
    Обработчик кнопки "✏️ Редактировать".
    Переводит пользователя в режим свободного редактирования.
    
    Args:
        callback: Callback запрос от нажатия кнопки
        state: Состояние FSM для пользователя
    """
    # Получаем отправителя и сообщение
    user_id = callback.from_user.id
    message_id = callback.message.message_id
    
    # Сохраняем в state message_id для дальнейшего доступа к данным инвойса
    await state.update_data(edit_msg_id=message_id)
    
    # Переходим в режим ожидания ввода свободной команды редактирования
    await state.set_state(EditFree.awaiting_input)
    
    # Отправляем сообщение с инструкцией (используя i18n)
    # Получаем язык пользователя из state
    data = await state.get_data()
    lang = data.get("lang", "en")
    
    # Делегируем обработку в edit_flow если возможно
    try:
        from app.handlers.edit_flow import handle_edit_free
        # Используем улучшенный обработчик
        await handle_edit_free(callback, state)
    except (ImportError, AttributeError):
        # Если модуль недоступен, используем старый подход
        from app.i18n import t
        await callback.message.answer(
            t("example.edit_prompt", lang=lang),
            parse_mode=ParseMode.HTML
        )
    
    # Отвечаем на callback
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
    # Разбираем данные из callback
    _, field, idx = callback.data.split(":")
    idx = int(idx)

    # Логируем для диагностики
    logger.debug(
        f"BUGFIX: Field edit callback received for field {field}, idx {idx}, message_id {callback.message.message_id}"
    )

    # Получаем пользовательский язык
    data = await state.get_data()
    lang = data.get("lang", "en")
    
    # Запрашиваем новое значение с force_reply, используя i18n
    from app.i18n import t
    reply_msg = await callback.message.bot.send_message(
        callback.from_user.id,
        t("example.enter_field_value", {"field": field, "line": idx+1}, lang=lang),
        reply_markup={"force_reply": True},
        parse_mode=ParseMode.HTML
    )

    # Логируем ID созданного сообщения
    logger.debug(f"BUGFIX: Force reply message created with ID {reply_msg.message_id}")

    # Сохраняем контекст в FSM для последующей обработки
    await state.update_data(
        edit_idx=idx,
        edit_field=field,
        msg_id=callback.message.message_id,
        # Важно: отмечаем, что мы находимся в процессе редактирования поля
        # Это поможет правильно маршрутизировать ответ пользователя
        editing_mode="field_edit",
    )

    # Отвечаем на callback чтобы убрать индикатор загрузки
    await callback.answer()


from app.utils.api_decorators import with_async_retry_backoff


@with_async_retry_backoff(max_retries=2, initial_backoff=1.0, backoff_factor=2.0)
async def handle_field_edit(message, state: FSMContext):
    """
    Обрабатывает редактирование полей инвойса с использованием ассистента.
    Использует декоратор with_async_retry_backoff для автоматической обработки ошибок.
    """
    logger.debug(f"BUGFIX: Starting field edit handler for user {message.from_user.id}")

    # Получаем данные из состояния
    data = await state.get_data()
    idx = data.get("edit_idx")
    field = data.get("edit_field")
    msg_id = data.get("msg_id")

    # ВАЖНО: очищаем режим редактирования, чтобы следующие сообщения обрабатывались как обычные
    await state.update_data(editing_mode=None)
    logger.debug(f"BUGFIX: Cleared editing_mode in state")

    if idx is None or field is None or msg_id is None:
        logger.warning(
            f"Missing required field edit data in state: idx={idx}, field={field}, msg_id={msg_id}"
        )
        await message.answer("Ошибка: данные редактирования не найдены.")
        return

    user_id = message.from_user.id
    key = (user_id, msg_id)

    logger.debug(f"BUGFIX: Looking for invoice data with key {key}")
    if key not in user_matches:
        logger.warning(f"No matches found for user {user_id}, message {msg_id}")

        # Проверяем, может быть есть данные с другими message_id для этого пользователя
        alt_keys = [k for k in user_matches.keys() if k[0] == user_id]
        if alt_keys:
            logger.debug(f"BUGFIX: Found alternative keys for user: {alt_keys}")
            # Используем самый свежий ключ (предполагаем, что с наибольшим message_id)
            key = max(alt_keys, key=lambda k: k[1])
            logger.debug(f"BUGFIX: Using alternative key {key}")
        else:
            await message.answer("Ошибка: данные инвойса не найдены.")
            return

    entry = user_matches[key]
    text = message.text.strip()

    # Показываем пользователю, что обрабатываем запрос
    processing_msg = await message.answer("🔄 Обработка изменений...")

    try:
        logger.debug(
            f"BUGFIX: Processing field edit, text: '{text[:30]}...' (truncated)"
        )

        # Обновляем напрямую данные в инвойсе (упрощенный вариант без использования ассистента)
        # Это гарантирует, что мы сможем обработать запрос без сетевых вызовов

        # Обновляем поле напрямую
        old_value = entry["match_results"][idx].get(field, "")
        entry["match_results"][idx][field] = text
        logger.debug(f"BUGFIX: Updated {field} from '{old_value}' to '{text}'")

        # Запускаем матчер заново для обновленной строки, если нужно
        if field in ["name", "qty", "unit"]:
            products = data_loader.load_products("data/base_products.csv")
            entry["match_results"][idx] = matcher.match_positions(
                [entry["match_results"][idx]], products
            )[0]
            logger.debug(
                f"BUGFIX: Re-matched item, new status: {entry['match_results'][idx].get('status')}"
            )

        # Создаем отчет
        parsed_data = entry["parsed_data"]
        report, has_errors = build_report(parsed_data, entry["match_results"], escape_html=True)

        # Используем HTML отчет без экранирования
        formatted_report = report

        # Отправляем новое сообщение с обновленным отчетом
        logger.debug("TELEGRAM OUT >>> %s", formatted_report[:300])
        logger.debug("TELEGRAM parse_mode: %s", ParseMode.HTML)
        logger.debug("TELEGRAM OUT (report) >>> %s", formatted_report[:500])
        try:
            # Проверяем наличие потенциально опасных HTML-тегов
            from app.utils.md import clean_html
            if '<' in formatted_report and '>' in formatted_report:
                logger.debug("Detecting potential HTML formatting issues, trying to send without formatting")
                try:
                    # Пробуем сначала с HTML-форматированием 
                    result = await message.answer(
                        formatted_report,
                        reply_markup=build_edit_keyboard(True),
                        parse_mode=ParseMode.HTML,  # Используем константу из aiogram
                    )
                    logger.debug("Successfully sent message with HTML formatting")
                except Exception as html_error:
                    logger.error(f"Error sending with HTML parsing: {html_error}")
                    try:
                        # Пробуем без форматирования
                        result = await message.answer(
                            formatted_report,
                            reply_markup=build_edit_keyboard(True),
                            parse_mode=None,  # Без форматирования для безопасности
                        )
                        logger.debug("Successfully sent message without HTML parsing")
                    except Exception as format_error:
                        logger.error(f"Error sending without HTML parsing: {format_error}")
                        # Если не получилось - очищаем HTML-теги
                        clean_formatted_report = clean_html(formatted_report)
                        result = await message.answer(
                            clean_formatted_report,
                            reply_markup=build_edit_keyboard(True),
                            parse_mode=None,
                        )
                        logger.debug("Sent message with cleaned HTML")
            else:
                # Стандартный случай - пробуем с HTML
                result = await message.answer(
                    formatted_report,
                    reply_markup=build_edit_keyboard(True),
                    parse_mode=ParseMode.HTML,  # Используем константу из aiogram
                )
        except Exception as e:
            logger.error("Telegram error: %s\nText length: %d\nText sample: %s", 
                         str(e), len(formatted_report), formatted_report[:200])
            # Пытаемся отправить сообщение без форматирования и без клавиатуры
            try:
                from app.i18n import t
                data = await state.get_data()
                lang = data.get("lang", "en")
                simple_msg = t("example.edit_field_success", {"field": field, "value": text, "line": idx+1}, lang=lang)
                result = await message.answer(simple_msg, parse_mode=None)
                logger.info("Sent fallback simple message")
                return  # Выходим досрочно
            except Exception as final_e:
                logger.error(f"Final fallback message failed: {final_e}")
                raise

        # Обновляем ссылки в user_matches с новым ID сообщения
        new_msg_id = result.message_id
        try:
            new_key = (user_id, new_msg_id)
            user_matches[new_key] = entry.copy()

            # Удаляем старую запись
            if key in user_matches and key != new_key:
                del user_matches[key]

            logger.debug(f"BUGFIX: Created new report with message_id {new_msg_id}")
        except Exception as e:
            logger.error(f"BUGFIX: Error sending new report: {str(e)}")
            # Отправляем простое подтверждение с использованием i18n
            from app.i18n import t
            data = await state.get_data()
            lang = data.get("lang", "en")
            await message.answer(
                t("example.edit_field_success", {"field": field, "value": text, "line": idx+1}, lang=lang),
                parse_mode=None,
            )

    except Exception as e:
        logger.error(f"Error handling field edit: {str(e)}")
        await message.answer(
            f"Ошибка при обработке изменений. Пожалуйста, попробуйте еще раз."
        )

    finally:
        # Удаляем сообщение о загрузке
        try:
            await bot.delete_message(message.chat.id, processing_msg.message_id)
        except Exception:
            pass

        # Возвращаемся в режим редактирования инвойса
        await state.set_state(NotaStates.editing)


async def cb_confirm(callback: CallbackQuery, state: FSMContext):
    # Делегируем обработку в специализированный обработчик
    from app.handlers.syrve_handler import handle_invoice_confirm
    
    # Используем реальную интеграцию с Syrve
    await handle_invoice_confirm(callback, state)


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
    report, has_errors = build_report(parsed_data, match_results)
    await message.reply(f"✏️ Updated line {idx+1}.\n" + report)
    
#     
# from app.edit.free_parser import detect_intent, apply_edit
# from app.keyboards import build_main_kb
# from rapidfuzz import process as fuzzy_process
# 
# 
# # Функция перенесена в app/handlers/edit_flow.py
# # async def handle_free_edit_text(message: types.Message, state: FSMContext):
# #     """
# #     Обработчик текстовых сообщений в режиме свободного редактирования.
# #     Парсит команду и применяет соответствующее изменение к инвойсу.
# #     
# #     Args:
# #         message: Сообщение с командой редактирования
# #         state: Состояние FSM для пользователя
# #     """
# #     text = message.text.strip()
# #     user_id = message.from_user.id
# #     
# #     # Проверка на команду отмены
# #     if text.lower() in ["отмена", "cancel"]:
# #         await state.set_state(NotaStates.editing)
# #         await message.answer("Редактирование отменено")
# #         return
# #     
# #     # Получаем данные из state
# #     data = await state.get_data()
# #     edit_msg_id = data.get("edit_msg_id")
# #     
# #     if not edit_msg_id:
# #         await message.answer("Ошибка: данные инвойса не найдены.")
# #         await state.set_state(NotaStates.editing)
# #         return
# #         
# #     # Получаем данные инвойса
# #     key = (user_id, edit_msg_id)
#     
# #     if key not in user_matches:
# #         # Попробуем найти по user_id, если нет точного ключа
# #         alt_keys = [k for k in user_matches.keys() if k[0] == user_id]
# #         if alt_keys:
# #             key = max(alt_keys, key=lambda k: k[1])
# #         else:
# #             await message.answer("Ошибка: данные инвойса не найдены.")
# #             await state.set_state(NotaStates.editing)
# #             return
# #     
# #     entry = user_matches[key]
# #     
# #     # Определяем намерение пользователя
# #     intent = detect_intent(text)
#     
#     # Если это редактирование имени (name), проверяем fuzzy match
#     if intent["action"] == "edit_line_field" and intent["field"] in ["name", "имя"]:
#         field_value = intent["value"]
#         line_idx = intent["line"] - 1
#         
#         # Загружаем базу продуктов
#         products = data_loader.load_products("data/base_products.csv")
#         
#         # Ищем ближайшее совпадение с порогом 0.82 (82%)
#         product_names = [p.name for p in products]
#         best_match, score = None, 0
#         
#         if product_names:
#             result = fuzzy_process.extractOne(field_value, product_names)
#             if result is not None:
#                 best_match, score = result[0], result[1]
#             else:
#                 best_match, score = None, 0
#         
#         # Если есть хорошее совпадение (≥82%), предлагаем пользователю подтвердить
#         if best_match and score >= 82:
#             # Сохраняем контекст для подтверждения
#             await state.update_data(
#                 fuzzy_original=field_value,
#                 fuzzy_match=best_match,
#                 fuzzy_line=line_idx,
#                 fuzzy_msg_id=edit_msg_id
#             )
#             
#             # Создаем клавиатуру для подтверждения
#             keyboard = InlineKeyboardMarkup(
#                 inline_keyboard=[
#                     [
#                         InlineKeyboardButton(
#                             text="✓ Да", callback_data=f"fuzzy:confirm:{line_idx}"
#                         ),
#                         InlineKeyboardButton(
#                             text="✗ Нет", callback_data=f"fuzzy:reject:{line_idx}"
#                         )
#                     ]
#                 ]
#             )
#             
#             # Отправляем вопрос с кнопками подтверждения
#             await message.answer(
#                 f"Наверное, вы имели в виду \"{best_match}\"?",
#                 reply_markup=keyboard
#             )
#             
#             # Переходим в состояние ожидания подтверждения
#             await state.set_state(EditFree.awaiting_free_edit)
#             return
#     
#     # Применяем изменения
#     try:
#         # Подготавливаем контекст
#         ctx = {
#             "parsed_data": entry["parsed_data"],
#             "match_results": entry["match_results"],
#             "positions": entry["match_results"]
#         }
#         
#         # Применяем изменения
#         updated_ctx = apply_edit(ctx, intent)
#         
#         # Обновляем данные
#         entry["match_results"] = updated_ctx["positions"]
#         
#         # Формируем новый отчет
#         report, has_errors = build_report(entry["parsed_data"], entry["match_results"], escape_html=True)
#         
#         # Отправляем сообщение с обновленным отчетом
#         result = await message.answer(
#             report,
#             reply_markup=build_main_kb(has_errors=has_errors),
#             parse_mode=ParseMode.HTML
#         )
#         
#         # Обновляем ссылку в user_matches с новым ID сообщения
#         new_msg_id = result.message_id
#         new_key = (user_id, new_msg_id)
#         user_matches[new_key] = entry.copy()
#         
#         # Сохраняем новый message_id в state
#         await state.update_data(edit_msg_id=new_msg_id)
#         
#         # Возвращаемся в режим обычного редактирования
#         await state.set_state(NotaStates.editing)
#         
#     except Exception as e:
#         logger.error(f"Error in free edit: {e}")
#         await message.answer(
#             f"Ошибка при редактировании: {str(e)}. Попробуйте еще раз."
#         )


from app.keyboards import build_main_kb
from app import data_loader, matcher

async def confirm_fuzzy_name(callback: CallbackQuery, state: FSMContext):
    """
    Обработчик подтверждения fuzzy-совпадения имени продукта.
    
    Args:
        callback: Callback запрос от кнопки "Да"
        state: Состояние FSM для пользователя
    """
    # Получаем данные из state
    data = await state.get_data()
    fuzzy_match = data.get("fuzzy_match")
    fuzzy_line = data.get("fuzzy_line")
    fuzzy_msg_id = data.get("fuzzy_msg_id")
    
    if not all([fuzzy_match, fuzzy_line is not None, fuzzy_msg_id]):
        await callback.message.answer("Ошибка: данные для подтверждения не найдены.")
        await state.set_state(NotaStates.editing)
        await callback.answer()
        return
    
    # Получаем ключ для доступа к данным инвойса
    user_id = callback.from_user.id
    key = (user_id, fuzzy_msg_id)
    
    if key not in user_matches:
        alt_keys = [k for k in user_matches.keys() if k[0] == user_id]
        if alt_keys:
            key = max(alt_keys, key=lambda k: k[1])
        else:
            await callback.message.answer("Ошибка: данные инвойса не найдены.")
            await state.set_state(NotaStates.editing)
            await callback.answer()
            return
    
    entry = user_matches[key]
    
    # Обновляем имя продукта
    entry["match_results"][fuzzy_line]["name"] = fuzzy_match
    
    # Загружаем базу продуктов для перепроверки совпадения
    products = data_loader.load_products("data/base_products.csv")
    
    # Перезапускаем matcher для обновленной строки
    updated_positions = matcher.match_positions(
        [entry["match_results"][fuzzy_line]], 
        products
    )
    
    if updated_positions:
        entry["match_results"][fuzzy_line] = updated_positions[0]
    
    # Формируем новый отчет
    report, has_errors = build_report(entry["parsed_data"], entry["match_results"], escape_html=True)
    
    # Отправляем сообщение с обновленным отчетом
    result = await callback.message.answer(
        report,
        reply_markup=build_main_kb(has_errors=has_errors),
        parse_mode=ParseMode.HTML
    )
    
    # Обновляем ссылку в user_matches с новым ID сообщения
    new_msg_id = result.message_id
    new_key = (user_id, new_msg_id)
    user_matches[new_key] = entry.copy()
    
    # Сохраняем новый message_id в state
    await state.update_data(edit_msg_id=new_msg_id)
    
    # Убираем клавиатуру с кнопками подтверждения
    await callback.message.edit_reply_markup(reply_markup=None)
    
    # Возвращаемся в режим обычного редактирования
    await state.set_state(NotaStates.editing)
    
    # Отвечаем на callback
    await callback.answer()


async def reject_fuzzy_name(callback: CallbackQuery, state: FSMContext):
    """
    Обработчик отклонения fuzzy-совпадения имени продукта.
    
    Args:
        callback: Callback запрос от кнопки "Нет"
        state: Состояние FSM для пользователя
    """
    # Получаем данные из state
    data = await state.get_data()
    fuzzy_original = data.get("fuzzy_original")
    fuzzy_line = data.get("fuzzy_line")
    fuzzy_msg_id = data.get("fuzzy_msg_id")
    
    if not all([fuzzy_original, fuzzy_line is not None, fuzzy_msg_id]):
        await callback.message.answer("Ошибка: данные для отклонения не найдены.")
        await state.set_state(NotaStates.editing)
        await callback.answer()
        return
    
    # Получаем ключ для доступа к данным инвойса
    user_id = callback.from_user.id
    key = (user_id, fuzzy_msg_id)
    
    if key not in user_matches:
        alt_keys = [k for k in user_matches.keys() if k[0] == user_id]
        if alt_keys:
            key = max(alt_keys, key=lambda k: k[1])
        else:
            await callback.message.answer("Ошибка: данные инвойса не найдены.")
            await state.set_state(NotaStates.editing)
            await callback.answer()
            return
    
    entry = user_matches[key]
    
    # Используем оригинальное введенное имя
    entry["match_results"][fuzzy_line]["name"] = fuzzy_original
    entry["match_results"][fuzzy_line]["status"] = "unknown"
    
    # Формируем новый отчет
    report, has_errors = build_report(entry["parsed_data"], entry["match_results"], escape_html=True)
    
    # Отправляем сообщение с обновленным отчетом
    result = await callback.message.answer(
        report,
        reply_markup=build_main_kb(has_errors=has_errors),
        parse_mode=ParseMode.HTML
    )
    
    # Обновляем ссылку в user_matches с новым ID сообщения
    new_msg_id = result.message_id
    new_key = (user_id, new_msg_id)
    user_matches[new_key] = entry.copy()
    
    # Сохраняем новый message_id в state
    await state.update_data(edit_msg_id=new_msg_id)
    
    # Убираем клавиатуру с кнопками подтверждения
    await callback.message.edit_reply_markup(reply_markup=None)
    
    # Возвращаемся в режим обычного редактирования
    await state.set_state(NotaStates.editing)
    
    # Отвечаем на callback
    await callback.answer()


async def text_fallback(message):
    await message.answer(
        "📸 Please send an invoice photo (image only).", parse_mode=None
    )


# Silence unhandled update logs
async def _dummy(update, data):
    pass


logging.getLogger("aiogram.event").setLevel(logging.DEBUG)


from app.keyboards import kb_main, kb_upload, kb_help_back

# Remove duplicate NotaStates class
# In-memory store for user sessions: {user_id: {msg_id: {...}}}
user_matches = {}

# Removed duplicate safe_edit function


async def text_fallback(message):
    await message.answer(
        "📸 Please send an invoice photo (image only).", parse_mode=None
    )


import signal
import sys
import os

def _graceful_shutdown(signum, frame):
    logger.info(f"Получен сигнал завершения ({signum}), выполняем graceful shutdown...")
    
    # Устанавливаем общий таймаут в 25 секунд для гарантированного завершения
    # даже если что-то зависнет в процессе shutdown
    def alarm_handler(signum, frame):
        logger.warning("Таймаут graceful shutdown превышен, принудительное завершение")
        sys.exit(1)
    
    # Установка обработчика сигнала и таймера
    old_alarm_handler = signal.signal(signal.SIGALRM, alarm_handler)
    old_alarm_time = signal.alarm(25)  # 25 секунд на все операции
    
    try:
        # 1. Stop background threads first
        logger.info("Останавливаем фоновые потоки...")
        try:
            # Stop the Redis cache cleanup thread
            from app.utils.redis_cache import _local_cache
            if hasattr(_local_cache, 'stop_cleanup'):
                _local_cache.stop_cleanup()
                logger.info("Поток очистки кэша остановлен")
        except Exception as thread_err:
            logger.error(f"Ошибка при остановке фоновых потоков: {thread_err}")

        # 2. Close Redis connection if it exists
        try:
            from app.utils.redis_cache import get_redis
            redis_conn = get_redis()
            if redis_conn:
                logger.info("Закрываем соединение с Redis...")
                redis_conn.close()
                logger.info("Соединение с Redis закрыто")
        except Exception as redis_err:
            logger.error(f"Ошибка при закрытии Redis: {redis_err}")

        # 3. Cancel any pending OpenAI requests and shut down thread pool
        logger.info("Отменяем запросы OpenAI API...")
        try:
            # Shutdown thread pool first to prevent new async tasks
            from app.assistants.thread_pool import shutdown_thread_pool
            loop = asyncio.get_event_loop()
            if loop.is_running():
                shutdown_task = asyncio.run_coroutine_threadsafe(shutdown_thread_pool(), loop)
                # Уменьшаем таймаут с 3 до 1.5 сек
                try:
                    shutdown_task.result(timeout=1.5)
                except (asyncio.TimeoutError, concurrent.futures.TimeoutError):
                    logger.warning("Timeout waiting for thread pool shutdown")
                except Exception as pool_err:
                    logger.error(f"Ошибка при остановке thread pool: {pool_err}")
            
            # Close the OpenAI client connection
            try:
                from app.config import get_chat_client
                client = get_chat_client()
                if client and hasattr(client, '_client') and hasattr(client._client, 'http_client'):
                    client._client.http_client.close()  # Close the underlying HTTP client
                    logger.info("HTTP клиент OpenAI закрыт")
            except Exception as client_err:
                logger.error(f"Ошибка при закрытии HTTP клиента: {client_err}")
        except Exception as openai_err:
            logger.error(f"Ошибка при остановке клиента OpenAI: {openai_err}")

        # 4. Stop the bot polling and dispatcher - критически важный шаг
        if 'dp' in globals() and dp:
            logger.info("Останавливаем диспетчер бота...")
            if hasattr(dp, '_polling'):
                dp._polling = False
            loop = asyncio.get_event_loop()
            if loop.is_running():
                try:
                    # Уменьшаем таймаут с 5 до 2 сек
                    stop_task = asyncio.run_coroutine_threadsafe(dp.stop_polling(), loop)
                    stop_task.result(timeout=2.0)
                    logger.info("Опрос Telegram API остановлен")
                except (asyncio.TimeoutError, concurrent.futures.TimeoutError):
                    logger.warning("Timeout waiting for polling to stop")
                except Exception as e:
                    logger.error(f"Ошибка при остановке опроса: {e}")

        # 5. Close event loop properly
        logger.info("Останавливаем event loop...")
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Collect and close all pending tasks
                pending = asyncio.all_tasks(loop)
                if pending:
                    logger.info(f"Отменяем {len(pending)} незавершенных задач...")
                    for task in pending:
                        if not task.done():
                            task.cancel()
                    
                    # Уменьшаем таймаут с 2 до 1 сек
                    try:
                        gather_task = asyncio.run_coroutine_threadsafe(
                            asyncio.gather(*pending, return_exceptions=True), 
                            loop
                        )
                        gather_task.result(timeout=1.0)
                    except (asyncio.TimeoutError, concurrent.futures.TimeoutError):
                        logger.warning("Timeout waiting for tasks to cancel")
                    except Exception as e:
                        logger.error(f"Ошибка при отмене задач: {e}")
                        
                # Now stop the loop
                loop.stop()
                logger.info("Event loop остановлен")
        except Exception as loop_err:
            logger.error(f"Ошибка при остановке event loop: {loop_err}")
        
        # Если loop всё ещё активен, то принудительно останавливаем его
        if loop.is_running():
            logger.warning("Event loop всё ещё активен, принудительно останавливаем...")
            loop.close()
            logger.info("Event loop принудительно остановлен")
    except Exception as e:
        logger.error(f"Ошибка при завершении: {e}")
    finally:
        # Восстанавливаем предыдущий обработчик сигнала и таймер
        signal.signal(signal.SIGALRM, old_alarm_handler)
        signal.alarm(old_alarm_time)  
        
        logger.info("Graceful shutdown завершен")
        # Гарантированное завершение процесса
        os._exit(0)

if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _graceful_shutdown)
    signal.signal(signal.SIGINT, _graceful_shutdown)

    async def main():
        # Парсинг аргументов командной строки
        parser = argparse.ArgumentParser(description='Nota Telegram Bot')
        parser.add_argument('--test-mode', action='store_true', help='Запуск в тестовом режиме для проверки зависимостей')
        args = parser.parse_args()
        
        # Тестовый режим - просто проверяем зависимости и выходим
        if args.test_mode:
            logger.info("Запущен в тестовом режиме. Проверка зависимостей:")
            logger.info("✅ Python modules loaded successfully")
            try:
                import numpy as np
                logger.info("✅ numpy imported successfully")
            except ImportError as e:
                logger.error(f"❌ Error importing numpy: {e}")
                return 1
            
            try:
                import cv2
                logger.info("✅ OpenCV imported successfully")
            except ImportError as e:
                logger.error(f"❌ Error importing OpenCV: {e}")
                return 1
            
            try:
                from PIL import Image
                logger.info("✅ Pillow imported successfully")
            except ImportError as e:
                logger.error(f"❌ Error importing Pillow: {e}")
                return 1
            
            logger.info("✅ All dependencies check passed!")
            return 0
        
        # Стандартный запуск бота
        # Создаем бота и диспетчер
        bot, dp = create_bot_and_dispatcher()
        register_handlers(dp, bot)
        
        # Проверка конфигурации логирования
        root_logger = logging.getLogger()
        logger.debug(f"Logger configuration: {len(root_logger.handlers)} handlers")
        
        # Запускаем бота сразу, не дожидаясь инициализации пула
        polling_task = asyncio.create_task(dp.start_polling(bot))
        
        # Инициализируем пул потоков OpenAI Assistant API в фоновом режиме
        async def init_openai_pool():
            try:
                from app.assistants.client import client, initialize_pool
                logger.info("Initializing OpenAI thread pool in background...")
                await initialize_pool(client)
                logger.info("OpenAI thread pool initialized successfully")
            except Exception as e:
                logger.error(f"Error initializing OpenAI pool: {e}")
        
        # Запускаем инициализацию пула в фоновом режиме
        pool_task = asyncio.create_task(init_openai_pool())
        
        # Выводим информацию о включенных оптимизациях
        logger.info("Performance optimizations enabled:")
        logger.info("✅ Non-blocking bot startup (immediate response)")
        logger.info("✅ Background OpenAI Thread pool initialization")
        logger.info("✅ Asynchronous OCR processing")
        logger.info("✅ Incremental UI updates for better UX")
        logger.info("✅ Parallel API processing")
        logger.info("✅ Fixed i18n formatting issues")
        logger.info("✅ Improved logging with duplication prevention")
        
        # Запускаем задачу периодической очистки временных файлов
        asyncio.create_task(periodic_cleanup())
        
        # Ожидаем завершения поллинга (не должно произойти до остановки бота)
        await polling_task

    asyncio.run(main())
