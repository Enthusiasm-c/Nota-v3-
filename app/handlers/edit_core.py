"""
Ядро системы редактирования для Nota-v3: общая логика обработки пользовательского ввода,
применения интентов и пересчёта отчёта для edit_flow и incremental_edit_flow.
"""

import asyncio
import logging
import time
import traceback
from datetime import datetime
from typing import Dict

from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.converters import parsed_to_dict
from app.data_loader import load_products
from app.edit.apply_intent import apply_intent
from app.formatters import report
from app.i18n import t
from app.matcher import match_positions
from app.utils.processing_guard import is_processing_edit, set_processing_edit

logger = logging.getLogger(__name__)

# Блокировки для предотвращения одновременного редактирования
edit_locks: Dict[int, datetime] = {}


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
    edit_state=None,
):
    """
    Универсальная функция обработки пользовательского ввода для редактирования инвойса.
    """
    user_id = getattr(message.from_user, "id", None)
    logger.critical(
        "ОТЛАДКА-ЯДРО: process_user_edit вызван для user_id=%s, text='%s'" % (user_id, user_text)
    )

    # Проверяем, не выполняется ли уже редактирование для этого пользователя
    is_processing = await is_processing_edit(user_id)
    logger.critical(
        "ОТЛАДКА-ЯДРО: Проверка блокировки: is_processing_edit=%s, user_id=%s"
        % (is_processing, user_id)
    )

    if is_processing:
        logger.critical(
            "ОТЛАДКА-ЯДРО: Обнаружена блокировка на редактирование для user_id=%s" % user_id
        )
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
        logger.critical(
            "ОТЛАДКА-ЯДРО: Проверка наличия инвойса: %s, user_id=%s" % (bool(invoice), user_id)
        )

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
                    logger.critical(
                        "ОТЛАДКА-ЯДРО: Результат локального парсера (%0.1f мс): %s"
                        % (elapsed, intent)
                    )
            except ImportError:
                logger.critical("ОТЛАДКА-ЯДРО: Локальный парсер не найден, используем OpenAI")
                intent = None
            except Exception as e:
                logger.critical("ОТЛАДКА-ЯДРО: Ошибка локального парсера: %s" % e)
                intent = None

            # Если локальный парсер не справился или вернул unknown, используем OpenAI
            if intent is None or intent.get("action") == "unknown":
                if run_openai_intent:
                    logger.critical("ОТЛАДКА-ЯДРО: Используем OpenAI для текста: '%s'" % user_text)
                    intent = await asyncio.wait_for(run_openai_intent(user_text), timeout=10.0)
                    logger.critical("ОТЛАДКА-ЯДРО: Результат OpenAI: %s" % intent)
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

            logger.critical("ОТЛАДКА-ЯДРО: Интент применен, действие: %s" % intent.get("action"))
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

        # ИСПРАВЛЕНО: Сохраняем предыдущие результаты совпадений и пересчитываем только измененные позиции
        old_match_results = data.get("match_results", [])
        old_positions = invoice.get("positions", [])
        new_positions = new_invoice.get("positions", [])

        logger.critical(f"ОТЛАДКА-ЯДРО: len(old_match_results)={len(old_match_results)}")
        logger.critical(f"ОТЛАДКА-ЯДРО: len(old_positions)={len(old_positions)}")
        logger.critical(f"ОТЛАДКА-ЯДРО: len(new_positions)={len(new_positions)}")
        logger.critical(f"ОТЛАДКА-ЯДРО: old_match_results={old_match_results}")

        # Определяем какие позиции изменились
        changed_indices = []
        name_changed_indices = []  # Позиции где изменилось название
        for i, (old_pos, new_pos) in enumerate(zip(old_positions, new_positions)):
            # Проверяем изменения в ключевых полях (name, qty, price, unit)
            key_fields = ["name", "qty", "price", "unit"]
            changes = []
            name_changed = False
            for field in key_fields:
                old_val = old_pos.get(field)
                new_val = new_pos.get(field)
                if old_val != new_val:
                    changes.append(
                        f"{field}: '{old_val}' -> '{new_val}' (types: {type(old_val).__name__} -> {type(new_val).__name__})"
                    )
                    if field == "name":
                        name_changed = True

            if changes:
                changed_indices.append(i)
                if name_changed:
                    name_changed_indices.append(i)
                logger.critical(f"ОТЛАДКА-ЯДРО: Позиция {i+1} изменилась: {', '.join(changes)}")
            else:
                logger.critical(
                    f"ОТЛАДКА-ЯДРО: Позиция {i+1} БЕЗ изменений: qty='{old_pos.get('qty')}' == '{new_pos.get('qty')}'"
                )

        # Если добавились новые позиции
        if len(new_positions) > len(old_positions):
            new_position_indices = list(range(len(old_positions), len(new_positions)))
            changed_indices.extend(new_position_indices)
            name_changed_indices.extend(
                new_position_indices
            )  # Новые позиции нужно полностью пересчитать
            logger.critical(
                f"ОТЛАДКА-ЯДРО: Добавлены новые позиции: {len(old_positions)} -> {len(new_positions)}"
            )

        # Пересчитываем только позиции где изменилось название или это новые позиции
        if name_changed_indices:
            logger.critical(
                f"ОТЛАДКА-ЯДРО: Пересчитываем позиции с изменением названий: {[i+1 for i in name_changed_indices]}"
            )
            name_changed_positions = [new_positions[i] for i in name_changed_indices]
            new_match_results = match_positions(name_changed_positions, products)

            # Объединяем старые и новые результаты
            match_results = []
            new_result_iter = iter(new_match_results)

            for i in range(len(new_positions)):
                if i in name_changed_indices:
                    # Используем новый результат для позиции с измененным названием
                    match_results.append(next(new_result_iter))
                elif i < len(old_match_results):
                    # Сохраняем старый результат, но обновляем числовые поля из новой позиции
                    old_result = old_match_results[i].copy()
                    new_position = new_positions[i]

                    # Обновляем числовые поля из новой позиции
                    for field in ["qty", "price", "unit"]:
                        if field in new_position:
                            old_result[field] = new_position[field]

                    # Пересчитываем line_total если есть qty и price
                    if "qty" in old_result and "price" in old_result:
                        try:
                            qty = float(old_result["qty"]) if old_result["qty"] is not None else 0
                            price = (
                                float(old_result["price"]) if old_result["price"] is not None else 0
                            )
                            old_result["line_total"] = qty * price
                        except (ValueError, TypeError):
                            pass

                    match_results.append(old_result)
                    logger.critical(
                        f"ОТЛАДКА-ЯДРО: Позиция {i+1} - сохранены старые совпадения, обновлены числовые поля"
                    )
                else:
                    # Новая позиция без предыдущего результата
                    match_results.append(
                        {
                            "name": new_positions[i].get("name", ""),
                            "status": "unknown",
                            "score": 0.0,
                        }
                    )
        elif changed_indices and not name_changed_indices:
            # Изменились только числовые поля, сохраняем все старые совпадения но обновляем числовые поля
            logger.critical("ОТЛАДКА-ЯДРО: Изменились только числовые поля, сохраняем совпадения")
            match_results = []
            for i in range(len(new_positions)):
                if i < len(old_match_results):
                    # Сохраняем старый результат, но обновляем числовые поля из новой позиции
                    old_result = old_match_results[i].copy()
                    new_position = new_positions[i]

                    # Обновляем числовые поля из новой позиции
                    for field in ["qty", "price", "unit"]:
                        if field in new_position:
                            old_result[field] = new_position[field]

                    # Пересчитываем line_total если есть qty и price
                    if "qty" in old_result and "price" in old_result:
                        try:
                            qty = float(old_result["qty"]) if old_result["qty"] is not None else 0
                            price = (
                                float(old_result["price"]) if old_result["price"] is not None else 0
                            )
                            old_result["line_total"] = qty * price
                        except (ValueError, TypeError):
                            pass

                    match_results.append(old_result)
                    logger.critical(
                        f"ОТЛАДКА-ЯДРО: Позиция {i+1} - сохранены старые совпадения, обновлены числовые поля"
                    )
                else:
                    # Новая позиция без предыдущего результата
                    match_results.append(
                        {
                            "name": new_positions[i].get("name", ""),
                            "status": "unknown",
                            "score": 0.0,
                        }
                    )
        elif len(old_match_results) == 0:
            # ИСПРАВЛЕНО: Если old_match_results пустой, полностью пересчитываем все позиции
            logger.critical(
                "ОТЛАДКА-ЯДРО: old_match_results пустой, полностью пересчитываем все позиции"
            )
            match_results = match_positions(new_positions, products)
        else:
            # Если ничего не изменилось, используем старые результаты
            logger.critical(
                "ОТЛАДКА-ЯДРО: Изменений в позициях не обнаружено, используем старые match_results"
            )
            match_results = old_match_results[: len(new_positions)]  # Обрезаем под новую длину

        # Явно считаем ошибки для более надежного определения статуса
        unknown_count = sum(1 for r in match_results if r.get("status") == "unknown")
        partial_count = sum(1 for r in match_results if r.get("status") == "partial")

        # Логируем для отладки
        logger.critical(
            "ОТЛАДКА-ЯДРО: Результаты: unknown=%s, partial=%s" % (unknown_count, partial_count)
        )

        # ДИАГНОСТИКА: Проверяем финальный match_results
        logger.critical(f"ОТЛАДКА-ЯДРО: Финальный len(match_results)={len(match_results)}")
        logger.critical(f"ОТЛАДКА-ЯДРО: Финальный match_results={match_results}")

        # Обновляем состояние с явными счетчиками ошибок
        await state.update_data(
            invoice=new_invoice,
            match_results=match_results,
            unknown_count=unknown_count,
            partial_count=partial_count,
            last_edit_time=asyncio.get_event_loop().time(),  # Сохраняем время последнего редактирования
        )
        logger.critical("ОТЛАДКА-ЯДРО: Состояние обновлено с новым инвойсом")

        # ОТЛАДКА: Проверяем что имена сохранились после match_positions
        logger.critical("ОТЛАДКА-ЯДРО: Проверка имен после match_positions:")
        for i, pos in enumerate(new_invoice.get("positions", [])):
            name = pos.get("name")
            logger.critical(f"ОТЛАДКА-ЯДРО: Позиция {i+1}: name='{name}'")

        for i, match in enumerate(match_results):
            name = match.get("name")
            matched_name = match.get("matched_name")
            status = match.get("status")
            logger.critical(
                f"ОТЛАДКА-ЯДРО: Match {i+1}: name='{name}', matched_name='{matched_name}', status='{status}'"
            )

        # Формируем отчет
        try:
            text, has_errors = report.build_report(new_invoice, match_results)
            logger.critical(
                "ОТЛАДКА-ЯДРО: Отчет сформирован, has_errors=%s, размер=%s"
                % (has_errors, len(text))
            )
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
