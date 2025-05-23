"""
Handlers for unrecognized product name suggestions with fuzzy matching.
"""

import logging
from typing import List

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.alias import add_alias
from app.config import settings
from app.converters import parsed_to_dict
from app.data_loader import load_products
from app.edit.apply_intent import set_name
from app.formatters import report
from app.fsm.states import EditFree
from app.i18n import t
from app.keyboards import build_edit_keyboard, build_main_kb
from app.matcher import async_match_positions, fuzzy_find, match_positions
from app.models import Product

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
        # Get user language preference
        data = await state.get_data()
        lang = data.get("lang", "en")
        await call.answer(t("error.invalid_callback_data", {}, lang=lang))
        return

    # Get invoice from state
    data = await state.get_data()
    invoice = data.get("invoice")
    lang = data.get("lang", "en")  # Get user language preference

    if not invoice:
        await call.answer(t("error.invoice_not_found"))
        return

    # Convert to dict format if needed
    invoice = parsed_to_dict(invoice)

    # Processing indicator
    processing_msg = await call.message.answer(t("status.applying_changes", lang=lang))

    try:
        # Find the product by ID
        products = load_products()
        selected_product = next(
            (
                p
                for p in products
                if getattr(p, "id", None) == product_id or p.get("id") == product_id
            ),
            None,
        )

        if not selected_product:
            await processing_msg.delete()
            await call.answer(t("error.product_not_found", lang=lang))
            return

        # Get product name from database
        product_name = getattr(selected_product, "name", None)
        if product_name is None and isinstance(selected_product, dict):
            product_name = selected_product.get("name", "")

        # Update invoice with the database name
        if 0 <= row_idx < len(invoice.get("positions", [])):
            # Save original name for alias
            original_name = invoice["positions"][row_idx].get("name", "")

            # Update with the selected product name from database
            invoice = set_name(invoice, row_idx, product_name)

            # Set matched_name to ensure it's displayed correctly
            invoice["positions"][row_idx]["matched_name"] = product_name

            # Recalculate errors and update report
            match_results = match_positions(invoice["positions"], products)

            text, has_errors = report.build_report(invoice, match_results)

            # Count remaining issues
            issues_count = sum(1 for item in match_results if item.get("status", "") != "ok")

            # Update state data
            await state.update_data(invoice=invoice, issues_count=issues_count)

            # Remove inline keyboard from the suggestion message
            await call.message.edit_reply_markup(reply_markup=None)

            # Show updated report
            await call.message.answer(
                text, reply_markup=build_main_kb(has_errors=has_errors), parse_mode="HTML"
            )

            # Add alias for future matching
            if original_name and original_name.lower() != product_name.lower():
                await add_alias(original_name, product_id)

            await processing_msg.delete()
        await call.answer()

    except Exception:
        logger.exception("Error in handle_pick_name")
        await processing_msg.delete()
        await call.message.answer(
            t("error.processing_error", lang=lang), reply_markup=build_main_kb()
        )
    await call.answer()


