"""
Handlers for invoice editing flow via GPT-3.5-turbo.
"""

import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from app.fsm.states import EditFree, NotaStates
from app.assistants.client import run_thread_safe, run_thread_safe_async
from app.edit.apply_intent import apply_intent
from app.formatters import report
from app.matcher import match_positions, fuzzy_find
from app.data_loader import load_products
from app.keyboards import build_main_kb
from app.converters import parsed_to_dict
from app.i18n import t
from app.utils.logger_config import get_buffered_logger
from app.edit.multi_edit_parser import parse_multi_edit_command, apply_multi_edit

logger = get_buffered_logger(__name__)

# Создаем роутер для регистрации обработчиков
router = Router()

@router.message(EditFree.awaiting_input)
@router.message(NotaStates.editing)
async def handle_free_edit_text(message: Message, state: FSMContext):
    """
    Обработчик свободного ввода команд редактирования.
    Поддерживает как одиночные команды, так и мультистрочное редактирование через разделитель ';'
    """
    user_id = getattr(message.from_user, 'id', 'unknown')
    message_text = getattr(message, 'text', None)
    
    logger.critical(f"ОТЛАДКА-ХЕНДЛЕР: handle_free_edit_text вызван для user_id={user_id}, text='{message_text}'")
    
    current_state = await state.get_state()
    logger.critical(f"ОТЛАДКА-ХЕНДЛЕР: Текущее состояние: {current_state}")
    
    data = await state.get_data()
    lang = data.get("lang", "en")
    
    # Проверка наличия инвойса в state
    invoice = data.get("invoice")
    if not invoice:
        logger.critical(f"ОТЛАДКА-ХЕНДЛЕР: Инвойс отсутствует в состоянии для user_id={user_id}")
        await message.answer("Не найден инвойс для редактирования. Отправьте фото инвойса или нажмите Edit.")
        return
    
    # Проверка наличия текста в сообщении
    if not hasattr(message, 'text') or message.text is None:
        logger.critical(f"ОТЛАДКА-ХЕНДЛЕР: Сообщение без текста для user_id={user_id}")
        await message.answer(t("edit.enter_text", lang=lang))
        await state.set_state(EditFree.awaiting_input)
        return
    
    # Проверка на пустую строку
    if not message.text.strip():
        logger.critical(f"ОТЛАДКА-ХЕНДЛЕР: Пустое сообщение для user_id={user_id}")
        return
    
    user_text = message.text.strip()
    logger.critical(f"ОТЛАДКА-ХЕНДЛЕР: Обрабатываем текст: '{user_text}' для user_id={user_id}")
    
    # Проверяем, является ли это мультистрочной командой
    if ";" in user_text:
        # Парсим мультистрочную команду
        intents = parse_multi_edit_command(user_text)
        if not intents:
            await message.answer("Не удалось распознать команды редактирования. Пожалуйста, проверьте формат.")
            return
            
        # Применяем все изменения
        try:
            new_invoice, applied_changes = apply_multi_edit(invoice, intents)
            if not applied_changes:
                await message.answer("Ни одно изменение не было применено. Пожалуйста, проверьте формат команд.")
                return
                
            # Формируем отчет о примененных изменениях
            changes_report = "Применены следующие изменения:\n"
            for intent in applied_changes:
                if intent["action"] == "edit_line_field":
                    changes_report += f"• Строка {intent['line']}, поле '{intent['field']}' → '{intent['value']}'\n"
                elif intent["action"] == "edit_date":
                    changes_report += f"• Дата → '{intent['value']}'\n"
                elif intent["action"] == "remove_line":
                    changes_report += f"• Удалена строка {intent['line']}\n"
                    
            # Обновляем состояние и отправляем отчет
            await state.update_data(invoice=new_invoice)
            formatted_report = report.format_invoice(new_invoice)
            await message.answer(changes_report + "\n" + formatted_report)
            
        except Exception as e:
            logger.error(f"Error applying multi-edit: {str(e)}")
            await message.answer("Произошла ошибка при применении изменений. Пожалуйста, попробуйте еще раз.")
            return
    else:
        # Обработка одиночной команды (существующая логика)
        intent = detect_intent(user_text)
        if intent["action"] == "unknown":
            await message.answer("Не удалось распознать команду. Пожалуйста, проверьте формат.")
            return
            
        try:
            new_invoice = apply_edit(invoice, intent)
            await state.update_data(invoice=new_invoice)
            formatted_report = report.format_invoice(new_invoice)
            await message.answer(formatted_report)
        except Exception as e:
            logger.error(f"Error applying edit: {str(e)}")
            await message.answer("Произошла ошибка при применении изменения. Пожалуйста, попробуйте еще раз.")
            return
    
    # Гарантируем, что мы в режиме редактирования
    if current_state not in [EditFree.awaiting_input, NotaStates.editing]:
        logger.critical(f"ОТЛАДКА-ХЕНДЛЕР: Устанавливаем состояние в EditFree.awaiting_input из {current_state}")
        await state.set_state(EditFree.awaiting_input)

