"""
Optimized photo handler for Nota bot.

This module provides a fully asynchronous photo handler
with progressive UI, caching, protection against repeated processing,
and detailed execution time logging.
"""

import asyncio
import logging
import uuid
from typing import Any, Dict, Tuple

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.formatters.report import build_report
from app.fsm.states import NotaStates
from app.i18n import t
from app.keyboards import build_main_kb
from app.matcher import async_match_positions  # Updated import
from app.utils.async_ocr import async_ocr
from app.utils.cached_loader import cached_load_products
from app.utils.incremental_ui import IncrementalUI
from app.utils.md import clean_html
from app.utils.processing_guard import is_processing_photo, require_user_free, set_processing_photo
from app.utils.timing_logger import async_timed
from bot import user_matches

logger = logging.getLogger(__name__)

# Create router for handler registration
router = Router()

# Initialize user_matches if needed
if not isinstance(user_matches, dict):
    user_matches: Dict[Tuple[int, int], Dict[str, Any]] = {}


@router.message(
    F.photo,
    require_user_free(
        context_name="photo_processing", max_age=300
    ),  # 5 minutes maximum blocking time
)
@async_timed(operation_name="photo_processing")
async def optimized_photo_handler(message: Message, state: FSMContext):
    """
    Fully optimized photo handler for Nota bot.
    """
    if not message.from_user:
        await message.answer("Error: Could not identify user")
        return

    req_id = f"photo_{uuid.uuid4().hex[:8]}"
    user_id = message.from_user.id

    # Get current state
    current_state = await state.get_state()

    # Check if user is already processing a photo
    if await is_processing_photo(user_id):
        await message.answer("Processing previous photo")
        return

    # Set photo processing flag
    await set_processing_photo(user_id, True)
    await state.update_data(processing_photo=True)

    try:
        # Ensure message has photos
        if not message.photo or len(message.photo) == 0:
            await message.answer("Send a photo")
            return

        # Get user language from state
        data = await state.get_data()
        lang = data.get("lang", "en")

        # Initialize UI with progressive updates
        ui = IncrementalUI(message.bot, message.chat.id)
        await ui.start(t("status.receiving_image", lang=lang) or "Processing...")

        # 1. Photo download and preparation
        await ui.start_spinner(theme="loading")
        try:
            if not message.photo:
                await ui.error("No photo found in message")
                return

            photo_id = message.photo[-1].file_id
            if not message.bot:
                await ui.error("Bot instance not available")
                return

            file = await message.bot.get_file(photo_id)
            if not file or not file.file_path:
                await ui.error("Could not get file info")
                return

            img_bytes_io = await message.bot.download_file(file.file_path)
            if not img_bytes_io:
                await ui.error("Could not download file")
                return

            img_bytes = img_bytes_io.getvalue()
        except Exception as e:
            logger.error(f"Error downloading photo: {e}")
            await ui.error("Error downloading photo")
            return
        ui.stop_spinner()

        # 2. Image OCR
        await ui.update(t("status.recognizing_text", lang=lang) or "Recognizing text...")
        await ui.start_spinner(theme="dots")

        try:
            ocr_result = await async_ocr(img_bytes, req_id=req_id, use_cache=True, timeout=60)
            positions_count = (
                len(ocr_result["positions"])
                if isinstance(ocr_result, dict)
                else len(ocr_result.positions)
            )
        except asyncio.TimeoutError:
            logger.error(f"OCR timeout for request {req_id}")
            await ui.error("Try another photo")
            return
        except Exception as e:
            logger.error(f"OCR error: {e}")
            await ui.error("Error recognizing text")
            return

        ui.stop_spinner()
        await ui.update(
            t("status.text_recognized", {"count": positions_count}, lang=lang)
            or f"Found {positions_count} items"
        )

        # 3. Matching with product database
        await ui.update(t("status.matching_items", lang=lang) or "Matching items...")
        await ui.start_spinner(theme="boxes")

        # Load product database with caching
        try:
            from app import data_loader

            products = cached_load_products("data/base_products.csv", data_loader.load_products)
        except Exception as e:
            logger.error(f"Error loading products: {e}")
            await ui.error("Error loading database")
            return

        try:
            positions = []
            if hasattr(ocr_result, "positions"):
                positions = ocr_result.positions
            elif isinstance(ocr_result, dict) and "positions" in ocr_result:
                positions = ocr_result["positions"]

            if not positions or len(positions) == 0:
                match_results = []
            else:
                match_results = await async_match_positions(positions, products)

        except Exception as e:
            logger.error(f"Matching error: {e}")
            await ui.error("Error matching items")
            return

        # Matching statistics
        ok_count = sum(1 for item in match_results if item.get("status") == "ok")
        unknown_count = sum(1 for item in match_results if item.get("status") == "unknown")
        positions_count = len(positions) if isinstance(positions, list) else len(positions)
        partial_count = positions_count - ok_count - unknown_count

        ui.stop_spinner()
        await ui.update(
            t(
                "status.matching_completed",
                {"ok": ok_count, "unknown": unknown_count, "partial": partial_count},
                lang=lang,
            )
            or f"Found: {ok_count} ✓, {unknown_count} ❌, {partial_count} ⚠️"
        )

        # 4. Saving results and generating report
        user_matches[(user_id, 0)] = {
            "parsed_data": ocr_result,
            "match_results": match_results,
            "photo_id": photo_id,
            "req_id": req_id,
        }

        await state.update_data(invoice=ocr_result, lang=lang)

        try:
            # Generate report with HTML formatting
            report_text, has_errors = build_report(ocr_result, match_results, escape_html=True)
        except Exception as e:
            logger.error(f"Error building report: {e}")
            await ui.error("Error generating report")
            return

        # Generate keyboard
        inline_kb = build_main_kb(
            has_errors=True if unknown_count + partial_count > 0 else False, lang=lang
        )

        ui.stop_spinner()
        await ui.complete(t("status.processing_completed", lang=lang) or "✅ Done!")

        # 5. Sending full report
        try:
            telegram_html_tags = [
                "<b>",
                "<i>",
                "<u>",
                "<s>",
                "<strike>",
                "<del>",
                "<code>",
                "<pre>",
                "<a",
            ]
            has_valid_html = any(tag in report_text for tag in telegram_html_tags)

            if has_valid_html:
                result = await message.answer(
                    report_text, reply_markup=inline_kb, parse_mode="HTML"
                )
            else:
                result = await message.answer(report_text, reply_markup=inline_kb)

            new_key = (user_id, result.message_id)
            user_matches[new_key] = user_matches.pop((user_id, 0))
            await state.update_data(invoice_msg_id=result.message_id)

        except Exception as msg_err:
            logger.error(f"Error sending HTML report: {msg_err}")
            try:
                clean_report = clean_html(report_text)

                if len(clean_report) > 4000:
                    part1 = clean_report[:4000]
                    part2 = clean_report[4000:]

                    await message.answer(part1)
                    result = await message.answer(part2, reply_markup=inline_kb)
                else:
                    result = await message.answer(clean_report, reply_markup=inline_kb)

                new_key = (user_id, result.message_id)
                if (user_id, 0) in user_matches:
                    user_matches[new_key] = user_matches.pop((user_id, 0))
                await state.update_data(invoice_msg_id=result.message_id)
            except Exception as e:
                logger.error(f"Error sending plain report: {e}")
                await message.answer("Error sending report")

        # Set editing state
        current_state = await state.get_state()
        if current_state != "EditFree:awaiting_input":
            await state.set_state(NotaStates.editing)

    except Exception as e:
        logger.error(f"Unexpected error in photo handler: {e}")
        await message.answer("Error processing photo")
    finally:
        # Remove photo processing flag
        await set_processing_photo(user_id, False)
        await state.update_data(processing_photo=False)
