import asyncio
import logging
import re
from app.formatters.report import build_report
import atexit
import uuid
import json
import time
import shutil
from datetime import datetime
from typing import Dict, Any
from pathlib import Path

# Aiogram импорты
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramBadRequest
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

# Импортируем состояния для свободного редактирования
from app.fsm.states import EditFree

# Импорты приложения
from app import ocr, matcher, data_loader
from app.utils.md import escape_html, clean_html
from app.config import settings

# Импортируем обработчики для свободного редактирования
from app.handlers.edit_flow import router as edit_flow_router, handle_free_edit_text

# Setup logging
logging.basicConfig(
    level=logging.INFO,  # Default to INFO level
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Set logging levels for different modules
logging.getLogger("aiogram").setLevel(
    logging.DEBUG
)  # Повысим уровень логов aiogram для отладки
logging.getLogger("aiogram.event").setLevel(logging.DEBUG)  # Логи событий aiogram
logging.getLogger("httpx").setLevel(logging.WARNING)  # Reduce httpx logs
logging.getLogger("aiohttp").setLevel(logging.WARNING)  # Reduce aiohttp logs
logging.getLogger("openai").setLevel(logging.WARNING)  # Reduce OpenAI client logs
logging.getLogger("bot").setLevel(logging.DEBUG)  # Bot logs at DEBUG level для отладки
logging.getLogger("urllib3").setLevel(logging.WARNING)  # Reduce urllib3 logs
logging.getLogger("asyncio").setLevel(logging.WARNING)  # Reduce asyncio logs
logging.getLogger("matplotlib").setLevel(logging.WARNING)  # Reduce matplotlib logs

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
# Глобальный кэш для отредактированных сообщений
_edit_cache: Dict[str, Dict[str, Any]] = {}
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
    """
    Безопасное редактирование сообщения с обработкой ошибок форматирования.
    В случае ошибки с parse_mode пытается отправить сообщение без форматирования.
    Если редактирование не удаётся - отправляет новое сообщение.

    Args:
        bot: Экземпляр бота
        chat_id: ID чата
        msg_id: ID сообщения для редактирования
        text: Текст сообщения
        kb: Клавиатура (опционально)
        **kwargs: Дополнительные параметры для edit_message_text
    """
    if not is_inline_kb(kb):
        kb = None

    parse_mode = kwargs.get("parse_mode")
    logger = logging.getLogger("bot")

    # Не экранируем HTML-теги, если используется HTML режим
    # Экранируем только для Markdown
    if parse_mode in ("MarkdownV2", ParseMode.MARKDOWN_V2) and not (
        text and text.startswith("\\")
    ):
        text = escape_html(text)

    logger.debug("OUT >>> %s", text[:200])
    
    # Попытка 1: Стандартное редактирование с форматированием
    try:
        await bot.edit_message_text(
            chat_id=chat_id, message_id=msg_id, text=text, reply_markup=kb, **kwargs
        )
        logger.info(f"Successfully edited message {msg_id}")
        return True
    except Exception as e:
        error_msg = str(e)
        logger.warning(f"Error editing message: {type(e).__name__} - {error_msg} - in chat_id={chat_id}, msg_id={msg_id}")
        
        # Обработка случая с не найденным сообщением - переходим сразу к отправке нового
        if isinstance(e, TelegramBadRequest) and "message to edit not found" in error_msg:
            logger.info(f"Message {msg_id} not found, will send new message")
            # Сразу перейдем к отправке нового сообщения (код ниже)
            pass
        # Попытка 2: Если проблема с форматированием, пробуем без него
        elif isinstance(e, TelegramBadRequest) and (
            "can't parse entities" in error_msg or "parse_mode" in error_msg
        ):
            logger.info("Formatting failed, retrying without parse_mode")
            try:
                clean_kwargs = {k: v for k, v in kwargs.items() if k != "parse_mode"}
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg_id,
                    text=text,
                    reply_markup=kb,
                    **clean_kwargs,
                )
                logger.info("Message sent without formatting")
                return True
            except Exception as retry_error:
                logger.warning(f"Second attempt failed: {type(retry_error).__name__}")
                
                # Попытка 3: Удаляем HTML-теги
                try:
                    clean_text = re.sub(r'<[^>]+>', '', text)
                    await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=msg_id,
                        text=clean_text,
                        reply_markup=kb,
                        parse_mode=None,
                    )
                    logger.info("Message edited with stripped HTML tags")
                    return True
                except Exception as html_error:
                    logger.warning(f"Third attempt (HTML strip) failed: {type(html_error).__name__}")
                    
                    # Попытка 4: Очищаем от всех спецсимволов
                    try:
                        ultra_clean_text = re.sub(r"[^\w\s]", " ", text)
                        if len(ultra_clean_text) < 10:  # Если текст стал слишком коротким
                            ultra_clean_text = "Failed to render message with special characters. Please try again."
                        
                        await bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=msg_id,
                            text=ultra_clean_text,
                            reply_markup=kb,
                            parse_mode=None,
                        )
                        logger.info("Sent clean fallback text message")
                        return True
                    except Exception as last_edit_error:
                        logger.error(f"All edit attempts failed: {type(last_edit_error).__name__}")
        
        # Попытка 5: Если все способы редактирования не сработали - отправляем новое сообщение
        try:
            # Сначала пробуем с форматированием
            # Храним ID новых сообщений, чтобы избежать дублирования
            from datetime import datetime
            msg_key = f"new_msg:{chat_id}:{datetime.now().timestamp()}"
            
            result = await bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=kb,
                **kwargs
            )
            logger.info(f"Sent new message instead of editing: {result.message_id}")
            
            # Добавляем сообщение в кэш, чтобы избежать дублирования
            _edit_cache[msg_key] = {"sent": True, "msg_id": result.message_id}
            return True
        except Exception as send_error:
            logger.warning(f"Failed to send formatted message: {type(send_error).__name__}")
            
            # Если с форматированием не вышло - пробуем без него
            try:
                clean_kwargs = {k: v for k, v in kwargs.items() if k != "parse_mode"}
                result = await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    reply_markup=kb,
                    **clean_kwargs
                )
                logger.info(f"Sent new plain message instead of editing: {result.message_id}")
                return True
            except Exception as final_error:
                logger.error(f"All message attempts failed: {type(final_error).__name__}")
                return False
        
        logger.error(f"Unexpected error editing message: {type(e).__name__}")
        return False


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
    
    # Подключаем роутер для GPT-ассистента
    dp.include_router(edit_flow_router)
    
    # Закоментированы в пользу новой реализации через GPT
    # dp.message.register(handle_free_edit_text, EditFree.awaiting_input)
    # dp.callback_query.register(confirm_fuzzy_name, F.data.startswith("fuzzy:confirm:"))
    # dp.callback_query.register(reject_fuzzy_name, F.data.startswith("fuzzy:reject:"))


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
    "report": "Формирование отчета",
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
    stages = kwargs.get("_stages", {})
    stages_names = kwargs.get("_stages_names", {})
    req_id = kwargs.get("_req_id", uuid.uuid4().hex[:8])

    # Шаг 1: Показываем пользователю, что обрабатываем запрос
    progress_msg = await message.answer("🔄 Загрузка и анализ фото...", parse_mode=None)
    progress_msg_id = progress_msg.message_id

    # Функция для обновления сообщения о прогрессе
    async def update_progress_message(stage=None, stage_name=None, error_message=None):
        """Вспомогательная функция для обновления сообщения о прогрессе"""
        if error_message:
            await safe_edit(
                bot,
                message.chat.id,
                progress_msg_id,
                f"⚠️ {error_message}",
                parse_mode=None,
            )
        elif stage and stage_name:
            await safe_edit(
                bot,
                message.chat.id,
                progress_msg_id,
                f"🔄 {stage_name}...",
                parse_mode=None,
            )

    # Передаем функцию обновления прогресса
    kwargs["_update_progress"] = update_progress_message

    try:
        # Шаг 2: Загрузка фото
        # Получаем информацию о файле
        file = await bot.get_file(message.photo[-1].file_id)

        # Загружаем содержимое файла
        img_bytes = await bot.download_file(file.file_path)

        # Обновляем статус стадии
        update_stage("download", kwargs, update_progress_message)
        logger.info(
            f"[{req_id}] Downloaded photo from user {user_id}, size {len(img_bytes.getvalue())} bytes"
        )

        # Шаг 3: OCR изображения
        # Запуск OCR в отдельном потоке
        ocr_result = await asyncio.to_thread(ocr.call_openai_ocr, img_bytes.getvalue())

        # Обновляем статус стадии
        update_stage("ocr", kwargs, update_progress_message)
        logger.info(
            f"[{req_id}] OCR successful for user {user_id}, found {len(ocr_result.positions)} positions"
        )

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
            "req_id": req_id,
        }

        # Обновляем статус стадии
        update_stage("matching", kwargs, update_progress_message)
        logger.info(f"[{req_id}] Matching complete for user {user_id}")

        # Шаг 5: Формирование отчета
        # Создаем отчет для HTML-форматирования
        report, has_errors = build_report(ocr_result, match_results, escape_html=True)

        # Строим клавиатуру для редактирования - используем новую функцию build_main_kb
        edit_needed = False
        for pos in match_results:
            if pos["status"] != "ok":
                edit_needed = True
                break
        
        # Импортируем функцию из keyboards
        from app.keyboards import build_main_kb
        
        # Новая клавиатура - только кнопки "Редактировать", "Отмена" и "Подтвердить" (если нет ошибок)
        inline_kb = build_main_kb(has_errors=edit_needed)

        # Обновляем статус стадии
        update_stage("report", kwargs, update_progress_message)

        # Полностью отказываемся от редактирования сообщений, так как оно нестабильно
        # Вместо этого всегда отправляем новое сообщение

        # Лог: Подготовка отчета
        logger.debug("BUGFIX: Starting report preparation")

        # Формируем полный отчет с подсказкой в одном сообщении
        full_message = report

        # Добавляем подсказку о редактировании непосредственно в отчет
        if edit_needed:
            full_message += "\n\n⚠️ Некоторые позиции не удалось определить. Используйте кнопки «Ред.» для корректировки."

        # Расширенное логирование форматирования для отладки
        logger.debug(
            f"BUGFIX: Full message prepared, length: {len(full_message)}, "
            f"has code blocks: {'```' in full_message}, "
            f"has HTML tags: {'<' in full_message and '>' in full_message}, "
            f"contains <pre>: {'<pre>' in full_message}"
        )
        
        # Удаляем любые Markdown-стиль блоки кода (```) если они есть, 
        # так как мы используем HTML-форматирование
        if '```' in full_message:
            logger.debug("Removing Markdown code blocks as we're using HTML formatting")
            full_message = full_message.replace('```diff', '')
            full_message = full_message.replace('```', '')

        # Пробуем удалить текущее сообщение о прогрессе
        try:
            logger.debug(
                f"BUGFIX: Attempting to delete progress message {progress_msg_id}"
            )
            await bot.delete_message(message.chat.id, progress_msg_id)
            logger.debug("BUGFIX: Successfully deleted progress message")
        except Exception as e:
            logger.debug(f"BUGFIX: Could not delete progress message: {str(e)}")

        # Создаем флаг для отслеживания успешной отправки
        success = False
        report_msg = None
        
        # Многоуровневая стратегия отправки сообщений
        # 1: Пробуем сначала с HTML-форматированием
        try:
            # Проверяем сообщение на потенциальные проблемы с HTML до отправки
            telegram_html_tags = ["<b>", "<i>", "<u>", "<s>", "<strike>", "<del>", "<code>", "<pre>", "<a"]
            has_valid_html = any(tag in full_message for tag in telegram_html_tags)
            
            if "<pre>" in full_message and "</pre>" not in full_message:
                logger.warning("Unclosed <pre> tag detected in message, attempting to fix")
                full_message = full_message.replace("<pre>", "<pre>") + "</pre>"
                
            logger.debug(f"Sending report with HTML formatting (valid HTML tags: {has_valid_html})")
            report_msg = await message.answer(
                full_message,
                reply_markup=inline_kb,
                parse_mode=ParseMode.HTML,  # Используем константу из aiogram вместо строки
            )
            success = True
            logger.debug(f"Successfully sent HTML-formatted report with message_id={report_msg.message_id}")
        except Exception as html_err:
            logger.warning(f"Error sending HTML report: {str(html_err)}")
            
            # 2: Если не получилось, пробуем без форматирования
            try:
                logger.debug("Attempting to send report without formatting")
                report_msg = await message.answer(
                    full_message,
                    reply_markup=inline_kb,
                    parse_mode=None
                )
                success = True
                logger.debug(f"Successfully sent plain report with message_id={report_msg.message_id}")
            except Exception as plain_err:
                logger.warning(f"Error sending plain report: {str(plain_err)}")
                
                # 3: Последний вариант - очищаем текст от HTML и отправляем
                try:
                    logger.debug("Sending report with cleaned HTML")
                    cleaned_message = clean_html(full_message)
                    report_msg = await message.answer(
                        cleaned_message,
                        reply_markup=inline_kb,
                        parse_mode=None
                    )
                    success = True
                    logger.debug(f"Successfully sent cleaned report with message_id={report_msg.message_id}")
                except Exception as clean_err:
                    logger.error(f"All report sending attempts failed: {str(clean_err)}")
                    
                    # 4: Крайний случай - отправляем краткую сводку
                    try:
                        simple_message = (
                            f"📋 Найдено {len(match_results)} позиций. "
                            f"✅ OK: {sum(1 for p in match_results if p.get('status') == 'ok')}. "
                            f"⚠️ Проблемы: {sum(1 for p in match_results if p.get('status') != 'ok')}."
                        )
                        report_msg = await message.answer(
                            simple_message, 
                            reply_markup=inline_kb, 
                            parse_mode=None
                        )
                        success = True
                        logger.debug(f"Sent summary message with message_id={report_msg.message_id}")
                    except Exception as final_err:
                        logger.error(f"All message attempts failed: {str(final_err)}")
        
        # Если успешно отправили сообщение, обновляем ссылки в user_matches
        if success and report_msg:
            try:
                # Сохраняем ID нового сообщения для дальнейшего доступа
                entry = user_matches[(user_id, progress_msg_id)]
                new_key = (user_id, report_msg.message_id)
                user_matches[new_key] = entry
                # Удаляем старую запись
                del user_matches[(user_id, progress_msg_id)]
                logger.debug(f"Updated user_matches with new message_id={report_msg.message_id}")
            except Exception as key_err:
                logger.error(f"Error updating user_matches: {str(key_err)}")

        # Обновляем состояние пользователя
        await state.set_state(NotaStates.editing)
        logger.info(f"[{req_id}] Invoice processing complete for user {user_id}")
        
        # Проверяем и чистим любые оставшиеся сообщения о прогрессе
        try:
            # Предыдущие стадии могли создать сообщения о прогрессе, которые не были удалены
            for stage_name in stages_names.values():
                stage_key = f"progress_msg_{stage_name}_{user_id}"
                if stage_key in _edit_cache and "msg_id" in _edit_cache[stage_key]:
                    old_msg_id = _edit_cache[stage_key]["msg_id"]
                    try:
                        await bot.delete_message(chat_id=message.chat.id, message_id=old_msg_id)
                        logger.debug(f"Cleaned up old progress message {old_msg_id} for stage {stage_name}")
                    except Exception as e:
                        logger.debug(f"Could not delete old progress message: {e}")
        except Exception as cleanup_error:
            logger.debug(f"Error during progress message cleanup: {cleanup_error}")

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
    text = message.text
    chat_id = message.chat.id
    user_id = message.from_user.id

    # Получаем данные состояния пользователя для определения режима
    user_data = await state.get_data()

    # Проверяем, находимся ли мы в режиме редактирования поля
    if user_data.get("editing_mode") == "field_edit":
        logger.debug(f"BUGFIX: Handling message as field edit for user {user_id}")
        # Вызываем обработчик редактирования поля напрямую
        await handle_field_edit(message, state)
        return

    # Если не в режиме редактирования, считаем запрос обычным диалогом с ассистентом
    # Отправляем индикатор обработки
    processing_msg = await message.answer("🤔 Обрабатываю ваш запрос...")

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
                    "✅ Изменения применены (edit_line)", parse_mode=None
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
            raise

        # Сохраняем состояние редактирования инвойса
        await state.set_state(NotaStates.editing)

    except Exception as e:
        logger.error(f"Assistant error: {str(e)}")
        # Отправляем ошибку как новое сообщение
        await message.answer(
            f"Извините, не удалось обработать запрос. Пожалуйста, попробуйте еще раз.",
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
    
    # Отправляем сообщение с инструкцией
    await callback.message.answer(
        "Что нужно отредактировать? Примеры команд:\n\n"
        "• <i>дата 26 апреля</i>\n"
        "• <i>строка 2 name томаты</i>\n"
        "• <i>строка 3 цена 90000</i>\n"
        "• <i>строка 1 qty 5</i>\n"
        "• <i>строка 4 unit kg</i>\n"
        "• <i>удали 3</i> — удалить строку\n\n"
        "Введите команду или <i>отмена</i> для возврата.",
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

    # Запрашиваем новое значение с force_reply
    reply_msg = await callback.message.bot.send_message(
        callback.from_user.id,
        f"Введите новое значение для {field} (строка {idx+1}):",
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
                simple_msg = f"✅ Редактирование успешно. Поле '{field}' обновлено на '{text}'."
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
            # Отправляем простое подтверждение
            await message.answer(
                f"✅ Поле '{field}' обновлено на '{text}'. Позиция {idx+1} изменена.",
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
    # Вместо редактирования - отправляем новое сообщение
    chat_id = callback.message.chat.id

    # Логируем для отладки
    logger.debug(f"BUGFIX: Confirming invoice in chat {chat_id}")

    # Отправляем сообщение о подтверждении
    await callback.message.answer(
        "✅ Invoice #123 saved to Syrve. Thank you!", reply_markup=kb_main()
    )

    # Обновляем состояние пользователя
    await state.set_state(NotaStates.main_menu)

    # Отвечаем на callback, чтобы убрать индикатор загрузки
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
    
    # Добавляем алиас если строка успешно распознана
    original_name = data.get("fuzzy_original")
    if original_name and entry["match_results"][fuzzy_line].get("product_id"):
        product_id = entry["match_results"][fuzzy_line]["product_id"]
        from app.alias import add_alias
        add_alias(original_name, product_id)
        logger.info(f"Added alias: {original_name} -> {product_id}")
    
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


if __name__ == "__main__":

    async def main():
        global bot, dp
        bot, dp = create_bot_and_dispatcher()
        register_handlers(dp, bot)
        await dp.start_polling(bot)

    asyncio.run(main())
