"""
Handlers for invoice editing flow via GPT-3.5-turbo.
"""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.converters import parsed_to_dict
from app.data_loader import load_products
from app.formatters import report
from app.fsm.states import EditFree, NotaStates
from app.i18n import t
from app.keyboards import build_main_kb
from app.matcher import match_positions
from app.parsers.local_parser import parse_command_async
from app.utils.logger_config import get_buffered_logger

logger = get_buffered_logger(__name__)

# Создаем роутер для регистрации обработчиков
router = Router()


@router.message(EditFree.awaiting_input)
@router.message(NotaStates.editing)
async def handle_free_edit_text(message: Message, state: FSMContext):
    """
    Обработчик свободного ввода пользователя для редактирования инвойса через ядро edit_core.
    Оставляет только UI-логику, бизнес-логика вынесена в edit_core.py.
    """
    user_id = getattr(message.from_user, "id", "unknown")
    message_text = getattr(message, "text", None)

    logger.critical(
        f"ОТЛАДКА-ХЕНДЛЕР: handle_free_edit_text вызван для user_id={user_id}, text='{message_text}'"
    )

    current_state = await state.get_state()
    logger.critical(f"ОТЛАДКА-ХЕНДЛЕР: Текущее состояние: {current_state}")

    data = await state.get_data()
    lang = data.get("lang", "en")

    # Проверка наличия инвойса в state
    invoice = data.get("invoice")
    if not invoice:
        logger.critical(f"ОТЛАДКА-ХЕНДЛЕР: Инвойс отсутствует в состоянии для user_id={user_id}")
        await message.answer("Invoice not found for editing. Send an invoice photo or click Edit.")
        return

    # Проверка наличия текста в сообщении
    if not hasattr(message, "text") or message.text is None:
        logger.critical(f"ОТЛАДКА-ХЕНДЛЕР: Сообщение без текста для user_id={user_id}")
        await message.answer(t("edit.enter_text", lang=lang))
        await state.set_state(EditFree.awaiting_input)
        return

    # Проверка на пустую строку
    if not message.text.strip():
        logger.critical(f"ОТЛАДКА-ХЕНДЛЕР: Пустое сообщение для user_id={user_id}")
        return

    user_text = message.text.strip()
    logger.critical(f"ОТЛАДКА-ХЕНДЛЕР: Обрабатываем текст: '{user_text}' для user_id={user_id}")

    # Гарантируем, что мы в режиме редактирования
    if current_state not in [EditFree.awaiting_input, NotaStates.editing]:
        logger.critical(
            f"ОТЛАДКА-ХЕНДЛЕР: Устанавливаем состояние в EditFree.awaiting_input из {current_state}"
        )
        await state.set_state(EditFree.awaiting_input)

    from app.handlers.edit_core import process_user_edit

    processing_msg = None

    async def send_processing(text):
        nonlocal processing_msg
        logger.critical(f"ОТЛАДКА-ХЕНДЛЕР: Отправляем сообщение об обработке: {text}")
        processing_msg = await message.answer(text)

    async def send_result(text):
        logger.critical(
            f"ОТЛАДКА-ХЕНДЛЕР: Отправляем результат (первые 50 символов): {text[:50]}..."
        )
        # Получаем обновленные данные для проверки ошибок
        data = await state.get_data()
        match_results = data.get("match_results", [])
        unknown_count = sum(1 for item in match_results if item.get("status") == "unknown")
        partial_count = sum(1 for item in match_results if item.get("status") == "partial")
        has_errors = unknown_count + partial_count > 0

        # Отправляем сообщение с клавиатурой
        await message.answer(
            text, parse_mode="HTML", reply_markup=build_main_kb(has_errors=has_errors, lang=lang)
        )

    async def send_error(text):
        logger.critical(f"ОТЛАДКА-ХЕНДЛЕР: Отправляем сообщение об ошибке: {text}")
        await message.answer(text)

    async def fuzzy_suggester(message, state, name, idx, lang):
        logger.critical(f"ОТЛАДКА-ХЕНДЛЕР: Вызван fuzzy_suggester для name={name}, idx={idx}")
        from app.handlers.name_picker import show_fuzzy_suggestions

        return await show_fuzzy_suggestions(message, state, name, idx, lang)

    async def edit_state():
        logger.critical("ОТЛАДКА-ХЕНДЛЕР: Устанавливаем состояние в основное меню")
        await state.set_state(NotaStates.main_menu)

    # --- Локальный парсер интента (fallback без OpenAI) ---
    async def local_intent_parser(text: str):
        """Использует полноценный локальный парсер с поддержкой всех команд."""
        logger.critical(f"ОТЛАДКА-ХЕНДЛЕР: Полноценный парсер анализирует текст: '{text}'")

        try:
            # Используем полноценный парсер из app.parsers.local_parser
            result = await parse_command_async(text)

            if result and result.get("action") != "unknown":
                logger.critical(f"ОТЛАДКА-ХЕНДЛЕР: Полноценный парсер распознал команду: {result}")
                return result
            else:
                logger.critical(
                    f"ОТЛАДКА-ХЕНДЛЕР: Полноценный парсер не распознал команду: '{text}'"
                )
                return {
                    "action": "unknown",
                    "user_message": t("error.parse_command", lang=lang),
                    "source": "local_parser",
                }
        except Exception as e:
            logger.critical(f"ОТЛАДКА-ХЕНДЛЕР: Исключение в полноценном парсере: {e}")
            import traceback

            logger.critical(traceback.format_exc())
            return {
                "action": "unknown",
                "user_message": f"An error occurred while processing the command: {e}",
                "source": "local_parser_error",
            }

    logger.critical("ОТЛАДКА-ХЕНДЛЕР: Перед вызовом process_user_edit")
    try:
        result = await process_user_edit(
            message=message,
            state=state,
            user_text=user_text,
            lang=lang,
            send_processing=send_processing,
            send_result=send_result,
            send_error=send_error,
            fuzzy_suggester=fuzzy_suggester,
            edit_state=edit_state,
            run_openai_intent=local_intent_parser,
        )
        logger.critical(
            f"ОТЛАДКА-ХЕНДЛЕР: process_user_edit завершился с результатом: {bool(result)}"
        )
    except Exception as e:
        logger.critical(f"ОТЛАДКА-ХЕНДЛЕР: Ошибка в process_user_edit: {e}", exc_info=True)
        await message.answer("An error occurred while processing the command. Please try again.")

    if processing_msg:
        try:
            logger.critical("ОТЛАДКА-ХЕНДЛЕР: Удаляем сообщение об обработке")
            await processing_msg.delete()
        except Exception as e:
            logger.critical(f"ОТЛАДКА-ХЕНДЛЕР: Ошибка при удалении processing_msg: {e}")

    logger.critical(
        "ОТЛАДКА-ХЕНДЛЕР: Устанавливаем окончательное состояние EditFree.awaiting_input"
    )
    await state.set_state(EditFree.awaiting_input)


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
        try:
            await call.message.edit_reply_markup(reply_markup=None)
        except Exception as e:
            logger.warning(f"Failed to remove suggestion buttons: {e}")

        # Generate keyboard based on errors presence
        keyboard = build_main_kb(has_errors, lang=lang)

        # Send updated report
        await call.message.answer(text, reply_markup=keyboard, parse_mode="HTML")

        # Add message about successful editing
        success_message = f"✅ {t('status.edit_success', {'field': 'name'}, lang=lang)}"
        if not has_errors:
            success_message += f" {t('status.edit_success_confirm', lang=lang)}"

        await call.message.answer(success_message, parse_mode="HTML")
    except Exception as e:
        logger.error("[confirm_fuzzy_name] Error updating name", extra={"data": {"error": str(e)}})

        # Delete processing indicator
        try:
            await processing_msg.delete()
        except Exception:
            pass

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

    # Remove suggestion buttons
    await call.message.edit_reply_markup(reply_markup=None)

    # Send message about manual editing requirement
    await call.message.answer(
        f"You can manually edit the name by sending the command:\n\n"
        f"<i>line {line_idx+1} name [new name]</i>",
        parse_mode="HTML",
    )

    # Answer callback
    await call.answer()

    # Stay in the same state for continued editing
    await state.set_state(EditFree.awaiting_input)
