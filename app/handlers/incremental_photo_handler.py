"""
Enhanced version of photo_handler using IncrementalUI.

This module provides an asynchronous photo handler for recognizing
and analyzing invoices with progressive UI updates.
"""

import asyncio
import json
import logging
import os
import tempfile
from pathlib import Path
import uuid
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.enums import ParseMode
from typing import Dict, List, Optional, Tuple

from app.utils.incremental_ui import IncrementalUI
from app import ocr, matcher, data_loader
from app.formatters.report import build_report
from app.keyboards import build_main_kb, kb_main
from app.utils.md import clean_html
from app.i18n import t
from app.config import settings

# Import NotaStates from states module
from app.fsm.states import NotaStates
from app.utils.task_manager import register_task, cancel_task
from app.utils.file_manager import temp_file, save_test_image, cleanup_temp_files
from app.utils.processing_pipeline import process_invoice_pipeline
from app.utils.incremental_ui_example import split_message

logger = logging.getLogger(__name__)

# Создаем роутер для регистрации обработчика
router = Router()

@router.message(F.photo)
async def photo_handler_incremental(message: Message, state: FSMContext):
    """
    Processes uploaded invoice photos with progressive UI updates.
    
    Provides the user with visual information about the processing at each stage:
    1. Photo download
    2. Image preprocessing
    3. OCR recognition
    4. Position matching
    5. Report generation
    
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
    
    # --- ОТМЕНА ПРЕДЫДУЩЕЙ ЗАДАЧИ ---
    prev_task_id = data.get("current_ocr_task")
    if prev_task_id:
        cancel_task(prev_task_id)
        logger.info(f"[{req_id}] Cancelled previous task {prev_task_id} for user {user_id}")
    # ---
    
    # Принудительно сбрасываем флаг обработки фото, даже если он был установлен
    # Это позволит начать обработку нового фото, даже если предыдущее зависло
    await state.update_data(processing_photo=False)
    
    # Проверяем снова, чтобы убедиться, что флаг сброшен
    data = await state.get_data()
    
    # Set processing flag
    await state.update_data(processing_photo=True)
    
    # --- РЕГИСТРАЦИЯ НОВОЙ ЗАДАЧИ ---
    task_id = f"ocr_{user_id}_{req_id}"
    current_task = asyncio.current_task()
    register_task(task_id, current_task)
    await state.update_data(current_ocr_task=task_id)
    
    # Очистка старых временных файлов
    cleanup_count = await asyncio.to_thread(cleanup_temp_files, False)
    if cleanup_count > 0:
        logger.info(f"Cleaned up {cleanup_count} old temporary files")

    logger.info(f"[{req_id}] Received new photo from user {user_id}")
    
    # Initialize IncrementalUI
    ui = IncrementalUI(message.bot, message.chat.id)
    await ui.start(t("status.receiving_image", lang=lang) or "📸 Receiving image...")
    
    try:
        # Step 1: Download photo
        # Get file information
        file = await message.bot.get_file(message.photo[-1].file_id)
        
        # Получаем и выводим URL для тестирования с OpenAI
        token = getattr(message.bot, 'token', os.environ.get('BOT_TOKEN', 'UNKNOWN_TOKEN'))
        file_url = f"https://api.telegram.org/file/bot{token}/{file.file_path}"
        logger.info(f"[{req_id}] TELEGRAM IMAGE URL: {file_url}")
        
        # Сохраняем в файл для последующего тестирования в OpenAI Playground
        try:
            img_path = f"/tmp/telegram_image_{req_id}.jpg"
            # Animate loading process
            await ui.start_spinner()
            
            # Download file content
            img_bytes_io = await message.bot.download_file(file.file_path)
            img_bytes = img_bytes_io.getvalue()
            
            # Сохраняем копию для тестирования
            with open(img_path, 'wb') as f:
                f.write(img_bytes)
            logger.info(f"[{req_id}] Saved test image to {img_path}")
            
            # Stop spinner and update UI
            ui.stop_spinner()
            await ui.update(t("status.image_received", lang=lang) or "✅ Image received")
            logger.info(f"[{req_id}] Downloaded photo, size {len(img_bytes)} bytes")
        except Exception as e:
            logger.error(f"[{req_id}] Error saving test image: {e}")
            ui.stop_spinner()  # Все равно останавливаем спиннер
            
            # Продолжаем обычную обработку фото при ошибке сохранения тестового файла
            # Download file content снова, если не удалось ранее
            if 'img_bytes' not in locals():
                img_bytes_io = await message.bot.download_file(file.file_path)
                img_bytes = img_bytes_io.getvalue()
                await ui.update(t("status.image_received", lang=lang) or "✅ Image received")
                logger.info(f"[{req_id}] Downloaded photo, size {len(img_bytes)} bytes")
        
        # Step 2: OCR изображения
        await ui.append(t("status.analyzing_image", lang=lang) or "🖼️ Analyzing image...")
        await ui.start_spinner()
        with temp_file(f"ocr_{req_id}", ".jpg") as tmp_path:
            with open(tmp_path, "wb") as f:
                f.write(img_bytes)
            # Новый асинхронный пайплайн
            try:
                processed_bytes, ocr_result = await process_invoice_pipeline(
                    img_bytes, tmp_path, req_id
                )
                img_bytes = processed_bytes
                ui.stop_spinner()
                positions_count = len(ocr_result.positions) if ocr_result and ocr_result.positions else 0
                await ui.update(t("status.text_recognized", {"count": positions_count}, lang=lang) or 
                               f"✅ Text recognized: found {positions_count} items")
                logger.info(f"[{req_id}] OCR completed successfully, found {positions_count} items")
            except Exception as ocr_err:
                ui.stop_spinner()
                logger.error(f"[{req_id}] OCR error: {ocr_err.__class__.__name__}: {str(ocr_err)}")
                await ui.update(t("status.text_recognition_failed", lang=lang) or "❌ Text recognition failed")
                raise
        
        # Step 3: Playground image (save_test_image)
        test_image_path = await asyncio.to_thread(save_test_image, img_bytes, req_id)
        if test_image_path:
            base_url = data.get("base_url", getattr(settings, "BASE_URL", ""))
            if base_url:
                playground_msg = f"🔍 Для тестирования в playground: {base_url}/{test_image_path}"
                await message.answer(playground_msg)
                logger.info(f"[{req_id}] Отправлена ссылка на тестовое изображение")
        
        # Step 4: Match with products
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
        
        # Step 5: Generate report
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
            telegram_html_tags = ["<b>", "<i>", "<u>", "", "<strike>", "<del>", "<code>", "<pre>", "<a"]
            has_valid_html = any(tag in report_text for tag in telegram_html_tags)
            
            if "<pre>" in report_text and "</pre>" not in report_text:
                logger.warning("Unclosed <pre> tag detected in message, attempting to fix")
                report_text = report_text.replace("<pre>", "<pre>") + "</pre>"
                
            logger.debug(f"Sending report with HTML formatting (valid HTML tags: {has_valid_html})")
            for part in split_message(report_text):
                report_msg = await message.answer(
                    part,
                    reply_markup=inline_kb,
                    parse_mode=ParseMode.HTML
                )
            logger.debug(f"Successfully sent HTML-formatted report with message_id={report_msg.message_id}")
        except Exception as html_err:
            logger.warning(f"Error sending HTML report: {str(html_err)}")
            
            # If that doesn't work, try without formatting
            try:
                logger.debug("Attempting to send report without formatting")
                report_msg = await message.answer(
                    report_text,
                    reply_markup=inline_kb,
                    parse_mode=None
                )
                logger.debug(f"Successfully sent plain report with message_id={report_msg.message_id}")
            except Exception as plain_err:
                logger.warning(f"Error sending plain report: {str(plain_err)}")
                
                # Last option - clean HTML from text and send
                try:
                    logger.debug("Sending report with cleaned HTML")
                    cleaned_message = clean_html(report_text)
                    report_msg = await message.answer(
                        cleaned_message,
                        reply_markup=inline_kb,
                        parse_mode=None
                    )
                    logger.debug(f"Successfully sent cleaned report with message_id={report_msg.message_id}")
                except Exception as clean_err:
                    logger.error(f"All report sending attempts failed: {str(clean_err)}")
                    
                    # Last resort - send a brief summary
                    try:
                        simple_message = t("status.brief_summary", {"total": positions_count, "ok": ok_count, "issues": unknown_count + partial_count}, lang=lang) or (
                            f"📋 Found {positions_count} items. "
                            f"✅ OK: {ok_count}. "
                            f"⚠️ Issues: {unknown_count + partial_count}."
                        )
                        report_msg = await message.answer(
                            simple_message, 
                            reply_markup=inline_kb, 
                            parse_mode=None
                        )
                        logger.debug(f"Sent summary message with message_id={report_msg.message_id}")
                    except Exception as final_err:
                        logger.error(f"All message attempts failed: {str(final_err)}")
                        report_msg = None
        
        # If message was sent successfully, update links in user_matches
        if report_msg:
            try:
                # Update message_id in user_matches
                entry = user_matches.pop((user_id, 0), None)
                if entry:
                    new_key = (user_id, report_msg.message_id)
                    user_matches[new_key] = entry
                    logger.debug(f"Updated user_matches with new message_id={report_msg.message_id}")
            except Exception as key_err:
                logger.error(f"Error updating user_matches: {str(key_err)}")
        
        # Update user state and clear processing flag
        await state.update_data(processing_photo=False)
        await state.set_state(NotaStates.editing)
        logger.info(f"[{req_id}] Invoice processing completed for user {user_id}")
        
    except Exception as e:
        logger.error(f"[{req_id}] Error processing photo: {str(e)}", exc_info=True)
        
        # Complete UI with error message
        await ui.error(
            t("error.photo_processing", lang=lang) or 
            "An error occurred while processing the photo. Please try again or contact the administrator."
        )
        
        # Clear processing flag
        await state.update_data(processing_photo=False)
        
        # Return to initial state
        await state.set_state(NotaStates.main_menu)
    finally:
        await state.update_data(processing_photo=False)
        await state.update_data(current_ocr_task=None)