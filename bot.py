import asyncio
import atexit
import logging
import os
import shutil
import sys
import time
import traceback
import uuid
from pathlib import Path
from typing import Any, Dict

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from app import data_loader, matcher
from app.config import settings
from app.formatters.report import build_report
from app.fsm.states import NotaStates
from app.handlers.tracing_log_middleware import TracingLogMiddleware
from app.i18n import t
from app.keyboards import build_main_kb, kb_help_back, kb_main
from app.utils.api_decorators import with_async_retry_backoff
from app.utils.file_manager import cleanup_temp_files, ensure_temp_dirs

# Import optimized logging configuration
from app.utils.logger_config import configure_logging, get_buffered_logger
from app.utils.md import escape_html
from app.utils.optimized_safe_edit import optimized_safe_edit
from json_trace_logger import setup_json_trace_logger

# Aiogram импорты

# Импортируем состояния

# Импорты приложения

# Импортируем обработчики для свободного редактирования


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
    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher(storage=storage)
    dp.message.middleware(TracingLogMiddleware())
    dp.callback_query.middleware(TracingLogMiddleware())
    # Регистрация роутеров теперь только в register_handlers
    return bot, dp


async def cmd_start(message: Message):
    await message.answer(
        "👋 Привет! Я Nota AI Bot - бот для обработки инвойсов.\n\n📱 Просто отправьте фотографию инвойса, и я проанализирую его для вас. Никаких дополнительных кнопок не требуется."
    )


async def global_error_handler(event, exception):
    """Глобальный обработчик ошибок для предотвращения крашей бота."""
    # Уникальный ID для трассировки в логах
    error_id = f"error_{uuid.uuid4().hex[:8]}"
    
    # Логируем детали ошибки
    logger.error(f"[{error_id}] Перехвачена необработанная ошибка: {exception}")
    logger.error(f"[{error_id}] Тип события: {type(event).__name__}")
    
    # Собираем подробную информацию об ошибке
    trace = traceback.format_exc()
    logger.error(f"[{error_id}] Трассировка:\n{trace}")
    
    # Пытаемся получить информацию о пользователе
    try:
        if hasattr(event, "from_user") and event.from_user:
            user_id = event.from_user.id
        elif hasattr(event, "chat") and event.chat:
            user_id = event.chat.id
        else:
            user_id = "unknown"
        
        logger.error(f"[{error_id}] Ошибка у пользователя: {user_id}")
    except AttributeError as e:
        logger.error(f"[{error_id}] Не удалось определить пользователя: {e}")
    
    # Пытаемся отправить сообщение пользователю
    try:
        if hasattr(event, "answer"):
            await event.answer("Произошла ошибка. Пожалуйста, попробуйте снова.")
        elif hasattr(event, "reply"):
            await event.reply("Произошла ошибка. Пожалуйста, попробуйте снова.")
        elif hasattr(event, "message") and hasattr(event.message, "answer"):
            await event.message.answer("Произошла ошибка. Пожалуйста, попробуйте снова.")
        
        logger.info(f"[{error_id}] Отправлено сообщение об ошибке пользователю")
    except Exception as e:
        logger.error(f"[{error_id}] Не удалось отправить сообщение об ошибке: {e}")
    
    # Ошибка обработана, бот может продолжать работу
    return True  # Предотвращаем дальнейшее распространение ошибки


