"""
Handlers for invoice editing flow via GPT-3.5-turbo.
"""

import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from app.fsm.states import EditFree
from app.assistants.client import run_thread_safe, run_thread_safe_async
from app.edit.apply_intent import apply_intent
from app.formatters import report
from app.matcher import match_positions, fuzzy_find
from app.data_loader import load_products
from app.keyboards import build_main_kb
from app.converters import parsed_to_dict
from app.i18n import t

logger = logging.getLogger(__name__)

# Создаем роутер для регистрации обработчиков
router = Router()

@router.message(EditFree.awaiting_input)
async def handle_free_edit_text(message: Message, state: FSMContext):
    """
    Handles free-form user input in edit mode.
    Uses GPT-3.5-turbo for natural language parsing.
    
    Args:
        message: Incoming Telegram message
        state: FSM context
    """
    user_text = message.text.strip()
    logger.info("[edit_flow] New user input", extra={"data": {"user_text": user_text}})
    
    # Get user language preference (default to English)
    data = await state.get_data()
    lang = data.get("lang", "en")
    
    # Handle cancel command
    if user_text.lower() in ["отмена", "cancel"]:
        await message.answer(t("status.edit_cancelled", lang=lang))
        await state.set_state(None)  # Return to initial state
        return
    
    # Get data from state
    logger.info("[edit_flow] State at handler start", extra={"data": data})
    invoice = data.get("invoice")
    
    if not invoice:
        logger.warning("[edit_flow] No invoice in user state")
        await message.answer(t("status.session_expired", lang=lang))
        await state.clear()
        return
    
    # Send processing indicator
    processing_msg = await message.answer(t("status.processing", lang=lang))
    
    try:
        logger.info("[edit_flow] Sending user text to OpenAI", extra={"data": {"user_text": user_text}})
        # Use async version for better performance
        intent = await run_thread_safe_async(user_text)
        logger.info("[edit_flow] OpenAI response received", extra={"data": {"intent": intent}})
        
        # Check parsing success
        if intent.get("action") == "unknown":
            error = intent.get("error", "unknown_error")
            logger.warning("[edit_flow] Failed to parse command", extra={"data": {"error": error}})
            
            # Delete loading message
            try:
                await processing_msg.delete()
            except Exception:
                pass
            
            # Use custom error message if available
            error_message = intent.get("user_message", t("error.parse_command", lang=lang))
            
            await message.answer(error_message)
            return
            
        # Convert invoice to dict via universal adapter
        invoice = parsed_to_dict(invoice)
        
        # Apply intent to invoice
        new_invoice = apply_intent(invoice, intent)
        
        # Recalculate errors and update report
        products = load_products()
        match_results = match_positions(new_invoice["positions"], products)
        text, has_errors = report.build_report(new_invoice, match_results)
    
        # Flag to show if there was a change
        was_changed = True
        
        # Check if there are any unknown positions for fuzzy matching
        from app.handlers.name_picker import show_fuzzy_suggestions
        suggestion_shown = False
        
        for idx, item in enumerate(match_results):
            if item.get("status") == "unknown":
                name_to_check = item.get("name", "")
                # Try to show fuzzy suggestions with the new implementation
                suggestion_shown = await show_fuzzy_suggestions(
                    message, state, name_to_check, idx, lang
                )
                if suggestion_shown:
                    # Update invoice in state before exiting
                    await state.update_data(invoice=new_invoice)
                    
                    # Delete loading message
                    try:
                        await processing_msg.delete()
                    except Exception:
                        pass
                        
                    # Stay in input state
                    await state.set_state(EditFree.awaiting_input)
                    return
    
        # Count remaining issues
        issues_count = sum(1 for item in match_results if item.get("status", "") != "ok")
    
        # Update data in state
        await state.update_data(invoice=new_invoice, issues_count=issues_count)
    
        # Generate keyboard based on errors presence
        keyboard = build_main_kb(has_errors, lang=lang)
    
        # Delete loading message
        try:
            await processing_msg.delete()
        except Exception:
            pass
            
        # Send updated report
        await message.answer(
            text, 
            reply_markup=keyboard, 
            parse_mode="HTML"
        )
    
        # Add message about successful editing
        if was_changed:
            field_map = {
                "set_date": "date",
                "set_price": "price",
                "set_name": "name",
                "set_quantity": "quantity",
                "set_unit": "unit",
                "add_line": "new item"
            }
            field = field_map.get(intent.get("action", ""), "value")
            
            success_message = t("status.edit_success", {"field": field}, lang=lang)
            if not has_errors:
                success_message += t("status.edit_success_confirm", lang=lang)
                
            await message.answer(success_message)
    
        # Stay in the same state for continued editing
        await state.set_state(EditFree.awaiting_input)
        
    except Exception as e:
        logger.error("[edit_flow] Critical error processing command", extra={"data": {"error": str(e)}})
        
        # Delete loading message
        try:
            await processing_msg.delete()
        except Exception:
            pass
            
        await message.answer(t("status.service_unavailable", lang=lang))
        # Don't clear state so user can try again

