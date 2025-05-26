"""
Enhanced version of photo_handler using IncrementalUI.

This module provides an asynchronous photo handler for recognizing
and analyzing invoices with progressive UI updates.
"""

import asyncio
import logging
import uuid

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app import data_loader, matcher, ocr
from app.formatters.report import build_report

# Import NotaStates from states module
from app.fsm.states import NotaStates
from app.i18n import t
from app.keyboards import build_main_kb
from app.utils.incremental_ui import IncrementalUI
from app.utils.md import clean_html

logger = logging.getLogger(__name__)

# Создаем роутер для регистрации обработчика
router = Router()


# Основной обработчик фотографий с отладочной информацией
@router.message(F.photo)
async def photo_handler_incremental(message: Message, state: FSMContext):
    """Обработчик фотографий с подробным логированием для предотвращения зависаний"""

    # Уникальный ID запроса для трассировки в логах
    req_id = uuid.uuid4().hex[:8]
    logger.info(f"[{req_id}] Получена фотография от пользователя {message.from_user.id}")

    # Убедимся, что у сообщения есть фотографии
    if not message.photo or len(message.photo) == 0:
        logger.warning(f"[{req_id}] Сообщение не содержит фотографий")
        await message.answer("Error: photo not found. Please try sending again.")
        return

    # Берем фото с наивысшим качеством (последнее в массиве)
    photo_id = message.photo[-1].file_id
    logger.debug(f"[{req_id}] ID фотографии: {photo_id}")
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
    try:
        data = await state.get_data()
        lang = data.get("lang", "en")
    except Exception as e:
        logger.error(f"[{req_id}] Ошибка при получении данных состояния: {e}")
        lang = "en"  # Default language

    # Debug data
    user_id = message.from_user.id

    # Всегда сбрасываем флаг обработки при получении нового фото
    # Это устраняет возможность застрять в состоянии processing_photo=True
    await state.update_data(processing_photo=False)

    # Устанавливаем флаг обработки для текущего фото
    await state.update_data(processing_photo=True)

    logger.info(f"[{req_id}] Received new photo from user {user_id}")

    # Initialize IncrementalUI
    ui = IncrementalUI(message.bot, message.chat.id)
    await ui.start(t("status.receiving_image", lang=lang) or "📸 Receiving image...")

    try:
        # Step 1: Download photo
        # Get file information using provided photo_id
        file = await message.bot.get_file(photo_id)

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
        await ui.append(t("status.recognizing_text", lang=lang) or "🔍 Recognizing...")
        await ui.start_spinner()

        # Запускаем OCR асинхронно в отдельном потоке с таймаутом
        try:
            # Явно указываем таймаут в 60 секунд для OCR
            logger.info(f"[{req_id}] Starting OCR processing with timeout 60s")

            # Обновляем UI, чтобы пользователь видел, что обработка идет
            await ui.update("🔍 Распознавание текста (может занять до 60 секунд)...")

            # Используем to_thread для выполнения OCR без блокировки основного потока
            ocr_result = await asyncio.to_thread(ocr.call_openai_ocr, img_bytes, timeout=60)

            logger.info(f"[{req_id}] OCR completed successfully")
        except asyncio.TimeoutError as e:
            logger.error(f"[{req_id}] OCR processing timed out: {e}")
            # В случае таймаута очищаем флаг обработки
            await state.update_data(processing_photo=False)
            # Сообщаем пользователю о таймауте
            await ui.update(
                "⏱️ Время обработки фото превышено. Пожалуйста, попробуйте снова с другим фото."
            )
            # Прекращаем обработку
            return
        except Exception as e:
            logger.error(f"[{req_id}] Error in OCR processing: {e}")
            # В случае ошибки очищаем флаг обработки
            await state.update_data(processing_photo=False)
            # Сообщаем об ошибке
            await ui.update(
                "❌ Error recognizing text. Try another photo or take a clearer picture."
            )
            # Прекращаем обработку
            return

        ui.stop_spinner()
        positions_count = len(ocr_result.positions) if ocr_result.positions else 0
        await ui.update(
            t("status.text_recognized", {"count": positions_count}, lang=lang)
            or f"✅ Text recognized: found {positions_count} items"
        )
        logger.info(f"[{req_id}] OCR completed successfully, found {positions_count} items")

        # Step 3: Match with products
        await ui.append(t("status.matching_items", lang=lang) or "🔄 Matching items...")
        await ui.start_spinner()

        # Load product database with caching
        from app.utils.cached_loader import cached_load_products

        products = cached_load_products("data/base_products.csv", data_loader.load_products)

        # Match positions - тоже запускаем в to_thread для предотвращения блокировки
        try:
            match_results = await asyncio.to_thread(
                matcher.match_positions, ocr_result.positions, products
            )
        except Exception as e:
            logger.error(f"[{req_id}] Error in matching: {e}")
            await ui.update("❌ Error matching products. Please try again.")
            return

        # Calculate matching statistics
        ok_count = sum(1 for item in match_results if item.get("status") == "ok")
        unknown_count = sum(1 for item in match_results if item.get("status") == "unknown")
        partial_count = positions_count - ok_count - unknown_count

        ui.stop_spinner()
        await ui.update(
            t(
                "status.matching_completed",
                {"ok": ok_count, "unknown": unknown_count, "partial": partial_count},
                lang=lang,
            )
            or f"✅ Matching completed: {ok_count} ✓, {unknown_count} ❌, {partial_count} ⚠️"
        )
        logger.info(
            f"[{req_id}] Matching completed: {ok_count} OK, {unknown_count} unknown, {partial_count} partial"
        )

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

        # ИСПРАВЛЕНО: Сохраняем match_results в state для корректной работы редактирования
        await state.update_data(match_results=match_results)

        # New keyboard - only "Edit", "Cancel" and "Confirm" buttons (if no errors)
        inline_kb = build_main_kb(
            has_errors=True if unknown_count + partial_count > 0 else False, lang=lang
        )

        ui.stop_spinner()
        # Complete UI with brief summary
        await ui.complete(
            t("status.processing_completed", lang=lang) or "✅ Photo processing completed!"
        )

        # Send full report as a separate message
        try:
            # Check message for potential HTML problems before sending
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

            # Add helpful instructions for users
            if unknown_count + partial_count > 0:
                instructions = (
                    "\n\n💬 <i>Just type your edits: 'line 3 qty 5' or 'date 2024-12-25'</i>"
                )
            else:
                instructions = "\n\n💬 <i>Ready to confirm! Or edit with: 'line 3 qty 5'</i>"

            final_text = report_text + instructions

            # Try to send with HTML first if we have valid HTML tags
            if has_valid_html:
                result = await message.answer(final_text, reply_markup=inline_kb, parse_mode="HTML")
            else:
                # If no HTML tags, send without parse_mode
                result = await message.answer(final_text, reply_markup=inline_kb)

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
                result = await message.answer(clean_report[:4000], reply_markup=inline_kb)
                new_key = (user_id, result.message_id)
                if (user_id, 0) in user_matches:
                    user_matches[new_key] = user_matches.pop((user_id, 0))
                await state.update_data(invoice_msg_id=result.message_id)
                logger.info(f"[{req_id}] Report sent with fallback formatting")
            except Exception as final_err:
                logger.error(f"[{req_id}] Critical error sending report: {str(final_err)}")
                await message.answer(
                    t("error.report_failed", lang=lang)
                    or "Error generating report. Please try again or contact support."
                )

        # Set state to editing mode
        await state.set_state(NotaStates.editing)

    except Exception as e:
        logger.error(f"[{req_id}] Error processing photo: {str(e)}")
        error_msg = (
            t("error.processing_failed", lang=lang) or "Error processing photo. Please try again."
        )
        # Показываем ошибку через UI
        await ui.error(error_msg)
        await state.set_state(NotaStates.main_menu)
    finally:
        # Clear processing flag
        try:
            await state.update_data(processing_photo=False)
        except Exception as e:
            logger.error(f"Failed to reset processing flag: {e}")

        # Останавливаем спиннер, если он все еще активен
        try:
            ui.stop_spinner()
        except Exception:
            pass
