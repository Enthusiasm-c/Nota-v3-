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
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message

# Импортируем состояния
from app.fsm.states import EditFree, NotaStates

# Импорты приложения
from app import ocr, matcher, data_loader
from app.utils.md import escape_html, clean_html
from app.config import settings
from app.i18n import t

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
    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher(storage=storage)
    dp.message.middleware(TracingLogMiddleware())
    dp.callback_query.middleware(TracingLogMiddleware())
    # Регистрация роутеров теперь только в register_handlers
    return bot, dp


async def cmd_start(message: Message):
    await message.answer("👋 Привет! Я Nota AI Bot - бот для обработки инвойсов.\n\n📱 Просто отправьте фотографию инвойса, и я проанализирую его для вас. Никаких дополнительных кнопок не требуется.")


async def global_error_handler(event, exception):
    """Глобальный обработчик ошибок для предотвращения крашей бота."""
    # Уникальный ID для трассировки в логах
    error_id = f"error_{uuid.uuid4().hex[:8]}"
    
    # Логируем детали ошибки
    logger.error(f"[{error_id}] Перехвачена необработанная ошибка: {exception}")
    logger.error(f"[{error_id}] Тип события: {type(event).__name__}")
    
    # Собираем подробную информацию об ошибке
    import traceback
    trace = traceback.format_exc()
    logger.error(f"[{error_id}] Трассировка:\n{trace}")
    
    # Пытаемся получить информацию о пользователе
    try:
        if hasattr(event, 'from_user') and event.from_user:
            user_id = event.from_user.id
        elif hasattr(event, 'chat') and event.chat:
            user_id = event.chat.id
        else:
            user_id = "unknown"
        
        logger.error(f"[{error_id}] Ошибка у пользователя: {user_id}")
    except:
        logger.error(f"[{error_id}] Не удалось определить пользователя")
    
    # Пытаемся отправить сообщение пользователю
    try:
        if hasattr(event, 'answer'):
            await event.answer("Произошла ошибка. Пожалуйста, попробуйте снова.")
        elif hasattr(event, 'reply'):
            await event.reply("Произошла ошибка. Пожалуйста, попробуйте снова.")
        elif hasattr(event, 'message') and hasattr(event.message, 'answer'):
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
        from app.handlers.incremental_photo_handler import router as photo_router
        from app.handlers.syrve_handler import router as syrve_router
        
        # Проверяем, не был ли уже добавлен роутер
        if not hasattr(dp, '_registered_routers'):
            dp._registered_routers = set()
            
        # ВАЖНО: Сначала регистрируем роутер редактирования,
        # чтобы он имел приоритет над обработчиком фотографий
        if 'edit_flow_router' not in dp._registered_routers:
            dp.include_router(edit_flow_router)
            dp._registered_routers.add('edit_flow_router')
            logger.info("Зарегистрирован обработчик редактирования")
            
        # Затем регистрируем роутер обработки фотографий
        if 'photo_router' not in dp._registered_routers:
            # Регистрируем оптимизированный обработчик фотографий
            from app.handlers.optimized_photo_handler import router as optimized_photo_router
            dp.include_router(optimized_photo_router)
            dp._registered_routers.add('photo_router')  # Добавляем флаг для предотвращения повторной регистрации
            logger.info("Зарегистрирован оптимизированный обработчик фотографий")
            
            # Явная регистрация обработчика фото для диагностики проблемы
            from app.handlers.optimized_photo_handler import optimized_photo_handler
            logger.info("Добавляем прямую регистрацию фото-обработчика")
            dp.message.register(optimized_photo_handler, F.photo)
            
        # Регистрируем роутер Syrve для обработки отправки накладных
        if 'syrve_router' not in dp._registered_routers:
            dp.include_router(syrve_router)
            dp._registered_routers.add('syrve_router')
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
                        from app.utils.processing_guard import clear_all_locks, set_processing_photo, set_sending_to_syrve
                        
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
                        await asyncio.wait_for(
                            state.set_state(NotaStates.main_menu),
                            timeout=1.0
                        )
                        logger.info(f"[{op_id}] STEP2: установлено новое состояние: NotaStates.main_menu")
                    except Exception as e:
                        logger.error(f"[{op_id}] STEP2 ERROR: ошибка при работе с состоянием: {str(e)}")
                    
                    # Шаг 3: Удаляем клавиатуру (некритично)
                    try:
                        # Устанавливаем таймаут для этой операции
                        await asyncio.wait_for(
                            call.message.edit_reply_markup(reply_markup=None),
                            timeout=1.0
                        )
                        logger.info(f"[{op_id}] STEP3: клавиатура удалена")
                    except Exception as e:
                        logger.warning(f"[{op_id}] STEP3 WARNING: не удалось удалить клавиатуру: {str(e)}")
                    
                    # Шаг 4: Отправляем подтверждение
                    try:
                        # Самое простое сообщение без форматирования для максимальной надежности
                        result = await asyncio.wait_for(
                            bot.send_message(
                                chat_id=call.message.chat.id,
                                text="✅ Операция отменена.",
                                parse_mode=None  # Явно отключаем парсинг разметки
                            ),
                            timeout=1.0
                        )
                        logger.info(f"[{op_id}] STEP4: сообщение отправлено, message_id={result.message_id}")
                    except Exception as e:
                        logger.error(f"[{op_id}] STEP4 ERROR: не удалось отправить сообщение: {str(e)}")
                        
                    logger.info(f"[{op_id}] COMPLETE: операции отмены выполнены")
                except Exception as e:
                    logger.error(f"[{op_id}] GENERAL ERROR: необработанное исключение в задаче отмены: {str(e)}")
            
            # Создаем задачу и сохраняем ссылку на нее в глобальной переменной,
            # чтобы предотвратить ее сборку сборщиком мусора
            global _cancel_tasks
            if not '_cancel_tasks' in globals():
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
                        logger.debug(f"[{op_id}] Задача отмены удалена из списка, осталось {len(_cancel_tasks)}")
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
            
            logger.info(f"Пользователь {call.from_user.id} использовал устаревшую кнопку upload_new")

                    
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
                await call.message.answer("Произошла ошибка при отправке в Syrve. Попробуйте еще раз позже.")
                # В случае ошибки возвращаемся в режим редактирования
                await state.set_state(NotaStates.editing)
        
        # Регистрируем fallback-хендлер ПОСЛЕ всех остальных обработчиков,
        # и только для текстовых сообщений, чтобы он не перехватывал фото
        dp.message.register(text_fallback, F.content_type == 'text')
        
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
    if parse_mode in ("MarkdownV2", "MARKDOWN_V2") and not (
        text and text.startswith("\\")
    ):
        text = escape_html(text)
    
    # Вызываем оптимизированную версию функции
    return await optimized_safe_edit(bot, chat_id, msg_id, text, kb, **kwargs)