# Handler for the "✏️ Edit" button click
@router.callback_query(F.data == "edit:free")
async def handle_edit_free(call: CallbackQuery, state: FSMContext):
    """
    Handler for the "✏️ Edit" button.
    Transitions user to free-form editing mode.
    """
    import logging
    logger.warning(f"ДИАГНОСТИКА: Нажата кнопка Edit, user_id={call.from_user.id}, chat_id={call.message.chat.id}, message_id={call.message.message_id}")
    # Get data from state
    data = await state.get_data()
    lang = data.get("lang", "en")
    
    # Explicitly save invoice in state when transitioning to edit mode
    invoice = data.get("invoice")
    if invoice:
        await state.update_data(invoice=invoice)
    
    # Transition to input awaiting state
    await state.set_state(EditFree.awaiting_input)
    logger.warning(f"ДИАГНОСТИКА: Состояние переведено в EditFree.awaiting_input для user_id={call.from_user.id}")
    
    # Send instruction
    logger.warning(f"ДИАГНОСТИКА: Отправляю пользователю prompt для свободного редактирования user_id={call.from_user.id}")
    await call.message.answer(
        t("example.edit_prompt", lang=lang),
        parse_mode="HTML"
    )
    
    # Answer callback
    logger.warning(f"ДИАГНОСТИКА: Callback edit:free успешно обработан для user_id={call.from_user.id}")
    await call.answer()

# Handler for fuzzy-match confirmation
@router.callback_query(F.data.startswith("fuzzy:confirm:"))
async def confirm_fuzzy_name(call: CallbackQuery, state: FSMContext):
    """
    Handles fuzzy match name confirmation.
    
    Args:
        call: Callback query object from clicking "Yes" button
        state: FSM context
    """
    # Get line index from callback data
    line_idx = int(call.data.split(":")[-1])
    
    # Get data from state
    data = await state.get_data()
    fuzzy_match = data.get("fuzzy_match")  # Suggested name
    fuzzy_original = data.get("fuzzy_original")  # Original name
    invoice = data.get("invoice")
    lang = data.get("lang", "en")
    
    if not all([fuzzy_match, invoice]):
        await call.message.answer(t("error.unexpected", lang=lang))
        await call.message.edit_reply_markup(reply_markup=None)
        # Get user language preference
        lang = data.get("lang", "en")
        await call.answer()
        return
    
    # Send processing indicator
    processing_msg = await call.message.answer(t("status.applying_changes", lang=lang))
    
    try:
        # Update position name
        invoice = parsed_to_dict(invoice)
        if 0 <= line_idx < len(invoice.get("positions", [])):
            # Change name to suggested one
            invoice["positions"][line_idx]["name"] = fuzzy_match
            
            # Recalculate errors and update report
            match_results = match_positions(invoice["positions"], load_products())
            text, has_errors = report.build_report(invoice, match_results)
            
            # Count remaining issues
            issues_count = sum(1 for item in match_results if item.get("status", "") != "ok")
            
            # Update data in state
            await state.update_data(invoice=invoice, issues_count=issues_count)
            
            # Delete processing indicator
            try:
                await processing_msg.delete()
            except Exception:
                pass
                
            # Remove suggestion buttons
            await call.message.edit_reply_markup(reply_markup=None)
            
            # Generate keyboard based on errors presence
            keyboard = build_main_kb(has_errors, lang=lang)
            
            # Send updated report
            await call.message.answer(
                text, 
                reply_markup=keyboard, 
                parse_mode="HTML"
            )
            
            # Add message about successful editing
            success_message = f"✅ {t('status.edit_success', {'field': 'name'}, lang=lang)}"
            if not has_errors:
                success_message += f" {t('status.edit_success_confirm', lang=lang)}"
                
            await call.message.answer(success_message, parse_mode="HTML")
        else:
            await call.message.answer(t("error.position_not_found", {"index": line_idx}, lang=lang))
    
    except Exception as e:
        logger.error("[confirm_fuzzy_name] Error updating name", extra={"data": {"error": str(e)}})
        
        # Delete processing indicator
        try:
            await processing_msg.delete()
        except Exception:
            pass
            
        await call.answer()
    
    # Остаёмся в том же состоянии для продолжения редактирования
    await state.set_state(EditFree.awaiting_input)

# Handler for fuzzy-match rejection
@router.callback_query(F.data.startswith("fuzzy:reject:"))
async def reject_fuzzy_name(call: CallbackQuery, state: FSMContext):
    """
    Handles fuzzy match name rejection.
    
    Args:
        call: Callback query object from clicking "No" button
        state: FSM context
    """
    # Get line index from callback data
    line_idx = int(call.data.split(":")[-1])
    
    # Get data from state
    data = await state.get_data()
    fuzzy_original = data.get("fuzzy_original")
    lang = data.get("lang", "en")
    
    # Remove suggestion buttons
    await call.message.edit_reply_markup(reply_markup=None)
    
    # Send message about manual editing requirement
    await call.message.answer(
        f"You can manually edit the name by sending the command:\n\n"
        f"<i>line {line_idx+1} name [new name]</i>",
        parse_mode="HTML"
    )
    
    # Answer callback
    await call.answer()
    
    # Stay in the same state for continued editing
    await state.set_state(EditFree.awaiting_input)