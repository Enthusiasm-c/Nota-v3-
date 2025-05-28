"""
Handler for processing invoice confirmation and Syrve integration.
"""

import json
import logging
import os
from datetime import datetime, date
from decimal import Decimal

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from dotenv import load_dotenv

from app.alias import learn_from_invoice
from app.config import settings
from app.i18n import t
from app.keyboards import kb_main
from app.services.unified_syrve_client import UnifiedSyrveClient, Invoice, InvoiceItem
from app.utils.monitor import increment_counter
from app.utils.redis_cache import cache_set

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

# Create router for handler registration
router = Router()


def get_syrve_client():
    """
    Initialize and return unified Syrve client with current environment settings
    """
    try:
        return UnifiedSyrveClient.from_env()
    except Exception as e:
        logger.error(f"Failed to create Syrve client: {e}")
        raise


@router.callback_query(F.data == "confirm:invoice")
async def handle_invoice_confirm(callback: CallbackQuery, state: FSMContext):
    """
    Handle first confirmation click - show confirmation dialog with Yes/No buttons.
    """
    try:
        # Immediately answer the callback to prevent timeout
        await callback.answer()

        # Get user language
        data = await state.get_data()
        lang = data.get("lang", "en")

        # Get invoice data from state
        invoice = data.get("invoice")
        if not invoice:
            await callback.message.answer(t("error.invoice_not_found", {}, lang=lang))
            return

        # Show confirmation dialog with Yes/No buttons
        confirm_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Yes, send to Syrve", callback_data="confirm:invoice:final"
                    ),
                    InlineKeyboardButton(
                        text="❌ No, cancel", callback_data="confirm:invoice:cancel"
                    ),
                ]
            ]
        )

        # Show confirmation message
        await callback.message.edit_text(
            "🚨 <b>Confirm sending invoice to Syrve?</b>\n\n"
            "This action cannot be undone. The invoice will be permanently submitted to the restaurant system.",
            reply_markup=confirm_kb,
            parse_mode="HTML",
        )

    except Exception as e:
        logger.error(f"Error in confirmation dialog: {str(e)}", exc_info=True)
        await callback.message.answer("An error occurred. Please try again.")


