"""
Улучшенная версия обработчика photo_handler с использованием IncrementalUI.

Этот модуль предоставляет асинхронный обработчик фотографий для распознавания
и анализа инвойсов с использованием прогрессивных обновлений интерфейса.
"""

import asyncio
import logging
import uuid
from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.enums import ParseMode

from app.utils.incremental_ui import IncrementalUI
from app import ocr, matcher, data_loader
from app.formatters.report import build_report
from app.keyboards import build_main_kb
from app.utils.md import clean_html

# Импортируем NotaStates из модуля состояний
from app.fsm.states import NotaStates

logger = logging.getLogger(__name__)

# Создаем роутер для регистрации обработчика
router = Router()

@router.message(F.photo)
async def photo_handler_incremental(message: Message, state: FSMContext):
    """
    Обрабатывает загруженные фото инвойсов с прогрессивными обновлениями UI.
    
    Предоставляет пользователю наглядную информацию о процессе обработки на каждом этапе:
    1. Загрузка фото
    2. OCR-распознавание
    3. Сопоставление позиций
    4. Формирование отчета
    
    Args:
        message: Входящее сообщение Telegram с фото
        state: FSM-контекст пользователя
    """
    # Данные для отладки
    user_id = message.from_user.id
    photo_id = message.photo[-1].file_id if message.photo else None
    req_id = uuid.uuid4().hex[:8]  # Уникальный ID запроса для логирования
    
    logger.info(f"[{req_id}] Получено новое фото от пользователя {user_id}")
    
    # Инициализация IncrementalUI
    ui = IncrementalUI(message.bot, message.chat.id)
    await ui.start("📸 Получение изображения...")
    
    try:
        # Шаг 1: Загрузка фото
        # Получаем информацию о файле
        file = await message.bot.get_file(message.photo[-1].file_id)
        
        # Анимируем процесс загрузки
        await ui.start_spinner()
        
        # Загружаем содержимое файла
        img_bytes = await message.bot.download_file(file.file_path)
        
        # Останавливаем спиннер и обновляем UI
        ui.stop_spinner()
        await ui.update("✅ Изображение получено")
        logger.info(f"[{req_id}] Загружено фото, размер {len(img_bytes.getvalue())} байт")
        
        # Шаг 2: OCR изображения
        await ui.append("🔍 Распознавание текста (OCR)...")
        await ui.start_spinner()
        
        # Запуск OCR в отдельном потоке для неблокирующей работы
        ocr_result = await asyncio.to_thread(ocr.call_openai_ocr, img_bytes.getvalue())
        
        ui.stop_spinner()
        positions_count = len(ocr_result.positions) if ocr_result.positions else 0
        await ui.update(f"✅ Текст распознан: найдено {positions_count} позиций")
        logger.info(f"[{req_id}] OCR успешно выполнен, найдено {positions_count} позиций")
        
        # Шаг 3: Сопоставление с продуктами
        await ui.append("🔄 Сопоставление позиций...")
        await ui.start_spinner()
        
        # Загрузка базы продуктов
        products = data_loader.load_products("data/base_products.csv")
        
        # Сопоставляем позиции
        match_results = matcher.match_positions(ocr_result.positions, products)
        
        # Подсчитываем статистику сопоставления
        ok_count = sum(1 for item in match_results if item.get("status") == "ok")
        unknown_count = sum(1 for item in match_results if item.get("status") == "unknown")
        partial_count = positions_count - ok_count - unknown_count
        
        ui.stop_spinner()
        await ui.update(f"✅ Сопоставление завершено: {ok_count} ✓, {unknown_count} ❌, {partial_count} ⚠️")
        logger.info(f"[{req_id}] Сопоставление завершено: {ok_count} OK, {unknown_count} unknown, {partial_count} partial")
        
        # Сохраняем данные для доступа в других обработчиках
        from bot import user_matches
        user_matches[(user_id, 0)] = {  # 0 - временный ID, будет обновлен ниже
            "parsed_data": ocr_result,
            "match_results": match_results,
            "photo_id": photo_id,
            "req_id": req_id,
        }
        
        # Шаг 4: Формирование отчета
        await ui.append("📋 Формирование отчета...")
        await ui.start_spinner()
        
        # Создаем отчет для HTML-форматирования
        report_text, has_errors = build_report(ocr_result, match_results, escape_html=True)
        
        # Сохраняем invoice в state для доступа в режиме редактирования
        await state.update_data(invoice=ocr_result)
        
        # Импортируем функцию из keyboards
        from app.keyboards import build_main_kb
        
        # Новая клавиатура - только кнопки "Редактировать", "Отмена" и "Подтвердить" (если нет ошибок)
        inline_kb = build_main_kb(has_errors=True if unknown_count + partial_count > 0 else False)
        
        ui.stop_spinner()
        # Завершаем UI с кратким резюме
        await ui.complete("✅ Обработка фото завершена!")
        
        # Отправляем полный отчет отдельным сообщением
        try:
            # Проверяем сообщение на потенциальные проблемы с HTML до отправки
            telegram_html_tags = ["<b>", "<i>", "<u>", "<s>", "<strike>", "<del>", "<code>", "<pre>", "<a"]
            has_valid_html = any(tag in report_text for tag in telegram_html_tags)
            
            if "<pre>" in report_text and "</pre>" not in report_text:
                logger.warning("Unclosed <pre> tag detected in message, attempting to fix")
                report_text = report_text.replace("<pre>", "<pre>") + "</pre>"
                
            logger.debug(f"Sending report with HTML formatting (valid HTML tags: {has_valid_html})")
            report_msg = await message.answer(
                report_text,
                reply_markup=inline_kb,
                parse_mode=ParseMode.HTML
            )
            logger.debug(f"Successfully sent HTML-formatted report with message_id={report_msg.message_id}")
        except Exception as html_err:
            logger.warning(f"Error sending HTML report: {str(html_err)}")
            
            # Если не получилось, пробуем без форматирования
            try:
                logger.debug("Attempting to send report without formatting")
                report_msg = await message.answer(
                    report_text,
                    reply_markup=inline_kb,
                    parse_mode=None
                )
                logger.debug(f"Successfully sent plain report with message_id={report_msg.message_id}")
            except Exception as plain_err:
                logger.warning(f"Error sending plain report: {str(plain_err)}")
                
                # Последний вариант - очищаем текст от HTML и отправляем
                try:
                    logger.debug("Sending report with cleaned HTML")
                    cleaned_message = clean_html(report_text)
                    report_msg = await message.answer(
                        cleaned_message,
                        reply_markup=inline_kb,
                        parse_mode=None
                    )
                    logger.debug(f"Successfully sent cleaned report with message_id={report_msg.message_id}")
                except Exception as clean_err:
                    logger.error(f"All report sending attempts failed: {str(clean_err)}")
                    
                    # Крайний случай - отправляем краткую сводку
                    try:
                        simple_message = (
                            f"📋 Найдено {positions_count} позиций. "
                            f"✅ OK: {ok_count}. "
                            f"⚠️ Проблемы: {unknown_count + partial_count}."
                        )
                        report_msg = await message.answer(
                            simple_message, 
                            reply_markup=inline_kb, 
                            parse_mode=None
                        )
                        logger.debug(f"Sent summary message with message_id={report_msg.message_id}")
                    except Exception as final_err:
                        logger.error(f"All message attempts failed: {str(final_err)}")
                        report_msg = None
        
        # Если успешно отправили сообщение, обновляем ссылки в user_matches
        if report_msg:
            try:
                # Обновляем message_id в user_matches
                entry = user_matches.pop((user_id, 0), None)
                if entry:
                    new_key = (user_id, report_msg.message_id)
                    user_matches[new_key] = entry
                    logger.debug(f"Updated user_matches with new message_id={report_msg.message_id}")
            except Exception as key_err:
                logger.error(f"Error updating user_matches: {str(key_err)}")
        
        # Обновляем состояние пользователя
        await state.set_state(NotaStates.editing)
        logger.info(f"[{req_id}] Обработка инвойса завершена для пользователя {user_id}")
        
    except Exception as e:
        logger.error(f"[{req_id}] Ошибка при обработке фото: {str(e)}", exc_info=True)
        
        # Завершаем UI с сообщением об ошибке
        await ui.error(
            "Произошла ошибка при обработке фото. Пожалуйста, попробуйте еще раз или обратитесь к администратору."
        )
        
        # Возвращаемся в начальное состояние
        await state.set_state(NotaStates.main_menu)