def register_handlers(dp, bot=None):
    """
    Регистрирует обработчики для диспетчера.
    
    Args:
        dp: Диспетчер
        bot: Экземпляр бота (опционально)
    """
    # Регистрируем глобальный обработчик ошибок
    dp.errors.register(global_error_handler)
    
    try:
        # Импортируем роутеры
        from app.handlers.edit_flow import router as edit_flow_router
        from app.handlers.syrve_handler import router as syrve_router
        
        # Проверяем, не был ли уже добавлен роутер
        if not hasattr(dp, "_registered_routers"):
            dp._registered_routers = set()
            
        # ВАЖНО: Сначала регистрируем роутер редактирования,
        # чтобы он имел приоритет над обработчиком фотографий
        if "edit_flow_router" not in dp._registered_routers:
            dp.include_router(edit_flow_router)
            dp._registered_routers.add("edit_flow_router")
            logger.info("Зарегистрирован обработчик редактирования")
            
        # Затем регистрируем роутер обработки фотографий
        if "photo_router" not in dp._registered_routers:
            # Регистрируем оптимизированный обработчик фотографий
            from app.handlers.optimized_photo_handler import router as optimized_photo_router

            dp.include_router(optimized_photo_router)
            dp._registered_routers.add(
                "photo_router"
            )  # Добавляем флаг для предотвращения повторной регистрации
            logger.info("Зарегистрирован оптимизированный обработчик фотографий")
            
            # Явная регистрация обработчика фото для диагностики проблемы
            from app.handlers.optimized_photo_handler import optimized_photo_handler

            logger.info("Добавляем прямую регистрацию фото-обработчика")
            dp.message.register(optimized_photo_handler, F.photo)
            
        # Регистрируем роутер Syrve для обработки отправки накладных
        if "syrve_router" not in dp._registered_routers:
            dp.include_router(syrve_router)
            dp._registered_routers.add("syrve_router")
            logger.info("Зарегистрирован обработчик Syrve")
            
        # Регистрируем встроенный обработчик для кнопки cancel (еще более надежная версия)
        @dp.callback_query(F.data == "cancel:all")
        async def handle_cancel_all(call, state: FSMContext):
            """Обработчик кнопки Cancel с максимальным уровнем надежности и изоляцией операций"""
            # Используем более уникальный ID для трассировки в логах
            op_id = f"cancel_{call.message.message_id}_{int(time.time() * 1000)}"
            
            # Критично важно: быстро ответить на callback, чтобы Telegram не ждал
            # Это САМЫЙ важный шаг для предотвращения зависания интерфейса
            try:
                # Первым делом отвечаем на callback - это предотвращает зависание интерфейса
                # Устанавливаем минимальный cache_time
                await call.answer("Отмена", cache_time=1)
                print(f"[{op_id}] CRITICAL: Successfully answered callback")
                logger.info(f"[{op_id}] CRITICAL: Successfully answered callback")
            except Exception as e:
                # Если даже это не получилось - серьезная проблема, но продолжаем
                print(f"[{op_id}] CRITICAL ERROR: Failed to answer callback: {str(e)}")
                logger.error(f"[{op_id}] CRITICAL ERROR: Failed to answer callback: {str(e)}")
                
            # Создаем отдельную задачу для выполнения всех остальных операций
            # Это гарантирует, что даже если что-то зависнет, callback уже будет обработан
            async def perform_cancellation():
                try:
                    logger.info(f"[{op_id}] START: начато выполнение операций отмены")
                    
                    # Шаг 1: Очищаем все блокировки пользователя
                    user_id = call.from_user.id
                    try:
                        # Импортируем напрямую для надежности
                        from app.utils.processing_guard import (
                            clear_all_locks,
                            set_processing_photo,
                            set_sending_to_syrve,
                        )
                        
                        # Сбрасываем все возможные флаги
                        await set_processing_photo(user_id, False)
                        await set_sending_to_syrve(user_id, False)
                        # Для надежности вызываем также общий сброс
                        clear_all_locks()
                        
                        logger.info(f"[{op_id}] STEP1: все флаги блокировок пользователя сброшены")
                    except Exception as e:
                        logger.error(f"[{op_id}] STEP1 ERROR: {str(e)}")
                    
                    # Шаг 2: Сбрасываем состояние
                    try:
                        # Напрямую очищаем, чтобы гарантировать сброс
                        await state.clear()
                        logger.info(f"[{op_id}] STEP2: состояние полностью очищено")
                        
                        # Устанавливаем новое базовое состояние с коротким таймаутом
                        await asyncio.wait_for(state.set_state(NotaStates.main_menu), timeout=1.0)
                        logger.info(
                            f"[{op_id}] STEP2: установлено новое состояние: NotaStates.main_menu"
                        )
                    except Exception as e:
                        logger.error(
                            f"[{op_id}] STEP2 ERROR: ошибка при работе с состоянием: {str(e)}"
                        )
                    
                    # Шаг 3: Удаляем клавиатуру (некритично)
                    try:
                        # Устанавливаем таймаут для этой операции
                        await asyncio.wait_for(
                            call.message.edit_reply_markup(reply_markup=None), timeout=1.0
                        )
                        logger.info(f"[{op_id}] STEP3: клавиатура удалена")
                    except Exception as e:
                        logger.warning(
                            f"[{op_id}] STEP3 WARNING: не удалось удалить клавиатуру: {str(e)}"
                        )
                    
                    # Шаг 4: Отправляем подтверждение
                    try:
                        # Самое простое сообщение без форматирования для максимальной надежности
                        result = await asyncio.wait_for(
                            bot.send_message(
                                chat_id=call.message.chat.id,
                                text="✅ Операция отменена.",
                                parse_mode=None,  # Явно отключаем парсинг разметки
                            ),
                            timeout=1.0,
                        )
                        logger.info(
                            f"[{op_id}] STEP4: сообщение отправлено, message_id={result.message_id}"
                        )
                    except Exception as e:
                        logger.error(
                            f"[{op_id}] STEP4 ERROR: не удалось отправить сообщение: {str(e)}"
                        )
                        
                    logger.info(f"[{op_id}] COMPLETE: операции отмены выполнены")
                except Exception as e:
                    logger.error(
                        f"[{op_id}] GENERAL ERROR: необработанное исключение в задаче отмены: {str(e)}"
                    )
            
            # Создаем задачу и сохраняем ссылку на нее в глобальной переменной,
            # чтобы предотвратить ее сборку сборщиком мусора
            global _cancel_tasks
            if "_cancel_tasks" not in globals():
                _cancel_tasks = []
                
            # Запускаем задачу и сохраняем ссылку на нее
            cancel_task = asyncio.create_task(perform_cancellation())
            _cancel_tasks.append(cancel_task)
            
            # Регистрируем обработчик для удаления завершенных задач
            @cancel_task.add_done_callback
            def cleanup_task(task):
                try:
                    if task in _cancel_tasks:
                        _cancel_tasks.remove(task)
                        logger.debug(
                            f"[{op_id}] Задача отмены удалена из списка, осталось {len(_cancel_tasks)}"
                        )
                except Exception as e:
                    logger.error(f"[{op_id}] Ошибка при очистке задачи: {str(e)}")
            
            # Возвращаем успешный результат для предотвращения дальнейшей обработки
            return True
            
        # Регистрируем команду старт
        dp.message.register(cmd_start, CommandStart())
        
        # Обработчик для кнопки action:new больше не нужен, так как мы убрали эту кнопку из меню
        # Оставляем простую заглушку на случай, если какой-то клиент всё же отправит этот callback
        @dp.callback_query(F.data == "action:new")
        async def cb_new_invoice(call: CallbackQuery, state: FSMContext):
            """Заглушка для устаревшей кнопки Upload New Invoice"""
            # Немедленно отвечаем на callback и сообщаем, что нужно просто отправить фото
            await call.answer("Просто отправьте новое фото")
            
            # Полностью очищаем состояние и устанавливаем новое
            await state.clear()
            await state.set_state(NotaStates.awaiting_file)
            
            # Отправляем сообщение без кнопок
            await call.message.answer("📱 Просто отправьте фотографию инвойса для обработки.")
            
            logger.info(
                f"Пользователь {call.from_user.id} использовал устаревшую кнопку upload_new"
            )
                    
        # Регистрируем обработчик кнопки подтверждения инвойса
        @dp.callback_query(F.data == "confirm:invoice")
        async def handle_invoice_confirm(call: CallbackQuery, state: FSMContext):
            """Обработчик кнопки 'Подтвердить' для отправки в Syrve"""
            from app.handlers.syrve_handler import handle_invoice_confirm as syrve_handler

            try:
                # Сначала изменяем состояние
                await state.set_state(NotaStates.progress)
                # Затем вызываем обработчик
                await syrve_handler(call, state)
                # В случае успеха устанавливаем состояние главного меню
                await state.set_state(NotaStates.main_menu)
            except Exception as e:
                logger.error(f"Ошибка при обработке подтверждения инвойса: {e}")
                await call.message.answer(
                    "Произошла ошибка при отправке в Syrve. Попробуйте еще раз позже."
                )
                # В случае ошибки возвращаемся в режим редактирования
                await state.set_state(NotaStates.editing)
        
        # Регистрируем fallback-хендлер для всех сообщений (после всех остальных)
        dp.message.register(all_messages_fallback)
        
        logger.info("Все обработчики зарегистрированы успешно")
    except Exception as e:
        logger.error(f"Ошибка при регистрации обработчиков: {e}")
        # Для тестовых целей игнорируем ошибки регистрации


