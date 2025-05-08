"""
Handler for processing invoice confirmation and Syrve integration.
"""

import logging
import os
import json
import uuid
from datetime import datetime
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from app.fsm.states import NotaStates
from app.syrve_client import SyrveClient, generate_invoice_xml
from app.keyboards import kb_main
from app.i18n import t
from app.config import settings
from app.utils.monitor import increment_counter
from app.utils.redis_cache import cache_set
from app.alias import learn_from_invoice

logger = logging.getLogger(__name__)

# Create router for handler registration
router = Router()

# Initialize Syrve client
syrve_client = SyrveClient(
    api_url=os.getenv("SYRVE_API_URL", getattr(settings, "SYRVE_API_URL", "")),
    login=os.getenv("SYRVE_LOGIN", getattr(settings, "SYRVE_LOGIN", "")),
    password=os.getenv("SYRVE_PASSWORD", getattr(settings, "SYRVE_PASSWORD", ""))
)

@router.callback_query(F.data == "confirm:invoice")
async def handle_invoice_confirm(callback: CallbackQuery, state: FSMContext):
    """
    Handle confirmation of invoice and send to Syrve.
    
    Args:
        callback: Callback query from the Confirm button
        state: FSM context
    """
    # Get user language
    data = await state.get_data()
    lang = data.get("lang", "en")
    
    # Get invoice data from state
    invoice = data.get("invoice")
    if not invoice:
        await callback.message.answer(t("error.invoice_not_found", {}, lang=lang))
        await callback.answer()
        return
    
    # Show processing indicator
    await callback.answer(t("status.processing", {}, lang=lang), show_alert=False)
    
    # First message - processing started
    processing_msg = await callback.message.answer(t("status.sending_to_syrve", {}, lang=lang))
    
    try:
        # Generate invoice ID
        invoice_id = f"NOTA-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"
        
        # Get match results from state if available
        match_results = data.get("match_results", [])
        
        # Подготовка данных для автоматического обучения алиасов
        positions = []
        for pos in match_results:
            if pos.get("status") == "partial":
                # Добавляем информацию о сопоставленном продукте
                matched_product = {
                    "id": pos.get("product_id", ""),
                    "name": pos.get("matched_name", "")
                }
                positions.append({
                    "name": pos.get("name", ""),
                    "status": pos.get("status", ""),
                    "matched_product": matched_product,
                    "match_reason": pos.get("match_reason", "")
                })
        
        # Автоматическое обучение алиасов
        if positions:
            try:
                added_count, added_aliases = learn_from_invoice(positions)
                if added_count > 0:
                    logger.info(f"Automatically added {added_count} aliases: {', '.join(added_aliases)}")
            except Exception as e:
                logger.error(f"Error learning aliases from invoice: {str(e)}", exc_info=True)
        
        # Prepare data for Syrve XML generation
        syrve_data = prepare_invoice_data(invoice, match_results, invoice_id)
        
        # Generate XML with OpenAI using global client if available
        from app.config import get_ocr_client
        openai_client = get_ocr_client() or AsyncOpenAI(api_key=os.getenv("OPENAI_OCR_KEY", getattr(settings, "OPENAI_OCR_KEY", "")))
        
        # Timer for XML generation to track performance
        start_time = datetime.now()
        xml = await generate_invoice_xml(syrve_data, openai_client)
        generation_time = (datetime.now() - start_time).total_seconds()
        logger.info(f"XML generation took {generation_time:.2f} seconds")
        
        # Authenticate with Syrve
        auth_token = await syrve_client.auth()
        
        # Send to Syrve
        result = await syrve_client.import_invoice(auth_token, xml)
        
        # Process result
        if result.get("valid", False):
            # Success - update UI
            # Use optimized safe edit instead of direct edit
            from app.utils.optimized_safe_edit import optimized_safe_edit
            await optimized_safe_edit(
                callback.bot,
                callback.message.chat.id,
                processing_msg.message_id,
                t("status.syrve_success", {"id": invoice_id}, lang=lang),
                kb=kb_main(lang)
            )
            
            # Track successful upload
            increment_counter("nota_invoices_total", {"status": "ok"})
            
            # Save invoice ID for reference
            cache_set(f"invoice:{invoice_id}", json.dumps(syrve_data), ex=86400)  # 24 hours
            
        else:
            # Error from Syrve
            error_msg = result.get("errorMessage", "Unknown error")
            status = result.get("status", 500)
            
            if status == 401:
                error_text = t("error.syrve_auth", {}, lang=lang)
            elif status in (403, 409):
                error_text = t("error.syrve_duplicate", {}, lang=lang)
            else:
                # Detailed error from Syrve
                # Limit error message length to 50 chars to prevent overly long messages
                short_error = error_msg[:50] + ("..." if len(error_msg) > 50 else "")
                error_text = t("error.syrve_error", {"message": short_error}, lang=lang)
                
                # For 500 errors, log to admin chat
                if status == 500:
                    admin_chat_id = os.getenv("ADMIN_CHAT_ID", getattr(settings, "ADMIN_CHAT_ID", None))
                    if admin_chat_id:
                        try:
                            await callback.bot.send_message(
                                admin_chat_id,
                                f"⚠️ Syrve error (ID: {invoice_id}):\n{error_msg}"
                            )
                        except Exception as e:
                            logger.error(f"Failed to send admin alert: {str(e)}")
            
            # Update UI with error
            await processing_msg.edit_text(
                error_text,
                reply_markup=kb_main(lang)
            )
            
            # Track failed upload
            increment_counter("nota_invoices_total", {"status": "failed"})
    
    except Exception as e:
        # Handle unexpected errors
        logger.error(f"Error processing invoice confirmation: {str(e)}", exc_info=True)
        await processing_msg.edit_text(
            t("error.unexpected", {}, lang=lang),
            reply_markup=kb_main(lang)
        )
        increment_counter("nota_invoices_total", {"status": "failed"})
    
    # Update user state to main menu
    await state.set_state(NotaStates.main_menu)


