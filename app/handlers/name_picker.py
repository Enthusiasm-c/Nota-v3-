"""
Handlers for unrecognized product name suggestions with fuzzy matching.
"""

import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from app.fsm.states import EditFree, NotaStates
from app.formatters import report
from app.matcher import match_positions, fuzzy_find
from app.data_loader import load_products
from app.keyboards import build_main_kb
from app.converters import parsed_to_dict
from app.edit.apply_intent import set_name
from app.alias import add_alias
from app.i18n import t

logger = logging.getLogger(__name__)

# Create router for handler registration
router = Router()

@router.callback_query(F.data.startswith("pick_name:"))
async def handle_pick_name(call: CallbackQuery, state: FSMContext):
    """
    Handles callback when user selects a suggested product name.
    
    Args:
        call: Callback query from the inline keyboard
        state: FSM context
    """
    # Parse row and product ID from callback data
    try:
        _, row_idx, product_id = call.data.split(":")
        row_idx = int(row_idx)
    except (ValueError, IndexError):
        await call.answer(t("error.invalid_callback_data"))
        return
    
    # Get invoice from state
    data = await state.get_data()
    invoice = data.get("invoice")
    if not invoice:
        await call.answer(t("error.invoice_not_found"))
        return
    
    lang = data.get("lang", "en")  # Get user language preference
    
    # Convert to dict format if needed
    invoice = parsed_to_dict(invoice)
    
    # Processing indicator
    processing_msg = await call.message.answer(t("status.applying_changes", lang=lang))
    
    try:
        # Find the product by ID
        products = load_products()
        selected_product = next((p for p in products if getattr(p, "id", None) == product_id 
                               or p.get("id") == product_id), None)
        
        if not selected_product:
            await processing_msg.delete()
            await call.answer(t("error.product_not_found", lang=lang))
            return
        
        # Get product name
        product_name = getattr(selected_product, "name", None)
        if product_name is None and isinstance(selected_product, dict):
            product_name = selected_product.get("name", "")
        
        # Update invoice with the new name
        if 0 <= row_idx < len(invoice.get("positions", [])):
            # Save original name for alias
            original_name = invoice["positions"][row_idx].get("name", "")
            
            # Update with the selected product name
            invoice = set_name(invoice, row_idx, product_name)
            
            # Recalculate errors and update report
            match_results = match_positions(invoice["positions"], products)
            text, has_errors = report.build_report(invoice, match_results)
            
            # Add alias if the row is successfully recognized
            if original_name and product_id:
                add_alias(original_name, product_id)
                logger.info(f"[handle_pick_name] Added alias: {original_name} -> {product_id}")
            
            # Count remaining issues
            issues_count = sum(1 for item in match_results if item.get("status", "") != "ok")
            
            # Update state data
            await state.update_data(invoice=invoice, issues_count=issues_count)
            
            # Remove inline keyboard from the suggestion message
            await call.message.edit_reply_markup(reply_markup=None)
            
            # Delete processing message
            await processing_msg.delete()
            
            # Generate keyboard based on errors presence
            keyboard = build_main_kb(has_errors, lang=lang)
            
            # Send updated report
            await call.message.answer(
                text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            
            # Add success message
            success_message = t("name_changed", {"name": product_name}, lang=lang)
            if not has_errors:
                success_message += t("edit_success_confirm", lang=lang)
                
            await call.message.answer(success_message, parse_mode="HTML")
        else:
            await processing_msg.delete()
            await call.message.answer(t("error.position_not_found", {"index": row_idx}, lang=lang))
    
    except Exception as e:
        logger.error(f"[handle_pick_name] Error updating name: {str(e)}")
        
        # Delete processing message
        try:
            await processing_msg.delete()
        except Exception:
            pass
            
        await call.message.answer(t("error.update_name", lang=lang))
    
    # Answer callback query
    await call.answer()
    
    # Stay in the same state for continued editing
    await state.set_state(EditFree.awaiting_input)


async def show_fuzzy_suggestions(message: Message, state: FSMContext, name: str, row_idx: int, lang: str = "en"):
    """
    Shows inline suggestions for unrecognized product names.
    
    Args:
        message: User's message
        state: FSM context
        name: Unrecognized product name
        row_idx: Row index in the invoice
        lang: Language code
    
    Returns:
        True if suggestions were shown, False otherwise
    """
    products = load_products()
    matches = fuzzy_find(name, products, thresh=0.75)
    
    if not matches:
        await message.answer(t("suggestion.no_similar_items", lang=lang))
        return False
    
    # Limit to top 2 matches
    matches = matches[:2]
    
    # Create inline keyboard with suggestions
    buttons = []
    for match in matches:
        buttons.append(
            InlineKeyboardButton(
                text=match["name"], 
                callback_data=f"pick_name:{row_idx}:{match['id']}"
            )
        )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[buttons])
    
    # Show suggestion to the user
    await message.answer(
        t("suggestion.fuzzy_match", {"suggestion": matches[0]["name"]}, lang=lang),
        parse_mode="HTML",
        reply_markup=keyboard
    )
    
    return True