async def show_fuzzy_suggestions(
    message: Message, state: FSMContext, name: str, row_idx: int, lang: str = "en"
):
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
    # Detect if this is a reserved keyword that should bypass fuzzy matching
    reserved_keywords = ["date", "дата", "цена", "price", "per pack", "120k"]
    if any(keyword in name.lower() for keyword in reserved_keywords):
        logger.info(f"Name '{name}' contains reserved keyword, skipping fuzzy matching")
        return False

    # Get the edit context from state data
    data = await state.get_data()
    edit_context = data.get("edit_context", {})

    # Skip fuzzy matching if we're processing commands with date or other structured data
    if data.get("skip_fuzzy_matching") or any(
        action in name.lower() for action in ["date", "дата", "изменить дату"]
    ):
        logger.info(
            "Skipping fuzzy matching due to skip_fuzzy_matching flag or presence of date command"
        )
        # Reset flag after use
        await state.update_data(skip_fuzzy_matching=False)
        return False

    # Check if this was called from a line-specific edit command
    is_line_specific_edit = edit_context.get("line_specific", False)
    edited_line = edit_context.get("edited_line", None)

    # If this is a line-specific edit but for a different line, skip suggestions
    if is_line_specific_edit and edited_line is not None and edited_line != row_idx:
        logger.debug(
            f"Skipping suggestions for row {row_idx} because line-specific edit is for line {edited_line}"
        )
        return False

    # For short inputs (length < 4), apply higher similarity threshold
    thresh = 0.85 if len(name) < 4 else 0.75

    products = load_products()

    # Try to find fuzzy matches
    matches = fuzzy_find(name, products, thresh=thresh)

    # If no matches found, accept the user input as-is without showing error message
    if not matches:
        logger.info(f"No fuzzy matches found for '{name}', accepting user input as-is")
        # Don't show error message here, just accept the name as manual input
        return False

    # Limit to top 2 matches
    matches = matches[:2]

    # Create inline keyboard with suggestions
    buttons = [
        InlineKeyboardButton(text="✓ Yes", callback_data=f"pick_name:{row_idx}:{matches[0]['id']}"),
        InlineKeyboardButton(text="✗ No", callback_data=f"pick_name_reject:{row_idx}"),
    ]

    keyboard = InlineKeyboardMarkup(inline_keyboard=[buttons])

    # Show suggestion to the user with improved wording
    await message.answer(
        t("suggestion.fuzzy_match", {"suggestion": matches[0]["name"]}, lang=lang)
        or f"Did you mean \"{matches[0]['name']}\"?",
        parse_mode="HTML",
        reply_markup=keyboard,
    )

    # Save the current user input for handling rejection correctly
    await state.update_data(fuzzy_original_text=name)

    return True


@router.callback_query(F.data.startswith("pick_name_reject:"))
async def handle_pick_name_reject(call: CallbackQuery, state: FSMContext):
    """
    Handles rejection of a fuzzy suggestion.

    Args:
        call: Callback query from the 'No' button
        state: FSM context
    """
    # Parse row index from callback data
    try:
        _, row_idx = call.data.split(":")
        row_idx = int(row_idx)
    except (ValueError, IndexError):
        data = await state.get_data()
        lang = data.get("lang", "en")
        await call.answer(t("error.invalid_callback_data", {}, lang=lang))
        return

    # Get user data
    data = await state.get_data()
    invoice = data.get("invoice")
    original_text = data.get("fuzzy_original_text", "")
    lang = data.get("lang", "en")

    if not invoice:
        await call.answer(t("error.invoice_not_found", {}, lang=lang))
        return

    # Convert to dict format if needed
    invoice = parsed_to_dict(invoice)

    # Remove inline keyboard from the suggestion message
    await call.message.edit_reply_markup(reply_markup=None)

    # Keep original text as manual edit
    if original_text and 0 <= row_idx < len(invoice.get("positions", [])):
        # Apply manual edit flag to accept user's original input
        invoice = set_name(invoice, row_idx, original_text, manual_edit=True)

        # Load products and recalculate errors
        products = load_products()
        match_results = match_positions(invoice["positions"], products)
        text, has_errors = report.build_report(invoice, match_results)

        # Update state
        await state.update_data(invoice=invoice)

        # Generate keyboard based on errors presence
        keyboard = build_main_kb(has_errors, lang=lang)

        # Send updated report
        await call.message.answer(text, reply_markup=keyboard, parse_mode="HTML")

        # Confirm the manual edit
        await call.message.answer(
            t("manual_edit_accepted", {"text": original_text}, lang=lang)
            or f'✅ Your input "{original_text}" has been accepted as is.',
            parse_mode="HTML",
        )
    else:
        # Simply acknowledge the rejection without changes
        await call.message.answer(
            t("suggestion_rejected", {}, lang=lang)
            or "Suggestion rejected. You can try a different name.",
            parse_mode="HTML",
        )

    # Answer callback query
    await call.answer()

    # Stay in the same state for continued editing