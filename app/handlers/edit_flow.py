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
        if direct_actions and not any(action.get("error", "").startswith("invalid") for action in direct_actions):
            # Successfully parsed at least one action directly
            logger.info(f"[edit_flow] Using direct pattern matching results: {direct_actions}")
            
            # Detect if this contains commands with reserved keywords date/line/price
            has_date = any(action.get("action") == "set_date" for action in direct_actions)
            has_price = any(action.get("action") == "set_price" for action in direct_actions)
            
            # Flag to show if there was a change
            was_changed = len(direct_actions) > 0
            
            # Convert invoice to dict via universal adapter
            invoice = parsed_to_dict(invoice)
            new_invoice = invoice  # Start with original invoice
            
            # Apply all intents sequentially
            for action_data in direct_actions:
                # Convert to proper format expected by apply_intent
                if action_data.get("action") == "set_price" and "price" in action_data:
                    action_data["value"] = action_data["price"]
                elif action_data.get("action") == "set_date" and "date" in action_data:
                    action_data["value"] = action_data["date"]
                
                # Apply each intent individually
                try:
                    from app.edit.apply_intent import apply_intent
                    new_invoice = apply_intent(new_invoice, action_data)
                    logger.info(f"[edit_flow] Applied action: {action_data.get('action')} - result: {bool(new_invoice != invoice)}")
                except Exception as e:
                    logger.error(f"[edit_flow] Error in apply_intent: {str(e)}")
            
            # Set flag for no fuzzy matching when dealing with dates/prices
            suggestion_shown = False
            if has_date or has_price:
                # Skip fuzzy matching when dealing with dates/prices/known values
                logger.info(f"[edit_flow] Skipping fuzzy matching for date or price command")
            
        else:
            # Fall back to OpenAI interpretation if direct pattern matching fails
            intent = await run_thread_safe_async(user_text)
            logger.info("[edit_flow] OpenAI response received", extra={"data": {"intent": intent}})
            
            # Check if this is a line-specific edit command
            is_line_edit = False
            edited_line = None
            
            if intent.get("action") == "edit_line_field" and intent.get("line") is not None:
                is_line_edit = True
                edited_line = intent.get("line") - 1  # Convert to 0-based index
                logger.info(f"[edit_flow] Line-specific edit detected for line {edited_line}")
                
                # Save edit context in state
                await state.update_data(edit_context={
                    "line_specific": True,
                    "edited_line": edited_line,
                    "field": intent.get("field"),
                    "value": intent.get("value")
                })
            else:
                # Clear any previous edit context
                await state.update_data(edit_context={
                    "line_specific": False,
                    "edited_line": None
                })
            
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
            
            # Flag to show if there was a change
            was_changed = True
        
        # Recalculate errors and update report with cached products
        from app.utils.cached_loader import cached_load_products
        products = cached_load_products("data/base_products.csv", load_products)
        match_results = match_positions(new_invoice["positions"], products)
        text, has_errors = report.build_report(new_invoice, match_results)
        
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
            
            # Add alias if line was successfully recognized
            product_id = None
            for pos in match_results:
                if pos.get("name") == fuzzy_match and pos.get("product_id"):
                    product_id = pos.get("product_id")
                    break
                    
            if product_id and fuzzy_original:
                from app.alias import add_alias
                add_alias(fuzzy_original, product_id)
                logger.info(f"[confirm_fuzzy_name] Added alias: {fuzzy_original} -> {product_id}")
            
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