# Глобальные bot и dp убраны для тестируемости.
bot = None
dp = None
# Хранилище глобальных задач для предотвращения сборки мусора
_preload_task = None
_pool_task = None
_polling_task = None
# Глобальный кэш для отредактированных сообщений
_edit_cache: Dict[str, Dict[str, Any]] = {}
# assistant_thread_id убран из глобальных переменных и перенесен в FSMContext


user_matches = {}


def is_inline_kb(kb):
    return kb is None or isinstance(kb, InlineKeyboardMarkup)


# Import the optimized version of safe_edit


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
    if parse_mode in ("MarkdownV2", "MARKDOWN_V2") and not (text and text.startswith("\\")):
        text = escape_html(text)
    
    # Вызываем оптимизированную версию функции
    return await optimized_safe_edit(bot, chat_id, msg_id, text, kb, **kwargs)


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
    lang = data.get("lang", "en")  # Получаем язык пользователя
    
    # ВАЖНО: очищаем режим редактирования, чтобы следующие сообщения обрабатывались как обычные
    await state.update_data(editing_mode=None)
    logger.debug("BUGFIX: Cleared editing_mode in state")
    
    if idx is None or field is None or msg_id is None:
        logger.warning(
            f"Missing required field edit data in state: idx={idx}, field={field}, msg_id={msg_id}"
        )
        await message.answer(t("error.edit_data_not_found", lang=lang))
        return
    
    user_id = message.from_user.id
    key = (user_id, msg_id)
    
    logger.debug(f"BUGFIX: Looking for invoice data with key {key}")
    if key not in user_matches:
        logger.warning(f"No matches found for user {user_id}, message {msg_id}")
        await message.answer(t("error.invoice_data_not_found", lang=lang))
        return
    
    entry = user_matches[key]
    text = message.text.strip()
    
    # Показываем пользователю, что обрабатываем запрос
    processing_msg = await message.answer(t("status.processing_changes", lang=lang))
    
    try:
        logger.debug(f"BUGFIX: Processing field edit, text: '{text[:30]}...' (truncated)")
        
        # Обновляем напрямую данные в инвойсе
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
        try:
            # Проверяем наличие потенциально опасных HTML-тегов
            from app.keyboards import build_edit_keyboard
            from app.utils.md import clean_html
            
            keyboard = build_edit_keyboard(True)
            
            if "<" in formatted_report and ">" in formatted_report:
                try:
                    # Пробуем сначала с HTML-форматированием 
                    result = await message.answer(
                        formatted_report, reply_markup=keyboard, parse_mode="HTML"
                    )
                    logger.debug("Successfully sent message with HTML formatting")
                except Exception as html_error:
                    logger.error(f"Error sending with HTML parsing: {html_error}")
                    try:
                        # Пробуем без форматирования
                        result = await message.answer(
                            formatted_report, reply_markup=keyboard, parse_mode=None
                        )
                        logger.debug("Successfully sent message without HTML parsing")
                    except Exception as format_error:
                        logger.error(f"Error sending without HTML parsing: {format_error}")
                        # Если не получилось - очищаем HTML-теги
                        clean_formatted_report = clean_html(formatted_report)
                        result = await message.answer(
                            clean_formatted_report, reply_markup=keyboard, parse_mode=None
                        )
                        logger.debug("Sent message with cleaned HTML")
            else:
                # Стандартный случай - пробуем с HTML
                result = await message.answer(
                    formatted_report, reply_markup=keyboard, parse_mode="HTML"
                )
            
            # Обновляем ссылки в user_matches с новым ID сообщения
            new_msg_id = result.message_id
            new_key = (user_id, new_msg_id)
            user_matches[new_key] = entry.copy()
            
            # Удаляем старую запись
            if key in user_matches and key != new_key:
                del user_matches[key]
            
            logger.debug(f"BUGFIX: Created new report with message_id {new_msg_id}")
            
        except Exception as e:
            logger.error(
                "Telegram error: %s Text length: %d Text sample: %s",
                str(e),
                len(formatted_report),
                formatted_report[:200],
            )
            # Пытаемся отправить сообщение без форматирования и без клавиатуры
            try:
                simple_msg = t(
                    "example.edit_field_success",
                    {"field": field, "value": text, "line": idx + 1},
                    lang=lang,
                )
                if not simple_msg:
                    simple_msg = f"Field '{field}' updated to '{text}' for line {idx+1}"
                result = await message.answer(simple_msg, parse_mode=None)
                logger.info("Sent fallback simple message")
                return  # Выходим досрочно
            except Exception as final_e:
                logger.error(f"Final fallback message failed: {final_e}")
                try:
                    # Крайний случай - простое сообщение без i18n
                    result = await message.answer("Field updated successfully.", parse_mode=None)
                    logger.info("Sent basic fallback message")
                    return  # Выходим досрочно
                except Exception as absolutely_final_e:
                    logger.error(f"Absolutely final fallback failed: {absolutely_final_e}")
                    raise
        
    except Exception as e:
        logger.error(f"Error handling field edit: {str(e)}")
        await message.answer(
            t("error.edit_failed", lang=lang)
            or "Ошибка при обработке изменений. Пожалуйста, попробуйте еще раз."
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
    # Получаем язык пользователя
    data = await state.get_data()
    lang = data.get("lang", "en")
    
    await state.set_state(NotaStates.help)
    await message.answer(
        t("main.bot_help", lang=lang),
        reply_markup=kb_help_back(),
    )


async def cancel_command(message, state: FSMContext):
    # Получаем язык пользователя
    data = await state.get_data()
    lang = data.get("lang", "en")

    await state.set_state(NotaStates.main_menu)
    await message.answer(
        t("main.ready_to_work", lang=lang),
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
    await message.reply(f"Updated line {idx+1}.\n" + report)


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
    lang = data.get("lang", "en")  # Получаем язык пользователя
    
    if not all([fuzzy_match, fuzzy_line is not None, fuzzy_msg_id]):
        await callback.message.answer(t("error.confirm_data_not_found", lang=lang))
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
            await callback.message.answer(t("error.invoice_data_not_found", lang=lang))
            await state.set_state(NotaStates.editing)
            await callback.answer()
            return
    
    entry = user_matches[key]
    
    # Обновляем имя продукта
    entry["match_results"][fuzzy_line]["name"] = fuzzy_match
    
    # Загружаем базу продуктов для перепроверки совпадения
    products = data_loader.load_products("data/base_products.csv")
    
    # Перезапускаем matcher для обновленной строки
    updated_positions = matcher.match_positions([entry["match_results"][fuzzy_line]], products)
    
    if updated_positions:
        entry["match_results"][fuzzy_line] = updated_positions[0]
    
    # Формируем новый отчет
    report, has_errors = build_report(
        entry["parsed_data"], entry["match_results"], escape_html=True
    )
    
    # Отправляем сообщение с обновленным отчетом
    result = await callback.message.answer(
        report, reply_markup=build_main_kb(has_errors=has_errors), parse_mode="HTML"
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
    lang = data.get("lang", "en")  # Получаем язык пользователя
    
    if not all([fuzzy_original, fuzzy_line is not None, fuzzy_msg_id]):
        await callback.message.answer(t("error.reject_data_not_found", lang=lang))
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
            await callback.message.answer(t("error.invoice_data_not_found", lang=lang))
            await state.set_state(NotaStates.editing)
            await callback.answer()
            return
    
    entry = user_matches[key]
    
    # Используем оригинальное введенное имя
    entry["match_results"][fuzzy_line]["name"] = fuzzy_original
    entry["match_results"][fuzzy_line]["status"] = "unknown"
    
    # Формируем новый отчет
    report, has_errors = build_report(
        entry["parsed_data"], entry["match_results"], escape_html=True
    )
    
    # Отправляем сообщение с обновленным отчетом
    result = await callback.message.answer(
        report, reply_markup=build_main_kb(has_errors=has_errors), parse_mode="HTML"
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


async def all_messages_fallback(message, state: FSMContext):
    """Универсальный fallback для любых сообщений, даже если не сработал обычный text_fallback."""
    # Изолируем всю функцию в try-except для защиты от любых ошибок
    try:
        import re
        import traceback

        # Импортируем нужные классы состояний вначале функции
        from app.fsm.states import EditFree, NotaStates
        
        logger.critical(f"СТАРТ: all_messages_fallback вызван, тип={type(message).__name__}")
        
        # Получаем и проверяем текст сообщения
        try:
            text = getattr(message, "text", None) or ""
            user_id = getattr(message.from_user, "id", "unknown")
            logger.critical(f"СТАРТ: Текст сообщения: '{text}', user_id={user_id}")
        except Exception as e:
            logger.critical(f"ОШИБКА при получении текста: {e}")
            return
        
        # Проверяем на команду даты или редактирования строки максимально просто и надежно
        try:
            is_date_command = False
            is_line_edit_command = False
            text_lower = text.lower().strip()
            
            # Проверка на команду даты
            if text_lower.startswith("date ") or text_lower.startswith("дата "):
                is_date_command = True
            # Дополнительная проверка на формат даты без префикса (например, "25.06.2024")
            elif re.match(r"^\d{1,2}[./-]\d{1,2}[./-]\d{2,4}$", text_lower):
                is_date_command = True
                # Добавляем префикс для правильной обработки
                text = f"date {text}"
            # Распознавание команды на естественном языке для изменения даты
            elif (
                "дату на" in text_lower
                or "дата на" in text_lower
                or "изменить дату" in text_lower
                or "измени дату" in text_lower
                or "change date" in text_lower
                or "set date" in text_lower
            ):
                is_date_command = True
                # Пытаемся извлечь дату из команды
                date_match = re.search(r"(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})", text)
                if date_match:
                    extracted_date = date_match.group(1)
                    logger.critical(
                        f"СТАРТ: Извлечена дата '{extracted_date}' из команды на естественном языке"
                    )
                    # Переформатируем в стандартную команду даты
                    text = f"date {extracted_date}"
                else:
                    # Если дата не найдена, пропускаем команду напрямую в GPT-парсер
                    logger.critical(
                        f"СТАРТ: Отправляем команду изменения даты на естественном языке в GPT-парсер: '{text}'"
                    )
            
            # Проверка на команду редактирования строки
            elif re.match(r"^line\s+\d+", text_lower) or re.match(r"^строка\s+\d+", text_lower):
                is_line_edit_command = True
                logger.critical(f"СТАРТ: Обнаружена команда редактирования строки: '{text}'")
            # Распознавание других команд редактирования на естественном языке
            elif any(
                phrase in text_lower
                for phrase in [
                    "измени",
                    "изменить",
                    "поменяй",
                    "поменять",
                    "установи",
                    "установить",
                    "change",
                    "edit",
                    "update",
                    "set",
                    "modify",
                ]
            ):
                # Проверка на наличие слова "дату" для исключения дублирования с командами даты
                if not any(date_word in text_lower for date_word in ["дату", "дата", "date"]):
                    # Проверяем наличие указания на строку
                    line_match = re.search(r"строк[аеиу]\s*(\d+)", text_lower)
                    if not line_match:
                        # Проверка на английское "line X" или "row X"
                        line_match = re.search(r"(?:line|row)\s*(\d+)", text_lower)
                    
                    if line_match:
                        line_num = line_match.group(1)
                        is_line_edit_command = True
                        logger.critical(
                            f"СТАРТ: Обнаружена команда редактирования строки на естественном языке: '{text}', строка {line_num}"
                        )
                    else:
                        # Общая команда редактирования
                        is_line_edit_command = True
                        logger.critical(
                            f"СТАРТ: Обнаружена общая команда редактирования на естественном языке: '{text}'"
                        )
            
            if is_date_command:
                logger.critical(f"СТАРТ: Обнаружена команда даты: '{text}'")
            elif is_line_edit_command:
                logger.critical(f"СТАРТ: Обнаружена команда редактирования строки: '{text}'")
            else:
                # Проверяем, находится ли пользователь в режиме редактирования
                current_state = await state.get_state()
                data = await state.get_data()
                invoice = data.get("invoice")
                
                # Если пользователь в режиме редактирования и есть инвойс, 
                # то перенаправляем любой текст на GPT-парсер
                if (
                    current_state in [str(EditFree.awaiting_input), str(NotaStates.editing)]
                    and invoice
                ):
                    logger.critical(
                        f"СТАРТ: Перенаправляем неизвестную команду на GPT-парсер: '{text}'"
                    )
                    is_line_edit_command = True  # Устанавливаем флаг для перенаправления
                else:
                    logger.critical(f"СТАРТ: Не распознана команда: '{text}'")
                    return
        except Exception as e:
            logger.critical(f"ОШИБКА при проверке на команду: {e}")
            return
        
        # Если это команда даты или редактирования строки, проверяем состояние
        if is_date_command or is_line_edit_command:
            try:
                current_state = await state.get_state()
                logger.critical(f"СТАРТ: Текущее состояние: {current_state}")
            except Exception as e:
                logger.critical(f"ОШИБКА при получении состояния: {e}")
                return
            
            # Получаем данные инвойса
            try:
                data = await state.get_data()
                invoice = data.get("invoice")
                logger.critical(f"СТАРТ: Инвойс найден: {bool(invoice)}")
            except Exception as e:
                logger.critical(f"ОШИБКА при получении данных: {e}")
                return
            
            # Проверяем наличие инвойса
            if not invoice:
                try:
                    await message.answer(
                        "Не найден инвойс для редактирования. Отправьте фото или нажмите Edit снова."
                    )
                    logger.critical("СТАРТ: Инвойс отсутствует, отправлено сообщение пользователю")
                    return
                except Exception as e:
                    logger.critical(f"ОШИБКА при отправке сообщения: {e}")
                    return
            
            # Поддерживаем оба состояния: EditFree.awaiting_input и NotaStates.editing
            if current_state not in [str(EditFree.awaiting_input), str(NotaStates.editing)]:
                try:
                    logger.critical(
                        f"СТАРТ: Устанавливаем состояние EditFree.awaiting_input из {current_state}"
                    )
                    await state.set_state(EditFree.awaiting_input)
                except Exception as e:
                    logger.critical(f"ОШИБКА при установке состояния: {e}")
                    return
            
            # Если все в порядке, передаем управление обработчику редактирования
            try:
                # Перед вызовом обработчика импортируем все зависимости
                import importlib

                from app.fsm.states import EditFree, NotaStates
                
                # Пробуем использовать инкрементальный обработчик сначала
                try:
                    logger.critical("СТАРТ: Пробуем использовать incremental_edit_flow.py")
                    inc_edit_flow = importlib.import_module("app.handlers.incremental_edit_flow")
                    await inc_edit_flow.handle_free_edit_text(message, state)
                    logger.critical(
                        "СТАРТ: incremental_edit_flow.handle_free_edit_text выполнен успешно"
                    )
                    return
                except ImportError:
                    logger.critical(
                        "СТАРТ: incremental_edit_flow не найден, пробуем обычный edit_flow"
                    )
                except Exception as e:
                    logger.critical(f"ОШИБКА при вызове incremental_edit_flow: {e}")
                    logger.critical(traceback.format_exc())
                
                # Если не сработал инкрементальный - пробуем обычный
                try:
                    logger.critical("СТАРТ: Используем edit_flow.py")
                    edit_flow = importlib.import_module("app.handlers.edit_flow")
                    await edit_flow.handle_free_edit_text(message, state)
                    logger.critical("СТАРТ: edit_flow.handle_free_edit_text выполнен успешно")
                    return
                except Exception as e:
                    logger.critical(f"ОШИБКА при вызове edit_flow: {e}")
                    logger.critical(traceback.format_exc())
                    
                # Если все обработчики не сработали, показываем ошибку
                await message.answer(
                    "Произошла ошибка при обработке команды. Пожалуйста, повторите."
                )
                return
            except Exception as e:
                import traceback

                logger.critical(f"ОШИБКА при вызове обработчиков: {e}")
                logger.critical(traceback.format_exc())
                try:
                    await message.answer(
                        "Произошла ошибка при обработке команды. Пожалуйста, повторите."
                    )
                except Exception as e:
                    logger.error(f"Не удалось отправить сообщение об ошибке: {e}")
                return
    except Exception as e:
        import traceback

        logger.critical(f"ГЛОБАЛЬНАЯ ОШИБКА: {e}")
        logger.critical(traceback.format_exc())
        try:
            await message.answer("Произошла системная ошибка. Пожалуйста, повторите.")
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение о системной ошибке: {e}")
        return


# Silence unhandled update logs
async def _dummy(update, data):
    pass


logging.getLogger("aiogram.event").setLevel(logging.DEBUG)


# Remove duplicate NotaStates class
# In-memory store for user sessions: {user_id: {msg_id: {...}}}
user_matches = {}

# Removed duplicate safe_edit function


def _graceful_shutdown(signum, frame):
    """
    Gracefully shuts down the bot
    """
    logger.info("Received shutdown signal")
    cleanup_temp_files()
    sys.exit(0)


def _check_dependencies():
    """
    Проверяет наличие необходимых зависимостей
    """
    try:
        # Проверяем базовые Python модули
        logger.info("✅ Python modules loaded successfully")
                        
        # Проверяем наличие необходимых директорий
        ensure_temp_dirs()
        logger.info("✅ Temporary directories created")
        
        # Запускаем монитор ошибок
        from app.actions.error_monitor import start_error_monitor

        start_error_monitor("logs/bot.log")
        logger.info("AI Action монитор ошибок запущен")
        
        # Проверяем наличие необходимых библиотек
        try:
            logger.info("✅ Python modules loaded successfully")
            except ImportError as e:
            logger.error(f"❌ Error importing Python modules: {e}")
            return False

                return True
            except Exception as e:
        logger.error(f"❌ Error checking dependencies: {e}")
                return False
                

if __name__ == "__main__":
    # Проверяем зависимости
    if not _check_dependencies():
        logger.error("Failed to check dependencies")
        sys.exit(1)
        
        # Создаем бота и диспетчер
        bot, dp = create_bot_and_dispatcher()
        
        # Регистрируем обработчики
        register_handlers(dp, bot)
        
    # Запускаем бота
    logger.info("Starting bot...")
    asyncio.run(dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types()))