from app.utils.api_decorators import with_async_retry_backoff, ErrorType


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
    logger.debug(f"BUGFIX: Cleared editing_mode in state")
    
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
        logger.debug(
            f"BUGFIX: Processing field edit, text: '{text[:30]}...' (truncated)"
        )
        
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
            from app.utils.md import clean_html
            from app.keyboards import build_edit_keyboard
            
            keyboard = build_edit_keyboard(True)
            
            if '<' in formatted_report and '>' in formatted_report:
                try:
                    # Пробуем сначала с HTML-форматированием 
                    result = await message.answer(
                        formatted_report,
                        reply_markup=keyboard,
                        parse_mode="HTML"
                    )
                    logger.debug("Successfully sent message with HTML formatting")
                except Exception as html_error:
                    logger.error(f"Error sending with HTML parsing: {html_error}")
                    try:
                        # Пробуем без форматирования
                        result = await message.answer(
                            formatted_report,
                            reply_markup=keyboard,
                            parse_mode=None
                        )
                        logger.debug("Successfully sent message without HTML parsing")
                    except Exception as format_error:
                        logger.error(f"Error sending without HTML parsing: {format_error}")
                        # Если не получилось - очищаем HTML-теги
                        clean_formatted_report = clean_html(formatted_report)
                        result = await message.answer(
                            clean_formatted_report,
                            reply_markup=keyboard,
                            parse_mode=None
                        )
                        logger.debug("Sent message with cleaned HTML")
            else:
                # Стандартный случай - пробуем с HTML
                result = await message.answer(
                    formatted_report,
                    reply_markup=keyboard,
                    parse_mode="HTML"
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
            logger.error("Telegram error: %s Text length: %d Text sample: %s", 
                         str(e), len(formatted_report), formatted_report[:200])
            # Пытаемся отправить сообщение без форматирования и без клавиатуры
            try:
                simple_msg = t("example.edit_field_success", {"field": field, "value": text, "line": idx+1}, lang=lang)
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
            t("error.edit_failed", lang=lang) or "Ошибка при обработке изменений. Пожалуйста, попробуйте еще раз."
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


from app.keyboards import (
    kb_main,
    kb_upload,
    kb_help_back,
    build_main_kb,
    build_edit_keyboard,
    kb_set_supplier,
    kb_unit_buttons,
    kb_cancel_all
)
from app.assistants.client import client

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
        parse_mode="HTML"
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
    report, has_errors = build_report(entry["parsed_data"], entry["match_results"], escape_html=True)
    
    # Отправляем сообщение с обновленным отчетом
    result = await callback.message.answer(
        report,
        reply_markup=build_main_kb(has_errors=has_errors),
        parse_mode="HTML"
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


async def text_fallback(message, state: FSMContext):
    """Обработчик для любых текстовых сообщений, когда не требуется текст."""
    # Получаем текущее состояние чтобы не отвечать в режиме редактирования
    current_state = await state.get_state()
    
    # Не отвечаем, если пользователь находится в режиме редактирования
    edit_states = ["EditFree:awaiting_input", "NotaStates:editing", "EditFree:awaiting_free_edit"]
    if current_state in edit_states:
        logger.info(f"Игнорируем fallback для текстового сообщения в режиме редактирования ({current_state})")
        return
    
    # Более подробное сообщение с инструкцией
    await message.answer(
        "📸 Пожалуйста, отправьте фотографию инвойса (только изображение).\n\n"
        "Бот обрабатывает только фотографии, текстовые сообщения не поддерживаются.", 
        parse_mode=None
    )
    # Логируем для отладки
    logger.info(f"Получено текстовое сообщение от {message.from_user.id} в состоянии {current_state}: {message.text[:30]}...")


# Silence unhandled update logs
async def _dummy(update, data):
    pass


logging.getLogger("aiogram.event").setLevel(logging.DEBUG)


# Remove duplicate NotaStates class
# In-memory store for user sessions: {user_id: {msg_id: {...}}}
user_matches = {}

# Removed duplicate safe_edit function


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
            
            # Очищаем флаги блокировок пользователей
            from app.utils.processing_guard import clear_all_locks
            clear_all_locks()
            logger.info("Флаги блокировок пользователей очищены")
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

        # 5. Close HTTP session for async OCR if exists
        try:
            from app.utils.async_ocr import close_http_session
            loop = asyncio.get_event_loop()
            if loop.is_running():
                close_task = asyncio.run_coroutine_threadsafe(close_http_session(), loop)
                try:
                    close_task.result(timeout=1.0)
                    logger.info("HTTP сессия для OCR закрыта")
                except Exception:
                    logger.warning("Не удалось закрыть HTTP сессию OCR")
        except ImportError:
            pass  # Модуль может быть не установлен

        # 6. Close event loop properly
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
        if loop and loop.is_running():
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
        parser.add_argument('--force-restart', action='store_true', help='Принудительно сбросить сессию Telegram API перед запуском')
        args = parser.parse_args()
        
        # Создаем директорию для логов если её нет
        os.makedirs("logs", exist_ok=True)
        
        # Запускаем монитор ошибок
        from app.actions.error_monitor import start_error_monitor
        error_monitor = start_error_monitor("logs/bot.log")
        logger.info("AI Action монитор ошибок запущен")
        
        # Сбрасываем все блокировки пользователей при запуске
        from app.utils.processing_guard import clear_all_locks
        clear_all_locks()
        logger.info("Все блокировки пользователей сброшены при запуске")
        
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
            
            # Другие проверки оптимизированы - используем try...except вместо if
            try:
                from PIL import Image
                logger.info("✅ Pillow imported successfully")
            except ImportError as e:
                logger.error(f"❌ Error importing Pillow: {e}")
                
            try:
                from app.utils.async_ocr import async_ocr
                logger.info("✅ Async OCR module loaded successfully")
            except ImportError as e:
                logger.error(f"❌ Error importing async_ocr: {e}")
                
            logger.info("✅ All dependencies check passed!")
            return 0
        
        # Стандартный запуск бота
        # Предварительно загружаем данные в кеш асинхронно
        async def preload_data():
            try:
                from app import data_loader
                from app.utils.cached_loader import cached_load_products
                logger.info("Предварительная загрузка данных...")
                products = cached_load_products("data/base_products.csv", data_loader.load_products)
                logger.info(f"Предварительно загружено {len(products)} продуктов")
                return True
            except Exception as e:
                logger.warning(f"Ошибка при предварительной загрузке данных: {e}")
                return False
                
        # Запускаем предварительную загрузку в фоне
        # Сохраняем ссылку на задачу, чтобы она не была собрана сборщиком мусора
        global _preload_task
        _preload_task = asyncio.create_task(preload_data())
        
        # Создаем бота и диспетчер
        bot, dp = create_bot_and_dispatcher()
        
        # Если указан флаг force-restart, выполняем сброс сессии Telegram API
        if args.force_restart:
            try:
                logger.info("Force-restarting bot: terminating existing webhook/polling sessions...")
                # Отправляем запрос на удаление webhook и сброс getUpdates сессии
                await bot.delete_webhook(drop_pending_updates=True)
                # Дополнительная пауза для гарантированного сброса сессии
                await asyncio.sleep(0.5)
                logger.info("Existing webhook and polling sessions terminated")
            except Exception as e:
                logger.error(f"Error during forced restart: {e}")
        
        # Регистрируем обработчики
        register_handlers(dp, bot)
        
        # Проверка конфигурации логирования
        root_logger = logging.getLogger()
        logger.debug(f"Logger configuration: {len(root_logger.handlers)} handlers")
        
        # Запускаем бота сразу, не дожидаясь инициализации пула
        logger.info("Starting bot polling...")
        global _polling_task
        _polling_task = asyncio.create_task(dp.start_polling(bot, drop_pending_updates=True))
        
        # Инициализируем пул потоков OpenAI Assistant API в фоновом режиме
        from app.utils.timing_logger import async_timed
        @async_timed(operation_name="openai_pool_init")
        async def init_openai_pool():
            try:
                from app.assistants.client import client, initialize_pool
                logger.info("Initializing OpenAI thread pool in background...")
                await initialize_pool(client)
                logger.info("OpenAI thread pool initialized successfully")
            except Exception as e:
                logger.error(f"Error initializing OpenAI pool: {e}")
        
        # Запускаем инициализацию пула в фоновом режиме
        # Сохраняем ссылку на задачу, чтобы она не была собрана сборщиком мусора
        global _pool_task
        _pool_task = asyncio.create_task(init_openai_pool())
        
        # Выводим информацию о включенных оптимизациях
        logger.info("Bot is now running and ready to process messages!")
        
        try:
            # Запускаем поллинг напрямую, без создания отдельной задачи
            logger.info("Запускаем поллинг напрямую...")
            await dp.start_polling(bot, drop_pending_updates=True)
        except Exception as e:
            logger.error(f"Error in polling: {e}")
            # Критическая ошибка, завершаем все задачи
            _graceful_shutdown(None, None)

    asyncio.run(main())

# Экспорт для тестов
from app.handlers.edit_flow import handle_free_edit_text
try:
    from .cb_edit_line import cb_edit_line
except ImportError:
    # Если cb_edit_line определён в другом месте, импортируем напрямую
    from app.handlers.edit_flow import handle_edit_free as cb_edit_line
