"""
Ядро системы редактирования для Nota-v3: общая логика обработки пользовательского ввода,
применения интентов и пересчёта отчёта для edit_flow и incremental_edit_flow.
"""

import logging
import asyncio
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from app.edit.apply_intent import apply_intent
from app.formatters import report
from app.matcher import match_positions
from app.data_loader import load_products
from app.converters import parsed_to_dict
from app.i18n import t
from app.utils.processing_guard import is_processing_edit, set_processing_edit
import traceback
import time

logger = logging.getLogger(__name__)

# Словарь для хранения блокировок редактирования по user_id
edit_locks = {}

async def process_user_edit(
    message: Message,
    state: FSMContext,
    user_text: str,
    lang: str = "en",
    send_processing=None,
    send_result=None,
    send_error=None,
    run_openai_intent=None,
    fuzzy_suggester=None,
    edit_state=None
):
    """
    Универсальная функция обработки пользовательского ввода для редактирования инвойса.
    """
    user_id = getattr(message.from_user, 'id', None)
    logger.critical("ОТЛАДКА-ЯДРО: process_user_edit вызван для user_id=%s, text='%s'" % (user_id, user_text))

    # Проверяем, не выполняется ли уже редактирование для этого пользователя
    is_processing = await is_processing_edit(user_id)
    logger.critical("ОТЛАДКА-ЯДРО: Проверка блокировки: is_processing_edit=%s, user_id=%s" % (is_processing, user_id))
    
    if is_processing:
        logger.critical("ОТЛАДКА-ЯДРО: Обнаружена блокировка на редактирование для user_id=%s" % user_id)
        if send_error:
            await send_error(t("error.edit_in_progress", lang=lang))
        return
    
    # Устанавливаем блокировку на редактирование
    await set_processing_edit(user_id, True)
    logger.critical("ОТЛАДКА-ЯДРО: Блокировка установлена для user_id=%s" % user_id)
    
    try:
        # Проверка на отмену
        if user_text.lower() in ["cancel", "отмена"]:
            logger.critical("ОТЛАДКА-ЯДРО: Обнаружена команда отмены для user_id=%s" % user_id)
            if send_result:
                await send_result(t("status.edit_cancelled", lang=lang))
            await state.set_state(None)
            await set_processing_edit(user_id, False)  # Снимаем блокировку при отмене
            return

        # Получаем данные из состояния
        data = await state.get_data()
        invoice = data.get("invoice")
        logger.critical("ОТЛАДКА-ЯДРО: Проверка наличия инвойса: %s, user_id=%s" % (bool(invoice), user_id))
        
        if not invoice:
            logger.critical("ОТЛАДКА-ЯДРО: Инвойс отсутствует для user_id=%s" % user_id)
            if send_error:
                await send_error(t("status.session_expired", lang=lang))
            await state.clear()
            await set_processing_edit(user_id, False)  # Снимаем блокировку при ошибке
            return

        # Отправляем сообщение о начале обработки
        if send_processing:
            logger.critical("ОТЛАДКА-ЯДРО: Отправляем сообщение о начале обработки")
            await send_processing(t("status.processing", lang=lang))

        # Вызов парсера интентов (сначала локальный, затем OpenAI если нужно)
        intent = None
        try:
            # Сначала пробуем использовать локальный парсер для быстрой обработки команд
            try:
                from app.parsers.local_parser import parse_command_async
                local_start_time = time.time()
                intent = await parse_command_async(user_text)
                if intent:
                    elapsed = (time.time() - local_start_time) * 1000
                    logger.critical("ОТЛАДКА-ЯДРО: Результат локального парсера (%0.1f мс): %s" % (elapsed, intent))
            except ImportError:
                logger.critical("ОТЛАДКА-ЯДРО: Локальный парсер не найден, используем OpenAI")
            except Exception as e:
                logger.critical("ОТЛАДКА-ЯДРО: Ошибка локального парсера: %s" % e)
            
            # Если локальный парсер не справился, используем OpenAI или другой внешний парсер
            if intent is None:
                if run_openai_intent:
                    logger.critical("ОТЛАДКА-ЯДРО: Используем локальный парсер для текста: '%s'" % user_text)
                    intent = await asyncio.wait_for(run_openai_intent(user_text), timeout=10.0)
                    logger.critical("ОТЛАДКА-ЯДРО: Результат локального парсера: %s" % intent)
                else:
                    from app.assistants.client import run_thread_safe_async
                    logger.critical("ОТЛАДКА-ЯДРО: Используем OpenAI для текста: '%s'" % user_text)
                    intent = await asyncio.wait_for(run_thread_safe_async(user_text), timeout=20.0)
                    logger.critical("ОТЛАДКА-ЯДРО: Результат OpenAI: %s" % intent)
        except asyncio.TimeoutError:
            logger.critical("ОТЛАДКА-ЯДРО: Таймаут парсера для user_id=%s" % user_id)
            if send_error:
                await send_error(t("error.openai_timeout", lang=lang))
            await set_processing_edit(user_id, False)  # Снимаем блокировку при ошибке
            return
        except Exception as e:
            logger.critical("ОТЛАДКА-ЯДРО: Ошибка парсера: %s" % e)
            logger.critical(traceback.format_exc())
            if send_error:
                await send_error(t("error.openai_failed", lang=lang))
            await set_processing_edit(user_id, False)  # Снимаем блокировку при ошибке
            return

        # Проверка на неизвестный интент
        if not intent:
            logger.critical("ОТЛАДКА-ЯДРО: Пустой интент получен")
            if send_error:
                await send_error(t("error.parse_command", lang=lang))
            await set_processing_edit(user_id, False)  # Снимаем блокировку при ошибке
            return
            
        if intent.get("action") == "unknown":
            error_message = intent.get("user_message", t("error.parse_command", lang=lang))
            logger.critical("ОТЛАДКА-ЯДРО: Неизвестный интент: %s" % intent)
            if send_error:
                await send_error(error_message)
            await set_processing_edit(user_id, False)  # Снимаем блокировку при ошибке
            return

        # Применяем интент к инвойсу
        logger.critical("ОТЛАДКА-ЯДРО: Применяем интент: %s" % intent)
        try:
            invoice = parsed_to_dict(invoice)
            new_invoice = apply_intent(invoice, intent)
            
            # Проверяем, что new_invoice не None
            if new_invoice is None:
                logger.critical("ОТЛАДКА-ЯДРО: apply_intent вернул None вместо инвойса")
                if send_error:
                    await send_error("Ошибка при применении изменений: инвойс не получен")
                await set_processing_edit(user_id, False)  # Снимаем блокировку при ошибке
                return
                
            logger.critical("ОТЛАДКА-ЯДРО: Интент применен, действие: %s" % intent.get('action'))
        except Exception as e:
            logger.critical("ОТЛАДКА-ЯДРО: Ошибка при применении интента: %s" % e)
            logger.critical(traceback.format_exc())
            if send_error:
                await send_error("Ошибка при применении изменений: %s" % e)
            await set_processing_edit(user_id, False)  # Снимаем блокировку при ошибке
            return

        # Пересчёт совпадений
        logger.critical("ОТЛАДКА-ЯДРО: Пересчитываем совпадения")
        products = load_products()
        
        # Дополнительная проверка на наличие позиций
        if not new_invoice.get("positions"):
            logger.critical("ОТЛАДКА-ЯДРО: В инвойсе нет позиций после применения интента")
            if send_error:
                await send_error("Ошибка: после применения изменений в инвойсе отсутствуют позиции")
            await set_processing_edit(user_id, False)  # Снимаем блокировку при ошибке
            return
            
        match_results = match_positions(new_invoice["positions"], products)
        
        # Явно считаем ошибки для более надежного определения статуса
        unknown_count = sum(1 for r in match_results if r.get("status") == "unknown")
        partial_count = sum(1 for r in match_results if r.get("status") == "partial")
        
        # Логируем для отладки
        logger.critical("ОТЛАДКА-ЯДРО: Результаты: unknown=%s, partial=%s" % (unknown_count, partial_count))
        
        # Обновляем состояние с явными счетчиками ошибок
        await state.update_data(
            invoice=new_invoice,
            unknown_count=unknown_count,
            partial_count=partial_count,
            last_edit_time=asyncio.get_event_loop().time()  # Сохраняем время последнего редактирования
        )
        logger.critical("ОТЛАДКА-ЯДРО: Состояние обновлено с новым инвойсом")
        
        # Формируем отчет
        try:
            text, has_errors = report.build_report(new_invoice, match_results)
            logger.critical("ОТЛАДКА-ЯДРО: Отчет сформирован, has_errors=%s, размер=%s" % (has_errors, len(text)))
        except Exception as e:
            logger.critical("ОТЛАДКА-ЯДРО: Ошибка при построении отчета: %s" % e)
            logger.critical(traceback.format_exc())
            if send_error:
                await send_error("Ошибка при формировании отчета: %s" % e)
            await set_processing_edit(user_id, False)  # Снимаем блокировку при ошибке
            return
        
        # Fuzzy-сопоставление
        suggestion_shown = False
        for idx, item in enumerate(match_results):
            if item.get("status") == "unknown" and fuzzy_suggester:
                try:
                    name = new_invoice["positions"][idx]["name"]
                    suggestion_shown = await fuzzy_suggester(message, state, name, idx, lang)
                    if suggestion_shown:
                        break  # Показываем только одно предложение за раз
                except Exception as e:
                    logger.warning("Ошибка при fuzzy-сопоставлении: %s" % e)

        # Если не было показано предложений, отправляем обычный отчет
        if not suggestion_shown and send_result:
            await send_result(text)

        # Снимаем блокировку после успешного завершения
        await set_processing_edit(user_id, False)
        logger.critical("ОТЛАДКА-ЯДРО: Блокировка снята для user_id=%s" % user_id)
        
        return True

    except Exception as e:
        logger.critical("ОТЛАДКА-ЯДРО: Неожиданная ошибка: %s" % e)
        logger.critical(traceback.format_exc())
        if send_error:
            await send_error(t("error.unexpected", lang=lang))
        # Снимаем блокировку при любой ошибке
        await set_processing_edit(user_id, False)
        return False