# Handler for the "✏️ Edit" button click
@router.callback_query(F.data == "edit:free")
async def handle_edit_free(call: CallbackQuery, state: FSMContext):
    """
    Handler for the "✏️ Edit" button.
    Transitions user to free-form editing mode.
    """
    # Get data from state
    data = await state.get_data()
    lang = data.get("lang", "en")
    
    # Explicitly save invoice in state when transitioning to edit mode
    invoice = data.get("invoice")
    if invoice:
        await state.update_data(invoice=invoice)
    
    # Transition to input awaiting state
    await state.set_state(EditFree.awaiting_input)
    
    # Send instruction
    await call.message.answer(
        t("example.edit_prompt", lang=lang),
        parse_mode="HTML"
    )
    
    # Answer callback
    await call.answer()

# Обработчик подтверждения fuzzy-совпадения
@router.callback_query(F.data.startswith("fuzzy:confirm:"))
async def confirm_fuzzy_name(call: CallbackQuery, state: FSMContext):
    """
    Обработчик подтверждения fuzzy-совпадения названия позиции.
    
    Args:
        call: Объект callback запроса от нажатия кнопки "Да"
        state: FSM-контекст
    """
    # Получаем индекс строки из callback data
    line_idx = int(call.data.split(":")[-1])
    
    # Получаем данные из state
    data = await state.get_data()
    fuzzy_match = data.get("fuzzy_match")  # Предложенное название
    fuzzy_original = data.get("fuzzy_original")  # Оригинальное название
    invoice = data.get("invoice")
    
    if not all([fuzzy_match, invoice]):
        await call.message.answer("Ошибка: данные для подтверждения не найдены.")
        await call.message.edit_reply_markup(reply_markup=None)
        await call.answer()
        return
    
    # Отправляем индикатор обработки
    processing_msg = await call.message.answer("🔄 Применяю изменение...")
    
    try:
        # Обновляем название позиции
        invoice = parsed_to_dict(invoice)
        if 0 <= line_idx < len(invoice.get("positions", [])):
            # Изменяем название на предложенное
            invoice["positions"][line_idx]["name"] = fuzzy_match
            
            # Пересчитываем ошибки и обновляем отчёт
            match_results = match_positions(invoice["positions"], load_products())
            text, has_errors = report.build_report(invoice, match_results)
            
            # Добавляем алиас если строка успешно распознана
            product_id = None
            for pos in match_results:
                if pos.get("name") == fuzzy_match and pos.get("product_id"):
                    product_id = pos.get("product_id")
                    break
                    
            if product_id and fuzzy_original:
                from app.alias import add_alias
                add_alias(fuzzy_original, product_id)
                logger.info(f"[confirm_fuzzy_name] Added alias: {fuzzy_original} -> {product_id}")
            
            # Подсчитываем количество оставшихся проблем
            issues_count = sum(1 for item in match_results if item.get("status", "") != "ok")
            
            # Обновляем данные в состоянии
            await state.update_data(invoice=invoice, issues_count=issues_count)
            
            # Удаляем индикатор обработки
            try:
                await processing_msg.delete()
            except Exception:
                pass
                
            # Убираем кнопки с подсказкой
            await call.message.edit_reply_markup(reply_markup=None)
            
            # Генерируем клавиатуру в зависимости от наличия ошибок
            keyboard = build_main_kb(has_errors)
            
            # Отправляем обновлённый отчёт
            await call.message.answer(
                text, 
                reply_markup=keyboard, 
                parse_mode="HTML"
            )
            
            # Добавляем сообщение об успешном редактировании
            success_message = f"✅ Название позиции изменено на <b>{fuzzy_match}</b>!"
            if not has_errors:
                success_message += " Вы можете подтвердить инвойс."
                
            await call.message.answer(success_message, parse_mode="HTML")
        else:
            await call.message.answer(f"Ошибка: позиция с индексом {line_idx} не найдена.")
    
    except Exception as e:
        logger.error("[confirm_fuzzy_name] Ошибка при обновлении названия", extra={"data": {"error": str(e)}})
        
        # Удаляем индикатор обработки
        try:
            await processing_msg.delete()
        except Exception:
            pass
            
        await call.message.answer("Произошла ошибка при обновлении названия. Пожалуйста, попробуйте еще раз.")
    
    # Отвечаем на callback
    await call.answer()
    
    # Остаёмся в том же состоянии для продолжения редактирования
    await state.set_state(EditFree.awaiting_input)

# Обработчик отклонения fuzzy-совпадения
@router.callback_query(F.data.startswith("fuzzy:reject:"))
async def reject_fuzzy_name(call: CallbackQuery, state: FSMContext):
    """
    Обработчик отклонения fuzzy-совпадения названия позиции.
    
    Args:
        call: Объект callback запроса от нажатия кнопки "Нет"
        state: FSM-контекст
    """
    # Получаем индекс строки из callback data
    line_idx = int(call.data.split(":")[-1])
    
    # Получаем данные из state
    data = await state.get_data()
    fuzzy_original = data.get("fuzzy_original")
    
    # Убираем кнопки с подсказкой
    await call.message.edit_reply_markup(reply_markup=None)
    
    # Отправляем сообщение о необходимости ручного редактирования
    await call.message.answer(
        f"Хорошо, вы можете вручную отредактировать название, отправив команду:\n\n"
        f"<i>строка {line_idx+1} название [новое название]</i>",
        parse_mode="HTML"
    )
    
    # Отвечаем на callback
    await call.answer()
    
    # Остаёмся в том же состоянии для продолжения редактирования
    await state.set_state(EditFree.awaiting_input)