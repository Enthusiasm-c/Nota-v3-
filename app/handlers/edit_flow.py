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
    Обработчик свободного ввода пользователя для редактирования инвойса через ядро edit_core.
    Оставляет только UI-логику, бизнес-логика вынесена в edit_core.py.
    """
    logger.info(f"[edit_flow] Received update type: {type(message).__name__}")
    if not hasattr(message, 'text') or message.text is None:
        logger.warning("[edit_flow] Received message without text field")
        await message.answer("Пожалуйста, введите текст для редактирования.")
        await state.set_state(EditFree.awaiting_input)
        return
    if not message.text.strip():
        logger.debug("[edit_flow] Skipping empty message")
        return
    user_text = message.text.strip()
    data = await state.get_data()
    lang = data.get("lang", "en")

    from app.handlers.edit_core import process_user_edit
    processing_msg = None
    async def send_processing(text):
        nonlocal processing_msg
        processing_msg = await message.answer(text)
    async def send_result(text):
        await message.answer(text, parse_mode="HTML")
    async def send_error(text):
        await message.answer(text)
    async def fuzzy_suggester(message, state, name, idx, lang):
        from app.handlers.name_picker import show_fuzzy_suggestions
        return await show_fuzzy_suggestions(message, state, name, idx, lang)
    async def edit_state():
        await state.set_state(EditFree.awaiting_input)

    await process_user_edit(
        message=message,
        state=state,
        user_text=user_text,
        lang=lang,
        send_processing=send_processing,
        send_result=send_result,
        send_error=send_error,
        fuzzy_suggester=fuzzy_suggester,
        edit_state=edit_state
    )
    if processing_msg:
        try:
            await processing_msg.delete()
        except Exception:
            pass
    await state.set_state(EditFree.awaiting_input)

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
            
        await call.message.answer(t("error.unexpected", lang=lang))
    
    # Отвечаем на callback
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