def prepare_invoice_data(invoice, match_results, invoice_id):
    """
    Prepare invoice data for Syrve XML generation.
    
    Args:
        invoice: Invoice data from state
        match_results: Match results with product IDs
        invoice_id: Generated invoice ID
        
    Returns:
        Dictionary with structured data for XML generation
    """
    # Set default values from settings
    conception_id = os.getenv("SYRVE_CONCEPTION_ID", getattr(settings, "SYRVE_CONCEPTION_ID", ""))
    store_id = os.getenv("SYRVE_STORE_ID", getattr(settings, "SYRVE_STORE_ID", ""))
    
    # Get supplier ID from invoice or use default
    supplier_name = getattr(invoice, "supplier", None)
    if not supplier_name and hasattr(invoice, "__dict__"):
        supplier_name = invoice.__dict__.get("supplier")
    
    # Use default supplier ID if not found
    supplier_id = os.getenv("SYRVE_DEFAULT_SUPPLIER_ID", getattr(settings, "SYRVE_DEFAULT_SUPPLIER_ID", ""))
    
    # Get invoice date
    invoice_date = getattr(invoice, "date", None)
    if not invoice_date and hasattr(invoice, "__dict__"):
        invoice_date = invoice.__dict__.get("date")
    
    # Format date if needed
    if isinstance(invoice_date, datetime):
        invoice_date = invoice_date.strftime("%Y-%m-%d")
    elif not invoice_date:
        invoice_date = datetime.now().strftime("%Y-%m-%d")
    
    # Process items
    items = []
    positions = getattr(invoice, "positions", [])
    if not positions and hasattr(invoice, "__dict__"):
        positions = invoice.__dict__.get("positions", [])
    
    for i, position in enumerate(positions):
        # Get product data
        product_id = None
        match_item = None
        
        # Find matching product in match results
        if match_results and i < len(match_results):
            match_item = match_results[i]
            product_id = match_item.get("product_id")
        
        # Skip items without product ID
        if not product_id:
            continue
        
        # Get quantity and price
        qty = getattr(position, "qty", None)
        if qty is None and isinstance(position, dict):
            qty = position.get("qty")
        
        price = getattr(position, "price", None)
        if price is None and isinstance(position, dict):
            price = position.get("price")
        
        # Add item to list
        items.append({
            "product_id": product_id,
            "quantity": float(qty) if qty is not None else 0,
            "price": float(price) if price is not None else 0
        })
    
    # Create final data structure
    return {
        "invoice_number": invoice_id,
        "invoice_date": invoice_date,
        "conception_id": conception_id,
        "supplier_id": supplier_id,
        "store_id": store_id,
        "items": items
    }