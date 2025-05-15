"""
Оптимизированный обработчик фотографий для бота Nota.

Этот модуль предоставляет полностью асинхронный обработчик фотографий
с прогрессивным UI, кешированием, защитой от повторной обработки,
и подробным логированием времени выполнения.
"""

import asyncio
import logging
import uuid
import time
from pathlib import Path
from typing import Optional, Dict, Any, List, Union

from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.enums import ParseMode

from app.utils.incremental_ui import IncrementalUI
from app.utils.timing_logger import operation_timer, async_timed
from app.utils.processing_guard import require_user_free, set_processing_photo, is_processing_photo
from app.utils.async_ocr import async_ocr
from app.utils.optimized_matcher import async_match_positions
from app.utils.cached_loader import cached_load_products, cached_load_data_async

from app.formatters.report import build_report
from app.keyboards import build_main_kb
from app.utils.md import clean_html
from app.i18n import t
from app.fsm.states import NotaStates

logger = logging.getLogger(__name__)

# Создаем роутер для регистрации обработчика
router = Router()

# Импортируем нужные состояния
from app.fsm.states import EditFree, NotaStates

@router.message(
    F.photo,
    require_user_free(context_name="photo_processing", max_age=300)  # 5 минут максимальное время блокировки
)
@async_timed(operation_name="photo_processing")
async def optimized_photo_handler(message: Message, state: FSMContext):
    """
    Полностью оптимизированный обработчик фотографий для Nota-бота.
    
    Обеспечивает:
    - Асинхронную обработку без блокировки основного потока
    - Детальное логирование времени каждого этапа
    - Защиту от повторной обработки одной фотографии
    - Прогрессивный пользовательский интерфейс
    - Кеширование данных и результатов
    
    Args:
        message: Сообщение от пользователя с фотографией
        state: Состояние пользователя
    """
    # Уникальный ID запроса для трассировки в логах
    req_id = f"photo_{uuid.uuid4().hex[:8]}"
    user_id = message.from_user.id
    
    # Получаем текущее состояние
    current_state = await state.get_state()
    
    # Если пользователь в режиме редактирования, не обрабатываем фотографию
    # Отключаем эту проверку временно для диагностики проблемы с фото. Позже можно вернуть эту логику.
    # Note: Commenting out this condition as it might be preventing photo processing
    # if current_state == "EditFree:awaiting_input":
    #     logger.info(f"[{req_id}] Пользователь {user_id} отправил фото в режиме редактирования, игнорируем")
    #     return
    logger.info(f"[{req_id}] Пользователь {user_id} отправил фото в состоянии {current_state}, продолжаем обработку")
    
    # Проверяем, не обрабатывает ли пользователь уже фотографию
    if await is_processing_photo(user_id):
        await message.answer("⚠️ Обработка предыдущей фотографии еще не завершена. Пожалуйста, подождите.")
        logger.warning(f"[{req_id}] Пользователь {user_id} отправил фото во время обработки другого")
        return
    
    # Устанавливаем флаг обработки фотографии
    await set_processing_photo(user_id, True)
    await state.update_data(processing_photo=True)
    
    try:
        logger.info(f"[{req_id}] Получена фотография от пользователя {user_id}")
        
        # Убедимся, что у сообщения есть фотографии
        if not message.photo or len(message.photo) == 0:
            logger.warning(f"[{req_id}] Сообщение не содержит фотографий")
            await message.answer("Ошибка: фотография не найдена. Попробуйте отправить еще раз.")
            return
        
        # Получаем язык пользователя из состояния
        data = await state.get_data()
        lang = data.get("lang", "en")
        
        # Инициализируем UI с прогрессивными обновлениями
        ui = IncrementalUI(message.bot, message.chat.id)
        await ui.start(t("status.receiving_image", lang=lang) or "📸 Receiving image...")
        
        # 1. Загрузка фотографии и подготовка
        with operation_timer(req_id, "download_photo") as timer:
            # Берем фото с наивысшим качеством (последнее в массиве)
            photo_id = message.photo[-1].file_id
            
            # Анимируем процесс загрузки
            await ui.start_spinner(theme="loading")
            
            # Загружаем файл
            file = await message.bot.get_file(photo_id)
            img_bytes_io = await message.bot.download_file(file.file_path)
            img_bytes = img_bytes_io.getvalue()
            
            # Останавливаем анимацию и обновляем UI
            ui.stop_spinner()
            await ui.update(t("status.image_received", lang=lang) or "✅ Image received")
            logger.info(f"[{req_id}] Downloaded photo, size {len(img_bytes)} bytes")
        
        # 2. OCR изображения
        with operation_timer(req_id, "ocr_processing") as timer:
            await ui.append(t("status.recognizing_text", lang=lang) or "🔍 Recognizing...")
            await ui.start_spinner(theme="dots")
            
            try:
                # Запускаем асинхронный OCR с таймаутом
                await ui.update("🔍 Распознавание текста (может занять до 30 секунд)...")
                ocr_result = await async_ocr(img_bytes, req_id=req_id, use_cache=True, timeout=30)
                
                # Handle both dict and ParsedData object types
                if isinstance(ocr_result, dict) and "positions" in ocr_result:
                    positions_count = len(ocr_result["positions"])
                else:
                    positions_count = len(ocr_result.positions) if hasattr(ocr_result, "positions") and ocr_result.positions else 0
                
                timer.add_metadata("positions_count", positions_count)
            except asyncio.TimeoutError:
                logger.error(f"[{req_id}] OCR processing timed out")
                await ui.error("⏱️ Время обработки фото превышено. Пожалуйста, попробуйте снова с другим фото.")
                return
            except Exception as e:
                logger.error(f"[{req_id}] Error in OCR processing: {e}")
                await ui.error("❌ Ошибка при распознавании текста. Попробуйте другое фото или сделайте снимок более четким.")
                return
            
            # Успешное завершение OCR
            # Variable positions_count is already defined above
            timer.checkpoint("ocr_complete")
            
            ui.stop_spinner()
            await ui.update(t("status.text_recognized", {"count": positions_count}, lang=lang) or 
                        f"✅ Text recognized: found {positions_count} items")
            logger.info(f"[{req_id}] OCR completed, found {positions_count} items")
        
        # 3. Сопоставление с базой товаров
        with operation_timer(req_id, "product_matching") as timer:
            await ui.append(t("status.matching_items", lang=lang) or "🔄 Matching items...")
            await ui.start_spinner(theme="boxes")
            
            # Загружаем базу товаров с кешированием
            from app import data_loader
            products = cached_load_products("data/base_products.csv", data_loader.load_products)
            timer.checkpoint("products_loaded")
            
            # Асинхронное сопоставление позиций
            try:
                # Добавляем детальное логирование
                logger.info(f"[{req_id}] OCR result type: {type(ocr_result)}")
                
                # Обеспечиваем правильный доступ к позициям независимо от типа ocr_result
                positions = []  # Default safe value
                
                try:
                    # Try object-style access first (for Pydantic models)
                    if hasattr(ocr_result, 'positions'):
                        positions = ocr_result.positions
                        logger.info(f"[{req_id}] Positions accessed via attribute, type: {type(positions)}")
                    # Try dict-style access
                    elif isinstance(ocr_result, dict) and 'positions' in ocr_result:
                        positions = ocr_result['positions']
                        logger.info(f"[{req_id}] Positions accessed via dict key, type: {type(positions)}")
                    # Try converting ParsedData TypedDict to standard dict
                    elif hasattr(ocr_result, '__getitem__'):
                        try:
                            positions = ocr_result['positions']
                            logger.info(f"[{req_id}] Positions accessed via getitem, type: {type(positions)}")
                        except (KeyError, TypeError):
                            logger.warning(f"[{req_id}] Could not access positions with __getitem__, using empty list")
                    # Last resort - log more details about the ocr_result
                    else:
                        logger.warning(f"[{req_id}] Could not find positions in OCR result of type {type(ocr_result)}, keys: {dir(ocr_result) if hasattr(ocr_result, '__dict__') else 'no dir'}")
                except Exception as e:
                    logger.error(f"[{req_id}] Error accessing positions: {str(e)}")
                    
                # Ensure positions is a list
                if not isinstance(positions, list):
                    logger.warning(f"[{req_id}] Positions is not a list: {type(positions)}, converting...")
                    try:
                        # Try to convert to list if it's iterable
                        positions = list(positions) if hasattr(positions, '__iter__') else []
                    except Exception as e:
                        logger.error(f"[{req_id}] Error converting positions to list: {str(e)}")
                        positions = []
                
                logger.info(f"[{req_id}] Matching {len(positions)} positions...")
                
                # Handle empty positions case gracefully
                if not positions or len(positions) == 0:
                    logger.warning(f"[{req_id}] Empty positions list, returning empty match results")
                    match_results = []
                else:
                    # Debug log the positions to help diagnose issues
                    try:
                        if isinstance(positions[0], dict):
                            logger.info(f"[{req_id}] First position example: {positions[0]}")
                        else:
                            logger.info(f"[{req_id}] First position type: {type(positions[0])}")
                    except Exception as debug_error:
                        logger.error(f"[{req_id}] Error logging position info: {debug_error}")
                
                    # Try to match positions
                    match_results = await async_match_positions(
                        positions, 
                        products
                    )
                    
                timer.checkpoint("matching_complete")
            except ValueError as ve:
                # More specific error for value errors which are likely input validation issues
                logger.error(f"[{req_id}] Value error in matching: {ve}")
                # Handle the error more gracefully for the user
                await ui.error(f"❌ Не удалось обработать список товаров. Пожалуйста, попробуйте другое фото.")
                return
            except Exception as e:
                logger.error(f"[{req_id}] Error in matching: {e}", exc_info=True)
                # Send a more friendly message to the user
                await ui.error("❌ Ошибка при сопоставлении товаров. Пожалуйста, попробуйте другое фото.")
                return
            
            # Статистика сопоставления
            ok_count = sum(1 for item in match_results if item.get("status") == "ok")
            unknown_count = sum(1 for item in match_results if item.get("status") == "unknown")
            # Позиции могут быть в двух форматах - из словаря или из объекта
            if isinstance(positions, list):
                positions_count = len(positions)
            else:
                positions_count = len(positions) if hasattr(positions, '__len__') else 0
            partial_count = positions_count - ok_count - unknown_count
            
            timer.add_metadata("match_stats", {
                "ok": ok_count,
                "unknown": unknown_count,
                "partial": partial_count,
                "total": positions_count
            })
            
            ui.stop_spinner()
            await ui.update(t("status.matching_completed", 
                         {"ok": ok_count, "unknown": unknown_count, "partial": partial_count},
                         lang=lang) or 
                       f"✅ Matching completed: {ok_count} ✓, {unknown_count} ❌, {partial_count} ⚠️")
            logger.info(f"[{req_id}] Matching completed: {ok_count} OK, {unknown_count} unknown, {partial_count} partial")
        
        # 4. Сохранение результатов в состояние и формирование отчета
        with operation_timer(req_id, "report_generation") as timer:
            # Сохраняем данные для доступа в других обработчиках
            from bot import user_matches
            
            user_matches[(user_id, 0)] = {  # 0 - временный ID, будет обновлен ниже
                "parsed_data": ocr_result,
                "match_results": match_results,
                "photo_id": photo_id,
                "req_id": req_id,
            }
            
            # Сохраняем инвойс в состоянии для доступа в режиме редактирования
            await state.update_data(invoice=ocr_result, lang=lang)
            timer.checkpoint("state_updated")
            
            # Формируем отчет
            await ui.append(t("status.generating_report", lang=lang) or "📋 Generating report...")
            await ui.start_spinner(theme="invoice")
            
            # Создаем отчет с HTML-форматированием
            report_text, has_errors = build_report(ocr_result, match_results, escape_html=True)
            timer.add_metadata("report_length", len(report_text))
            timer.checkpoint("report_built")
            
            # Формируем клавиатуру
            inline_kb = build_main_kb(
                has_errors=True if unknown_count + partial_count > 0 else False, 
                lang=lang
            )
            
            # Завершаем UI с кратким итогом
            ui.stop_spinner()
            await ui.complete(t("status.processing_completed", lang=lang) or "✅ Photo processing completed!")
            timer.checkpoint("ui_completed")
        
        # 5. Отправка полного отчета пользователю
        with operation_timer(req_id, "send_report") as timer:
            try:
                # Проверяем наличие HTML-тегов и формируем сообщение
                telegram_html_tags = ["<b>", "<i>", "<u>", "<s>", "<strike>", "<del>", "<code>", "<pre>", "<a"]
                has_valid_html = any(tag in report_text for tag in telegram_html_tags)
                
                # Пробуем отправить с HTML, если есть теги
                if has_valid_html:
                    result = await message.answer(report_text, reply_markup=inline_kb, parse_mode="HTML")
                else:
                    # Если нет HTML-тегов, отправляем без форматирования
                    result = await message.answer(report_text, reply_markup=inline_kb)
                
                # Обновляем ID сообщения в user_matches
                new_key = (user_id, result.message_id)
                user_matches[new_key] = user_matches.pop((user_id, 0))
                
                # Сохраняем ID сообщения в состоянии для будущих ссылок
                await state.update_data(invoice_msg_id=result.message_id)
                
                logger.info(f"[{req_id}] Report sent successfully, message_id={result.message_id}")
                timer.add_metadata("result_message_id", result.message_id)
                
            except Exception as msg_err:
                logger.error(f"[{req_id}] Error sending report: {str(msg_err)}")
                
                # Пробуем отправить без HTML-форматирования как резервный вариант
                try:
                    clean_report = clean_html(report_text)
                    
                    # Разбиваем слишком длинные сообщения
                    if len(clean_report) > 4000:
                        part1 = clean_report[:4000]
                        part2 = clean_report[4000:]
                        
                        await message.answer(part1)
                        result = await message.answer(part2, reply_markup=inline_kb)
                        logger.info(f"[{req_id}] Report sent in 2 parts due to length")
                    else:
                        result = await message.answer(clean_report, reply_markup=inline_kb)
                    
                    # Обновляем ссылки
                    new_key = (user_id, result.message_id)
                    if (user_id, 0) in user_matches:
                        user_matches[new_key] = user_matches.pop((user_id, 0))
                    await state.update_data(invoice_msg_id=result.message_id)
                    logger.info(f"[{req_id}] Report sent with fallback formatting")
                except Exception as final_err:
                    logger.error(f"[{req_id}] Critical error sending report: {str(final_err)}")
                    await message.answer(
                        t("error.report_failed", lang=lang) or 
                        "Error generating report. Please try again or contact support."
                    )
            
            # Устанавливаем состояние редактирования 
            # Проверяем, что мы не находимся уже в режиме редактирования (например, после команды редактирования)
            current_state = await state.get_state()
            if current_state != "EditFree:awaiting_input":
                # Устанавливаем состояние только если мы не в режиме редактирования EditFree
                # Используем NotaStates.editing для совместимости с существующим кодом
                # В edit_flow.py добавлены обработчики для обоих состояний (NotaStates.editing и EditFree.awaiting_input)
                await state.set_state(NotaStates.editing)
                logger.info(f"[{req_id}] Set state to NotaStates.editing after photo processing")
                # Добавляем лог для диагностики
                logger.info(f"[edit_flow] Successfully set state to NotaStates.editing from {current_state}")
            else:
                logger.info(f"[{req_id}] Maintaining EditFree.awaiting_input state (already in edit mode)")
            
    except Exception as e:
        logger.error(f"[{req_id}] Unexpected error processing photo: {str(e)}", exc_info=True)
        await message.answer("Произошла непредвиденная ошибка. Пожалуйста, попробуйте снова.")
    finally:
        # Снимаем флаг обработки фотографии
        await set_processing_photo(user_id, False)
        await state.update_data(processing_photo=False)