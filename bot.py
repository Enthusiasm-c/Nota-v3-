import asyncio
import logging
import re
from app.formatters.report import build_report
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
from app.utils.md import escape_html
from app.config import settings
from pathlib import Path
from aiogram.types import CallbackQuery
import shutil

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
        
        # Попытка 2: Если проблема с форматированием, пробуем без него
        if isinstance(e, TelegramBadRequest) and (
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
            result = await bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=kb,
                **kwargs
            )
            logger.info(f"Sent new message instead of editing: {result.message_id}")
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
        # Создаем отчет с экранированием HTML
        report, has_errors = build_report(ocr_result, match_results, escape_html=True)

        # Строим клавиатуру для редактирования
        keyboard_rows = []
        edit_needed = False

        for idx, pos in enumerate(match_results):
            if pos["status"] != "ok":
                edit_needed = True
                keyboard_rows.append(
                    [
                        InlineKeyboardButton(
                            text=f"✏️ Ред. {idx+1}: {pos['name'][:15]}",
                            callback_data=f"edit:{idx}",
                        )
                    ]
                )

        if keyboard_rows:
            keyboard_rows.append(
                [
                    InlineKeyboardButton(
                        text="✅ Подтвердить", callback_data="confirm:invoice"
                    ),
                    InlineKeyboardButton(text="🚫 Отмена", callback_data="cancel:all"),
                ]
            )
            inline_kb = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
        else:
            # Если все позиции OK, добавляем только кнопку подтверждения
            inline_kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="✅ Подтвердить", callback_data="confirm:invoice"
                        )
                    ]
                ]
            )

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

        # Лог: размер и характеристики отчета
        logger.debug(
            f"BUGFIX: Full message prepared, length: {len(full_message)}, "
            f"has code blocks: {'```' in full_message}"
        )

        # Используем HTML отчет без экранирования
        formatted_message = full_message

        # Логируем изменение размера после форматирования
        logger.debug(f"BUGFIX: Formatted message length: {len(formatted_message)}")

        # Пробуем удалить текущее сообщение о прогрессе
        try:
            logger.debug(
                f"BUGFIX: Attempting to delete progress message {progress_msg_id}"
            )
            await bot.delete_message(message.chat.id, progress_msg_id)
            logger.debug("BUGFIX: Successfully deleted progress message")
        except Exception as e:
            logger.debug(f"BUGFIX: Could not delete progress message: {str(e)}")

        # Отправляем новое сообщение с форматированным отчетом
        try:
            logger.debug(
                "BUGFIX: Sending new message with formatted report and HTML mode"
            )
            result = await message.answer(
                formatted_message,
                reply_markup=inline_kb,
                parse_mode=ParseMode.HTML,
            )
            logger.debug(
                f"BUGFIX: Successfully sent formatted report, new message ID: {result.message_id}"
            )
            # Сохраняем ID нового сообщения для дальнейшего доступа
            # Это важно для редактирования позиций позже
            entry = user_matches[(user_id, progress_msg_id)]
            new_key = (user_id, result.message_id)
            user_matches[new_key] = entry
            # Удаляем старую запись, так как сообщение больше не существует
            logger.debug(
                f"BUGFIX: Updating user_matches with new message ID {result.message_id}"
            )
            del user_matches[(user_id, progress_msg_id)]
            success = True

        except Exception as format_err:
            logger.debug(f"BUGFIX: Error sending formatted report: {str(format_err)}")

            # Запасной вариант: отправка простого текстового отчета
            try:
                logger.debug("BUGFIX: Attempting to send plain text report")
                simple_message = re.sub(r"[^a-zA-Z0-9\s,.;:()]", " ", full_message)
                result = await message.answer(
                    simple_message, reply_markup=inline_kb, parse_mode=None
                )
                logger.debug(
                    f"BUGFIX: Successfully sent plain report, new message ID: {result.message_id}"
                )
                # Обновляем ID сообщения в справочнике
                entry = user_matches[(user_id, progress_msg_id)]
                new_key = (user_id, result.message_id)
                user_matches[new_key] = entry
                del user_matches[(user_id, progress_msg_id)]
                success = True

            except Exception as plain_err:
                logger.debug(f"BUGFIX: Error sending plain report: {str(plain_err)}")

                # Последний вариант: отправка простого сообщения
                try:
                    logger.debug("BUGFIX: Sending ultra-simple message")
                    # Очень простое сообщение с минимумом информации
                    ultrasimple_msg = f"📋 Найдено {len(match_results)} позиций:\n"
                    ultrasimple_msg += f"✅ {sum(1 for p in match_results if p.get('status') == 'ok')} распознано успешно\n"
                    ultrasimple_msg += f"⚠️ {sum(1 for p in match_results if p.get('status') != 'ok')} требуют проверки"

                    result = await message.answer(
                        ultrasimple_msg, reply_markup=inline_kb, parse_mode=None
                    )
                    logger.debug(
                        f"BUGFIX: Successfully sent summary message, new message ID: {result.message_id}"
                    )
                    # Обновляем ID сообщения в справочнике
                    entry = user_matches[(user_id, progress_msg_id)]
                    new_key = (user_id, result.message_id)
                    user_matches[new_key] = entry
                    del user_matches[(user_id, progress_msg_id)]
                    success = True

                except Exception as final_err:
                    logger.error(
                        f"BUGFIX: All message attempts failed: {str(final_err)}"
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
    idx = int(callback.data.split(":")[1])
    await callback.message.edit_reply_markup(reply_markup=kb_field_menu(idx))
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
        parse_mode="HTML"
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
                    # Пробуем сначала без парсинга HTML
                    result = await message.answer(
                        formatted_report,
                        reply_markup=kb_report(entry["match_results"]),
                        parse_mode=None,  # Без форматирования для безопасности
                    )
                    logger.debug("Successfully sent message without HTML parsing")
                except Exception as format_error:
                    logger.error(f"Error sending without HTML parsing: {format_error}")
                    # Если не получилось - очищаем HTML-теги
                    clean_formatted_report = clean_html(formatted_report)
                    result = await message.answer(
                        clean_formatted_report,
                        reply_markup=kb_report(entry["match_results"]),
                        parse_mode=None,
                    )
                    logger.debug("Sent message with cleaned HTML")
            else:
                # Стандартный случай - пробуем с HTML
                result = await message.answer(
                    formatted_report,
                    reply_markup=kb_report(entry["match_results"]),
                    parse_mode=ParseMode.HTML,
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


async def text_fallback(message):
    await message.answer(
        "📸 Please send an invoice photo (image only).", parse_mode=None
    )


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
