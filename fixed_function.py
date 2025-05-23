import logging
from typing import Dict, Tuple, Any, Optional, List, cast
from aiogram.fsm.context import FSMContext
from app.fsm.states import NotaStates
from app.i18n import t
from app.utils.bot import bot
from app.utils.retry import with_async_retry_backoff
from app.formatters.report import build_report
from app.data_loader import load_products
from app.matcher import match_positions

logger = logging.getLogger(__name__)

# Глобальный словарь для хранения матчей пользователей
user_matches: Dict[Tuple[int, int], Dict[str, Any]] = {}

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
        logger.debug(
            f"BUGFIX: Processing field edit, text: '{text[:30]}...' (truncated)"
        )
        
        # Обновляем напрямую данные в инвойсе
        old_value = entry["match_results"][idx].get(field, "")
        entry["match_results"][idx][field] = text
        logger.debug(f"BUGFIX: Updated {field} from '{old_value}' to '{text}'")
        
        # Запускаем матчер заново для обновленной строки, если нужно
        if field in ["name", "qty", "unit"]:
            products = load_products("data/base_products.csv")
            # Преобразуем список в нужный формат
            match_result = cast(Dict[str, Any], entry["match_results"][idx])
            entry["match_results"][idx] = match_positions(
                [match_result], cast(List[Dict[str, Any]], products)
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
            logger.error("Telegram error: %s\nText length: %d\nText sample: %s", 
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