"""
Enhanced version of photo_handler using IncrementalUI.

This module provides an asynchronous photo handler for recognizing
and analyzing invoices with progressive UI updates.
"""

import asyncio
import logging
import uuid
import os
import tempfile
from pathlib import Path
from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.enums import ParseMode

from app.utils.incremental_ui import IncrementalUI
from app import ocr, matcher, data_loader
from app.formatters.report import build_report
from app.keyboards import build_main_kb
from app.utils.md import clean_html
from app.i18n import t

# Import NotaStates from states module
from app.fsm.states import NotaStates

logger = logging.getLogger(__name__)

# Создаем роутер для регистрации обработчика
router = Router()

@router.message(F.photo)
async def photo_handler_incremental(message: Message, state: FSMContext):
    """
    Processes uploaded invoice photos with progressive UI updates.
    
    Provides the user with visual information about the processing at each stage:
    1. Photo download
    2. OCR recognition
    3. Position matching
    4. Report generation
    
    Args:
        message: Incoming Telegram message with photo
        state: User's FSM context
    """
    # Get user language preference
    data = await state.get_data()
    lang = data.get("lang", "en")
    
    # Debug data
    user_id = message.from_user.id
    photo_id = message.photo[-1].file_id if message.photo else None
    req_id = uuid.uuid4().hex[:8]  # Unique request ID for logging
    
    # Check if already processing a photo
    if data.get("processing_photo"):
        logger.warning(f"Already processing a photo for user {user_id}, ignoring new photo")
        await message.answer(
            t("status.wait_for_processing", lang=lang) or "Please wait while I finish processing your current photo.",
            parse_mode=None
        )
        return
    
    # Set processing flag
    await state.update_data(processing_photo=True)
    
    logger.info(f"[{req_id}] Received new photo from user {user_id}")
    
    # Initialize IncrementalUI
    ui = IncrementalUI(message.bot, message.chat.id)
    await ui.start(t("status.receiving_image", lang=lang) or "📸 Receiving image...")
    
    try:
        # Step 1: Download photo
        # Get file information
        file = await message.bot.get_file(message.photo[-1].file_id)
        
        # Animate loading process
        await ui.start_spinner()
        
        # Download file content
        img_bytes_io = await message.bot.download_file(file.file_path)
        img_bytes = img_bytes_io.getvalue()
        
        # Stop spinner and update UI
        ui.stop_spinner()
        await ui.update(t("status.image_received", lang=lang) or "✅ Image received")
        logger.info(f"[{req_id}] Downloaded photo, size {len(img_bytes)} bytes")
        
        # Step 2: OCR image
        await ui.append(t("status.recognizing_text", lang=lang) or "🔍 Recognizing text (OCR)...")
        await ui.start_spinner()
        
        # Run OCR without await since it's not an async function
        ocr_result = ocr.call_openai_ocr(img_bytes)
        
        ui.stop_spinner()
        positions_count = len(ocr_result.positions) if ocr_result.positions else 0
        await ui.update(t("status.text_recognized", {"count": positions_count}, lang=lang) or 
                       f"✅ Text recognized: found {positions_count} items")
        logger.info(f"[{req_id}] OCR completed successfully, found {positions_count} items")
        
        # Step 3: Match with products
        await ui.append(t("status.matching_items", lang=lang) or "🔄 Matching items...")
        await ui.start_spinner()
        
        # Load product database with caching
        from app.utils.cached_loader import cached_load_products
        products = cached_load_products("data/base_products.csv", data_loader.load_products)
        
        # Match positions
        match_results = matcher.match_positions(ocr_result.positions, products)
        
        # Calculate matching statistics
        ok_count = sum(1 for item in match_results if item.get("status") == "ok")
        unknown_count = sum(1 for item in match_results if item.get("status") == "unknown")
        partial_count = positions_count - ok_count - unknown_count
        
        ui.stop_spinner()
        await ui.update(t("status.matching_completed", 
                         {"ok": ok_count, "unknown": unknown_count, "partial": partial_count},
                         lang=lang) or 
                       f"✅ Matching completed: {ok_count} ✓, {unknown_count} ❌, {partial_count} ⚠️")
        logger.info(f"[{req_id}] Matching completed: {ok_count} OK, {unknown_count} unknown, {partial_count} partial")
        
        # Save data for access in other handlers
        from bot import user_matches
        user_matches[(user_id, 0)] = {  # 0 - temporary ID, will be updated below
            "parsed_data": ocr_result,
            "match_results": match_results,
            "photo_id": photo_id,
            "req_id": req_id,
        }
        
        # Step 4: Generate report
        await ui.append(t("status.generating_report", lang=lang) or "📋 Generating report...")
        await ui.start_spinner()
        
        # Create report with HTML formatting
        report_text, has_errors = build_report(ocr_result, match_results, escape_html=True)
        
        # Save invoice in state for access in edit mode
        await state.update_data(invoice=ocr_result, lang=lang)
        
        # New keyboard - only "Edit", "Cancel" and "Confirm" buttons (if no errors)
        inline_kb = build_main_kb(has_errors=True if unknown_count + partial_count > 0 else False, lang=lang)
        
        ui.stop_spinner()
        # Complete UI with brief summary
        await ui.complete(t("status.processing_completed", lang=lang) or "✅ Photo processing completed!")
        
        # Send full report as a separate message
        try:
            # Check message for potential HTML problems before sending
            telegram_html_tags = ["<b>", "<i>", "<u>", "<s>", "<strike>", "<del>", "<code>", "<pre>", "<a"]
            has_valid_html = any(tag in report_text for tag in telegram_html_tags)
            
            # Try to send with HTML first if we have valid HTML tags
            if has_valid_html:
                result = await message.answer(report_text, reply_markup=inline_kb, parse_mode="HTML")
            else:
                # If no HTML tags, send without parse_mode
                result = await message.answer(report_text, reply_markup=inline_kb)
            
            # Update message ID in user_matches
            new_key = (user_id, result.message_id)
            user_matches[new_key] = user_matches.pop((user_id, 0))
            
            # Save message ID in state for future reference
            await state.update_data(invoice_msg_id=result.message_id)
            
            logger.info(f"[{req_id}] Report sent successfully")
            
        except Exception as msg_err:
            logger.error(f"[{req_id}] Error sending report: {str(msg_err)}")
            # Try to send without HTML formatting as fallback
            try:
                clean_report = clean_html(report_text)
                result = await message.answer(clean_report, reply_markup=inline_kb)
                new_key = (user_id, result.message_id)
                user_matches[new_key] = user_matches.pop((user_id, 0))
                await state.update_data(invoice_msg_id=result.message_id)
                logger.info(f"[{req_id}] Report sent with fallback formatting")
            except Exception as final_err:
                logger.error(f"[{req_id}] Critical error sending report: {str(final_err)}")
                await message.answer(
                    t("error.report_failed", lang=lang) or 
                    "Error generating report. Please try again or contact support."
                )
        
        # Set state to editing mode
        await state.set_state(NotaStates.editing)
        
    except Exception as e:
        logger.error(f"[{req_id}] Error processing photo: {str(e)}")
        error_msg = t("error.processing_failed", lang=lang) or "Error processing photo. Please try again."
        # Показываем ошибку через UI
        await ui.error(error_msg)
        await state.set_state(NotaStates.main_menu)
    finally:
        # Clear processing flag
        await state.update_data(processing_photo=False)
        # Останавливаем спиннер, если он все еще активен
        ui.stop_spinner()