@router.callback_query(F.data == "confirm:invoice:cancel")
async def handle_invoice_confirm_cancel(callback: CallbackQuery, state: FSMContext):
    """
    Handle confirmation cancellation - restore original report.
    """
    try:
        await callback.answer("Sending cancelled")

        # Get data from state
        data = await state.get_data()
        lang = data.get("lang", "en")
        invoice = data.get("invoice")
        match_results = data.get("match_results", [])

        if not invoice:
            await callback.message.answer("Invoice not found. Please send a new photo.")
            return

        # Restore original report
        from app.formatters.report import build_report
        from app.keyboards import build_main_kb

        report_text, has_errors = build_report(invoice, match_results, escape_html=True)

        # Add helpful instructions
        if has_errors:
            instructions = "\n\n💬 <i>Just type your edits: 'line 3 qty 5' or 'date 2024-12-25'</i>"
        else:
            instructions = "\n\n💬 <i>Ready to confirm! Or edit with: 'line 3 qty 5'</i>"

        final_text = report_text + instructions

        # Restore original keyboard
        keyboard = build_main_kb(has_errors=has_errors, lang=lang)

        await callback.message.edit_text(final_text, reply_markup=keyboard, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Error cancelling confirmation: {str(e)}", exc_info=True)
        await callback.message.answer("An error occurred. Please try again.")


@router.callback_query(F.data == "confirm:invoice:final")
async def handle_invoice_confirm_final(callback: CallbackQuery, state: FSMContext):
    """
    Handle confirmation of invoice and send to Syrve.

    Args:
        callback: Callback query from the Confirm button
        state: FSM context
    """
    try:
        # Immediately answer the callback to prevent timeout
        await callback.answer(show_alert=False)

        # Get user language
        data = await state.get_data()
        lang = data.get("lang", "en")

        # Get invoice data from state
        invoice = data.get("invoice")
        if not invoice:
            await callback.message.answer(t("error.invoice_not_found", {}, lang=lang))
            return

        # Show processing indicator
        processing_msg = await callback.message.answer(t("status.sending_to_syrve", {}, lang=lang))

        # Initialize Syrve client
        syrve_client = get_syrve_client()

        # Get match results from state if available
        match_results = data.get("match_results", [])
        
        # ПРОВЕРКА: Если в match_results нет поля id, регенерируем их
        needs_regeneration = False
        if match_results:
            for result in match_results:
                if result.get("status") == "ok" and not result.get("id"):
                    needs_regeneration = True
                    break
        
        if needs_regeneration:
            logger.warning("match_results missing id field, regenerating...")
            from app.matcher import match_positions
            from app.data_loader import load_products
            
            # Получаем позиции из накладной
            positions = getattr(invoice, "positions", [])
            if not positions and hasattr(invoice, "__dict__"):
                positions = invoice.__dict__.get("positions", [])
            
            # Регенерируем match_results с правильными id
            products = load_products()
            match_results = match_positions(positions, products)
            
            # Сохраняем обновленные результаты в состояние
            await state.update_data(match_results=match_results)
            logger.info(f"Regenerated {len(match_results)} match_results with id fields")

        # Подготовка данных для автоматического обучения алиасов
        positions = []
        for pos in match_results:
            if pos.get("status") == "partial":
                # Добавляем информацию о сопоставленном продукте
                matched_product = {
                    "id": pos.get("product_id", ""),
                    "name": pos.get("matched_name", ""),
                }
                positions.append(
                    {
                        "name": pos.get("name", ""),
                        "status": pos.get("status", ""),
                        "matched_product": matched_product,
                        "match_reason": pos.get("match_reason", ""),
                    }
                )

        # Автоматическое обучение алиасов
        if positions:
            try:
                added_count, added_aliases = learn_from_invoice(positions)
                if added_count > 0:
                    logger.info(
                        f"Automatically added {added_count} aliases: {', '.join(added_aliases)}"
                    )
            except Exception as e:
                logger.error(f"Error learning aliases from invoice: {str(e)}", exc_info=True)

        # Extract manual supplier if set by user  
        manual_supplier = None
        if hasattr(invoice, 'supplier'):
            manual_supplier = invoice.supplier
        elif isinstance(invoice, dict):
            manual_supplier = invoice.get('supplier')
        elif hasattr(invoice, '__dict__') and 'supplier' in invoice.__dict__:
            manual_supplier = invoice.__dict__['supplier']
        
        # Prepare data for Syrve XML generation
        try:
            syrve_data = prepare_invoice_data(invoice, match_results, manual_supplier)
        except ValueError as e:
            # Ошибка маппинга поставщика - показываем пользователю понятное сообщение
            await processing_msg.edit_text(
                f"❌ Ошибка поставщика:\n\n{str(e)}",
                reply_markup=kb_main(lang)
            )
            increment_counter("nota_invoices_total", {"status": "supplier_error"})
            return

        # Generate XML with OpenAI using global client if available
        from app.config import get_ocr_client

        openai_client = get_ocr_client()
        if not openai_client:
            # Если не удалось получить клиент из глобального кэша, создаем новый
            from openai import AsyncOpenAI

            ocr_key = os.getenv("OPENAI_OCR_KEY", getattr(settings, "OPENAI_OCR_KEY", ""))
            if not ocr_key:
                logger.warning("OPENAI_OCR_KEY не установлен, пытаемся использовать OPENAI_API_KEY")
                ocr_key = os.getenv("OPENAI_API_KEY", getattr(settings, "OPENAI_API_KEY", ""))
            openai_client = AsyncOpenAI(api_key=ocr_key)

        # Timer for invoice processing
        start_time = datetime.now()
        # Создание Invoice объекта и отправка
        try:
            # Convert syrve_data to Invoice object
            items = []
            for i, item_data in enumerate(syrve_data.get("items", []), 1):
                items.append(InvoiceItem(
                    num=i,
                    product_id=item_data["product_id"],
                    amount=Decimal(str(item_data["quantity"])),
                    price=Decimal(str(item_data["price"])),
                    sum=Decimal(str(item_data["quantity"])) * Decimal(str(item_data["price"])),
                ))
            
            invoice = Invoice(
                items=items,
                supplier_id=syrve_data["supplier_id"],
                default_store_id=syrve_data["store_id"],
                conception_id=syrve_data.get("conception_id"),
                document_number=syrve_data.get("invoice_number"),
                date_incoming=date.fromisoformat(syrve_data["invoice_date"]) if syrve_data.get("invoice_date") else None,
            )
            
            # Send invoice to Syrve
            result = await syrve_client.send_invoice_async(invoice)
            
        except Exception as e:
            logger.error(f"Error sending to Syrve: {str(e)}", exc_info=True)
            await processing_msg.edit_text(
                t(
                    "error.syrve_error",
                    {"message": "Error sending to Syrve: " + str(e)},
                    lang=lang,
                ),
                reply_markup=kb_main(lang),
            )
            increment_counter("nota_invoices_total", {"status": "failed"})
            return
        
        processing_time = (datetime.now() - start_time).total_seconds()
        logger.info(f"Invoice processing took {processing_time:.2f} seconds")

        # Проверка результата
        if result.get("success", False):
            # Success - update UI
            # Use optimized safe edit instead of direct edit
            server_number = result.get("document_number", "unknown")
            from app.utils.optimized_safe_edit import optimized_safe_edit

            await optimized_safe_edit(
                callback.bot,
                callback.message.chat.id,
                processing_msg.message_id,
                t("status.syrve_success", {"id": f"✅ Импорт OK · № {server_number}"}, lang=lang),
            )

            # Track successful upload
            increment_counter("nota_invoices_total", {"status": "ok"})

            # Save invoice data for reference (using server number)
            cache_set(f"invoice:{server_number}", json.dumps(syrve_data), ex=86400)  # 24 hours

        else:
            # Ошибка от Syrve или OpenAI
            error_msg = result.get("errorMessage") or result.get("error") or "Unknown error"
            status = result.get("status", 500)
            # Проверка на ошибки структуры/валидации
            if "Missing required field" in error_msg or "Invalid" in error_msg:
                error_text = t("error.syrve_error", {"message": error_msg}, lang=lang)
            elif status == 401:
                error_text = t("error.syrve_auth", {}, lang=lang)
            elif status in (403, 409):
                error_text = t("error.syrve_duplicate", {}, lang=lang)
            else:
                short_error = error_msg[:50] + ("..." if len(error_msg) > 50 else "")
                error_text = t("error.syrve_error", {"message": short_error}, lang=lang)
                if status == 500:
                    admin_chat_id = os.getenv(
                        "ADMIN_CHAT_ID", getattr(settings, "ADMIN_CHAT_ID", None)
                    )
                    if admin_chat_id:
                        try:
                            await callback.bot.send_message(
                                admin_chat_id, f"⚠️ Syrve error (ID: {server_number}):\n{error_msg}"
                            )
                        except Exception as e:
                            logger.error(f"Failed to send admin alert: {str(e)}")
            await processing_msg.edit_text(error_text, reply_markup=kb_main(lang))
            increment_counter("nota_invoices_total", {"status": "failed"})

    except Exception as e:
        logger.error(f"Необработанная ошибка при отправке в Syrve: {str(e)}", exc_info=True)
        await callback.message.answer(
            t("error.syrve_error", {"message": str(e)}, lang=lang), reply_markup=kb_main(lang)
        )
        increment_counter("nota_invoices_total", {"status": "failed"})

    # ИСПРАВЛЕНИЕ: НЕ переводим пользователя в главное меню
    # Оставляем в состоянии редактирования для возможности дальнейших изменений
    # Данные invoice и match_results остаются в state для продолжения редактирования
    # await state.set_state(NotaStates.main_menu)  # УДАЛЕНО!


def prepare_invoice_data(invoice, match_results, manual_supplier=None):
    """
    Prepare invoice data for Syrve XML generation.

    Args:
        invoice: Invoice data from state
        match_results: Match results with product IDs
        manual_supplier: Manual supplier name entered by user (optional)

    Returns:
        Dictionary with structured data for XML generation
    """
    # Get IDs from environment variables
    conception_id = os.getenv("SYRVE_CONCEPTION_ID")  # Optional - only if server requires

    store_id = os.getenv("SYRVE_STORE_ID")
    if not store_id:
        logger.error("SYRVE_STORE_ID not set in environment")
        raise ValueError("SYRVE_STORE_ID environment variable is required")

    # Resolve supplier using mapping system
    from app.supplier_mapping import resolve_supplier_for_invoice
    
    # Convert invoice to dict for supplier resolution
    invoice_dict = {}
    if hasattr(invoice, '__dict__'):
        invoice_dict = invoice.__dict__
    elif hasattr(invoice, 'to_dict'):
        invoice_dict = invoice.to_dict()
    elif isinstance(invoice, dict):
        invoice_dict = invoice
    else:
        # Fallback: try to extract supplier from common attributes
        supplier = getattr(invoice, 'supplier', None)
        if supplier:
            invoice_dict = {'supplier': supplier}
    
    supplier_id = resolve_supplier_for_invoice(invoice_dict, manual_supplier)

    # Get invoice date with validation
    invoice_date = getattr(invoice, "date", None)
    if not invoice_date and hasattr(invoice, "__dict__"):
        invoice_date = invoice.__dict__.get("date")

    # Check if date is missing and warn user
    date_missing = False
    if not invoice_date:
        date_missing = True
        logger.warning("Invoice date is missing from OCR - using current date as fallback")
        
        # Show warning to user about missing date
        try:
            current_date_formatted = datetime.now().strftime('%d.%m.%Y')
            warning_msg = (
                "⚠️ <b>Warning: Invoice date not recognized!</b>\n\n"
                f"OCR could not extract the date from the invoice.\n"
                f"Current date will be used: {current_date_formatted}\n\n"
                f"💡 <i>If this is incorrect, cancel sending and fix the date with command: 'date 2025-05-15'</i>"
            )
            
            # Send warning message
            await callback.bot.send_message(
                callback.message.chat.id,
                warning_msg,
                parse_mode="HTML"
            )
            
            # Add a small delay to ensure user sees the warning
            import asyncio
            await asyncio.sleep(2)
            
        except Exception as e:
            logger.error(f"Failed to send date warning: {e}")

    # Format date if needed
    if hasattr(invoice_date, "isoformat"):
        # Handle datetime.date objects
        invoice_date = invoice_date.isoformat()
    elif isinstance(invoice_date, datetime):
        invoice_date = invoice_date.strftime("%Y-%m-%d")
    elif not invoice_date:
        invoice_date = datetime.now().strftime("%Y-%m-%d")

    # Process items from match_results instead of invoice.positions
    items = []
    
    logger.debug(f"prepare_invoice_data: match_results count = {len(match_results) if match_results else 0}")
    logger.debug(f"prepare_invoice_data: match_results type = {type(match_results)}")
    
    if not match_results:
        logger.error("No match_results provided to prepare_invoice_data")
        raise ValueError("No match results to process")

    for i, match_item in enumerate(match_results):
        # Debug logging
        logger.debug(f"Processing match_result {i}: keys = {list(match_item.keys()) if match_item else 'None'}")
        logger.debug(f"match_item = {match_item}")
        
        # Get local product ID first
        local_id = match_item.get("id")
        
        # If no 'id' field, try to extract from matched_product
        if not local_id and match_item.get("matched_product"):
            local_id = match_item["matched_product"].get("id")
        
        # Get Syrve GUID from mapping
        from app.syrve_mapping import get_syrve_guid
        product_id = get_syrve_guid(local_id) if local_id else None
        
        if product_id:
            logger.debug(f"Position {i}: mapped {local_id} -> {product_id}")
        else:
            logger.warning(f"Position {i}: No Syrve mapping for local_id = {local_id}")
            # For now, use local ID as fallback (will likely fail in Syrve)
            product_id = local_id
        
        logger.debug(f"Position {i}: final product_id = {product_id}")

        # Skip items without product ID or with status != 'ok'
        if not product_id or match_item.get("status") != "ok":
            logger.warning(f"Skipping position {i}: no product_id or status not ok")
            continue

        # Get quantity and price from match_result
        qty = match_item.get("qty", 0)
        price = match_item.get("price", 0)
        
        # Calculate sum (quantity * price)
        sum_value = float(qty) * float(price)

        # Add item to list
        item_data = {
            "product_id": product_id,
            "quantity": float(qty),
            "price": float(price),
            "sum": round(sum_value, 2)  # Round to 2 decimal places
        }
        
        # Add store_id if different from default
        if match_item.get("store_id") and match_item["store_id"] != store_id:
            item_data["store"] = match_item["store_id"]
            
        items.append(item_data)

    # Validate that we have items to process
    if not items:
        logger.error("No valid items found in invoice for Syrve export")
        raise ValueError("Invoice contains no valid items with product IDs")

    # Create final data structure
    result = {
        "invoice_date": invoice_date,
        "supplier_id": supplier_id,
        "store_id": store_id,
        "items": items,
    }
    
    # Add conception_id only if it's provided
    if conception_id:
        result["conception_id"] = conception_id

    # Add document number only if it exists in invoice
    doc_number = getattr(invoice, "document_number", None)
    if doc_number is not None:
        result["invoice_number"] = doc_number

    return result
