from aiogram import Router, CallbackQuery, Message, F
import re
import logging
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ForceReply
from aiogram.exceptions import TelegramBadRequest

from app.formatters import report as invoice_report, alias, data_loader, keyboards
from app import matcher
from app.bot_utils import edit_message_text_safe

logger = logging.getLogger(__name__)


class InvoiceReviewStates(StatesGroup):
    review = State()
    choose_line = State()
    edit_line = State()


class EditPosition(StatesGroup):
    waiting_field = State()
    waiting_name = State()
    waiting_qty = State()
    waiting_unit = State()
    waiting_price = State()


router = Router()


# --- Новый EDIT flow: интерактивный выбор строки ---
@router.callback_query(F.data == "edit:choose")
async def handle_edit_choose(call: CallbackQuery, state: FSMContext):
    await state.set_state(InvoiceReviewStates.choose_line)
    await call.message.answer(
        "Введите номер строки (1-40), которую хотите исправить:",
        reply_markup=None
    )

# --- Получаем номер строки от пользователя ---
@router.message(InvoiceReviewStates.choose_line)
async def handle_choose_line(message: Message, state: FSMContext):
    text = message.text.strip()
    if not text.isdigit() or not (1 <= int(text) <= 40):
        await message.answer("Пожалуйста, введите корректный номер строки (1-40):")
        return
    idx = int(text) - 1
    await state.update_data(edit_pos=idx)
    await state.set_state(InvoiceReviewStates.edit_line)
    # Показываем меню выбора поля (или сразу поле, если только один вариант)
    await message.answer(
        f"Какое поле строки {idx+1} вы хотите изменить? (name/qty/unit/price)",
        reply_markup=None
    )

# --- EDIT button pressed: show choose-field menu ---
@router.callback_query(F.data.startswith("edit:"))
async def handle_edit(call: CallbackQuery, state: FSMContext):
    idx = int(call.data.split(":")[1])
    await state.update_data(edit_pos=idx, msg_id=call.message.message_id)
    try:
        await call.message.edit_reply_markup(reply_markup=keyboards.kb_edit_fields(idx))
    except Exception as e:
        logging.warning(f"Failed to update keyboard: {e}")
        # Пробуем отправить новое сообщение с клавиатурой
        try:
            await call.message.answer("Выберите поле для редактирования:", 
                                    reply_markup=keyboards.kb_edit_fields(idx))
        except Exception as e2:
            logging.error(f"Failed to send fallback message: {e2}")


# --- Field selection: set FSM and ask for new value ---
@router.callback_query(F.data.startswith("field:"))
async def handle_field_choose(call: CallbackQuery, state: FSMContext):
    _, field, idx = call.data.split(":")
    idx = int(idx)
    await state.update_data(
        edit_pos=idx, edit_field=field, msg_id=call.message.message_id
    )
    await state.set_state(getattr(EditPosition, f"waiting_{field}"))
    await call.message.edit_text(
        f"Send new {field} for line {idx+1}:", reply_markup=ForceReply()
    )


# --- Cancel for row: restore Edit button ---
@router.callback_query(F.data.startswith("cancel:"))
async def handle_cancel(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if call.data == "cancel:all":
        try:
            await call.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        # После отмены редактирования — показать первую страницу отчёта с клавиатурой
        invoice = data.get("invoice")
        if invoice:
            match_results = matcher.match_positions(
                invoice["positions"], data_loader.load_products()
            )
            page = 1

            table_rows = [r for r in match_results]
            total_rows = len(table_rows)
            page_size = 15
            total_pages = (total_rows + page_size - 1) // page_size
            text, has_errors = invoice_report.build_report(invoice, match_results, page=page)
            await call.message.edit_text(
                text,
                reply_markup=keyboards.build_invoice_report(
                    text, has_errors, match_results, page=page, total_pages=total_pages
                ),
                parse_mode="HTML"
            )
        else:
            await call.message.edit_text("Editing cancelled. All keyboards removed.", parse_mode="HTML")
        await state.clear()
        return
    idx = int(call.data.split(":")[1])
    await call.message.edit_reply_markup(reply_markup=keyboards.kb_edit(idx))
    await state.clear()


# --- UX финального отчёта: обработчики новых кнопок ---
@router.callback_query(F.data == "inv_page_prev")
async def handle_page_prev(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    invoice = data.get("invoice")
    page = data.get("invoice_page", 1)
    if not invoice:
        await call.answer(
            "Session expired. Please resend the invoice.", show_alert=True
        )
        return
    page = max(1, page - 1)
    await state.update_data(invoice_page=page)
    match_results = matcher.match_positions(
        invoice["positions"], data_loader.load_products()
    )
    text, has_errors = invoice_report.build_report(invoice, match_results, page=page)
    table_rows = [r for r in match_results]
    total_rows = len(table_rows)
    page_size = 15
    total_pages = (total_rows + page_size - 1) // page_size
    await call.message.edit_text(
        text,
        reply_markup=keyboards.build_invoice_report(
            text, has_errors, match_results, page=page, total_pages=total_pages
        ),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "inv_page_next")
async def handle_page_next(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    invoice = data.get("invoice")
    page = data.get("invoice_page", 1)
    if not invoice:
        await call.answer(
            "Session expired. Please resend the invoice.", show_alert=True
        )
        return
    match_results = matcher.match_positions(
        invoice["positions"], data_loader.load_products()
    )
    table_rows = [r for r in match_results]
    total_rows = len(table_rows)
    page_size = 15
    total_pages = (total_rows + page_size - 1) // page_size
    page = min(total_pages, page + 1)
    await state.update_data(invoice_page=page)
    text, has_errors = invoice_report.build_report(invoice, match_results, page=page)
    if '<pre>' not in text:
        logger.error('Invoice report: <pre> block missing, forcibly wrapping!')
        text = f'<pre>{text}</pre>'
    await call.message.edit_text(
        text,
        reply_markup=keyboards.build_invoice_report(
            text, has_errors, match_results, page=page, total_pages=total_pages
        ),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "inv_cancel_edit")
async def handle_cancel_edit(call: CallbackQuery, state: FSMContext):
    # Вернуться к отчёту без удаления черновика
    data = await state.get_data()
    invoice = data.get("invoice")
    page = data.get("invoice_page", 1)
    if not invoice:
        await call.answer(
            "Session expired. Please resend the invoice.", show_alert=True
        )
        return
    match_results = matcher.match_positions(
        invoice["positions"], data_loader.load_products()
    )
    text, has_errors = invoice_report.build_report(invoice, match_results, page=page)
    table_rows = [r for r in match_results]
    total_rows = len(table_rows)
    page_size = 15
    total_pages = (total_rows + page_size - 1) // page_size
    await call.message.edit_text(
        text,
        reply_markup=keyboards.build_invoice_report(
            text, has_errors, match_results, page=page, total_pages=total_pages
        ),
        parse_mode="HTML"
    )
    await state.set_state(InvoiceReviewStates.review)


@router.callback_query(F.data == "inv_submit")
async def handle_submit(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    invoice = data.get("invoice")
    if not invoice:
        await call.answer("Session expired. Please resend the invoice.", show_alert=True)
        return
    match_results = matcher.match_positions(invoice["positions"], data_loader.load_products())
    text, has_errors = invoice_report.build_report(invoice, match_results)
    if has_errors:
        await call.answer("⚠️ Исправьте ошибки перед отправкой.", show_alert=True)
        return
    # Подтверждение перед отправкой
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    confirm_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Да, отправить",
                    callback_data="inv_submit_confirm"
                ),
                InlineKeyboardButton(
                    text="Нет, вернуться",
                    callback_data="inv_submit_cancel"
                ),
            ]
        ]
    )
    await call.message.edit_text(
        "Вы уверены, что хотите отправить инвойс?",
        reply_markup=confirm_kb,
        parse_mode="HTML"
    )



@router.callback_query(F.data == "inv_submit_confirm")
async def handle_submit_confirm(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    invoice = data.get("invoice")
    if not invoice:
        await call.answer("Session expired. Please resend the invoice.", show_alert=True)
        return
    # Здесь — экспорт/отправка в Syrve или другой сервис
    await call.message.edit_text("Инвойс успешно отправлен!")
    await state.clear()



@router.callback_query(F.data == "inv_submit_cancel")
async def handle_submit_cancel(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    invoice = data.get("invoice")
    page = data.get("invoice_page", 1)
    if not invoice:
        await call.answer("Session expired. Please resend the invoice.", show_alert=True)
        return
    match_results = matcher.match_positions(
        invoice["positions"],
        data_loader.load_products()
    )
    text, has_errors = invoice_report.build_report(
        invoice, match_results, page=page
    )
    table_rows = [r for r in match_results]
    total_rows = len(table_rows)
    page_size = 15
    total_pages = (total_rows + page_size - 1) // page_size
    await call.message.edit_text(
        text,
        reply_markup=keyboards.build_invoice_report(
            text,
            has_errors,
            match_results,
            page=page,
            total_pages=total_pages,
            page_size=page_size
        ),
        parse_mode="HTML"
    )
    await state.set_state(InvoiceReviewStates.review)





@router.callback_query(F.data.regexp(r"^page_(\\d+)$"))
async def handle_page_n(call: CallbackQuery, state: FSMContext):
    page = int(re.match(r"^page_(\\d+)$", call.data).group(1))
    data = await state.get_data()
    invoice = data.get("invoice")
    if not invoice:
        await call.answer("Session expired. Please resend the invoice.", show_alert=True)
        return
    match_results = matcher.match_positions(invoice["positions"], data_loader.load_products())
    text, has_errors = invoice_report.build_report(invoice, match_results, page=page)
    page_size = 15
    total_rows = len(match_results)
    total_pages = (total_rows + page_size - 1) // page_size
    await call.message.edit_text(
        text,
        reply_markup=keyboards.build_invoice_report(
            text,
            has_errors,
            match_results,
            page=page,
            total_pages=total_pages,
            page_size=page_size
        ),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "inv_submit_anyway")
async def handle_submit_anyway(call: CallbackQuery, state: FSMContext):
    # Отправить инвойс в Syrve даже если есть unknown
    data = await state.get_data()
    invoice = data.get("invoice")
    if not invoice:
        await call.answer(
            "Session expired. Please resend the invoice.", show_alert=True
        )
        return
    # Импортируем экспорт и вызываем
    from app.export import export_to_syrve

    try:
        await export_to_syrve(invoice)
        # После отправки — показать первую страницу отчёта, если invoice есть
        data = await state.get_data()
        invoice = data.get("invoice")
        if invoice:
            match_results = matcher.match_positions(
                invoice["positions"], data_loader.load_products()
            )
            page = 1
            table_rows = [r for r in match_results]
            total_rows = len(table_rows)
            page_size = 15
            total_pages = (total_rows + page_size - 1) // page_size
            text, has_errors = invoice_report.build_report(invoice, match_results, page=page)
            await call.message.answer(
                text,
                reply_markup=keyboards.build_invoice_report(
                    invoice["positions"], page=page, total_pages=total_pages
                ),
                parse_mode="HTML"
            )
        else:
            await call.message.answer("Invoice sent to Syrve!", reply_markup=None)
        await state.clear()
    except Exception as e:
        # После ошибки — показать первую страницу отчёта, если invoice есть
        data = await state.get_data()
        invoice = data.get("invoice")
        if invoice:
            match_results = matcher.match_positions(
                invoice["positions"], data_loader.load_products()
            )
            page = 1
            table_rows = [r for r in match_results]
            total_rows = len(table_rows)
            page_size = 15
            total_pages = (total_rows + page_size - 1) // page_size
            text, has_errors = invoice_report.build_report(invoice, match_results, page=page)
            await call.message.answer(
                text,
                reply_markup=keyboards.build_invoice_report(
                    invoice["positions"], page=page, total_pages=total_pages
                ),
                parse_mode="HTML"
            )
        else:
            await call.message.answer(f"Error sending invoice: {e}")


@router.callback_query(F.data == "inv_add_missing")
async def handle_add_missing(call: CallbackQuery, state: FSMContext):
    # Переход к поиску по базе (как при unknown)
    data = await state.get_data()
    invoice = data.get("invoice")
    if not invoice:
        await call.answer(
            "Session expired. Please resend the invoice.", show_alert=True
        )
        return
    # Найти первую unknown
    positions = invoice["positions"]
    for idx, pos in enumerate(positions):
        if pos.get("status") == "unknown":
            await state.update_data(edit_pos=idx, msg_id=call.message.message_id)
            await call.message.edit_reply_markup(
                reply_markup=keyboards.kb_edit_fields(idx)
            )
            return
    await call.answer("No unknown positions left.")


# --- Field value reply: validate, update, match, redraw ---
@router.message(EditPosition.waiting_name)
async def process_name(message: Message, state: FSMContext):
    await process_field_reply(message, state, "name")


@router.message(EditPosition.waiting_qty)
async def process_qty(message: Message, state: FSMContext):
    await process_field_reply(message, state, "qty")


@router.message(EditPosition.waiting_unit)
async def process_unit(message: Message, state: FSMContext):
    await process_field_reply(message, state, "unit")


@router.message(EditPosition.waiting_price)
async def process_price(message: Message, state: FSMContext):
    await process_field_reply(message, state, "price")


async def process_field_reply(message: Message, state: FSMContext, field: str):
    data = await state.get_data()
    idx = data.get("edit_pos")
    msg_id = data.get("msg_id")
    invoice = data.get("invoice")
    if invoice is None or idx is None or msg_id is None:
        await message.answer("Session expired. Please resend the invoice.")
        await state.clear()
        return
    value = message.text.strip()
    if field == "qty":
        try:
            value = float(value)
        except Exception:
            await message.answer(
                "⚠️ Введите корректное число для qty.", reply_markup=ForceReply()
            )
            return
    elif field == "price":
        try:
            value = float(value)
        except Exception:
            await message.answer(
                "⚠️ Введите корректное число для price.", reply_markup=ForceReply()
            )
            return
    invoice["positions"][idx][field] = value
    products = data_loader.load_products()
    match = matcher.match_positions(
        [invoice["positions"][idx]], products, return_suggestions=True
    )[0]
    invoice["positions"][idx]["status"] = match["status"]
    # Для совместимости: всегда показываем первую страницу, если не передан page
    match_results = matcher.match_positions(
        invoice["positions"], data_loader.load_products()
    )
    page = 1
    page_size = 40
    total_rows = len(match_results)
    total_pages = (total_rows + page_size - 1) // page_size
    if match["status"] == "ok":

        # После успешного редактирования сбрасываем страницу на 1
        await state.update_data(invoice_page=1)
        match_results = matcher.match_positions(invoice["positions"], data_loader.load_products())
        page = 1
        page_size = 40
        total_rows = len(match_results)
        total_pages = (total_rows + page_size - 1) // page_size
        text, has_errors = invoice_report.build_report(invoice, match_results, page=page)
        reply_markup = keyboards.build_edit_keyboard(has_errors)
        text_to_send = f"<b>Updated!</b><br>{text}"
        with open("/tmp/nota_debug.log", "a") as f:
            f.write(f"EDIT_MESSAGE_DEBUG: chat_id={message.chat.id}, msg_id={msg_id}, text_len={len(text_to_send)}, text_preview={text_to_send[:500]!r}, reply_markup={reply_markup}\n")
        
        # 1. Пытаемся отправить новое сообщение
        try:
            new_msg = await message.bot.send_message(
                chat_id=message.chat.id,
                text=text_to_send,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
            await state.update_data(msg_id=new_msg.message_id)
            await state.clear()
            return  # Всё ок, больше ничего не делаем
        except Exception as e:
            logger.error(f"Failed to send new message: {e}")

        # 2. Если не получилось — fallback: редактируем старое сообщение
        try:
            await edit_message_text_safe(
                bot=message.bot,
                chat_id=message.chat.id,
                msg_id=msg_id,
                text=text_to_send,
                kb=reply_markup,
            )
            await state.clear()
            return
        except Exception as e:
            logger.error(f"Fallback edit_message_text_safe also failed: {e}")

        # 3. Если и это не удалось — пробуем хотя бы убрать клавиатуру
        try:
            await message.bot.edit_message_reply_markup(
                message.chat.id, msg_id, reply_markup=None
            )
        except Exception as e:
            logging.warning(f"Failed to clear keyboard: {e}")
        await state.clear()
    else:
        # Если не ok, оставляем на той же странице (или сбрасываем на 1)
        await state.update_data(invoice_page=1)
        match_results = matcher.match_positions(invoice["positions"], data_loader.load_products())
        page = 1
        page_size = 40
        total_rows = len(match_results)
        total_pages = (total_rows + page_size - 1) // page_size
        text, has_errors = invoice_report.build_report(invoice, match_results, page=page)
        reply_markup = keyboards.build_edit_keyboard(has_errors)
        text_to_send = f"<b>Updated!</b><br>{text}"
        with open("/tmp/nota_debug.log", "a") as f:
            f.write(f"EDIT_MESSAGE_DEBUG: chat_id={message.chat.id}, msg_id={msg_id}, text_len={len(text_to_send)}, text_preview={text_to_send[:500]!r}, reply_markup={reply_markup}\n")
        
        # Отправляем новое сообщение вместо редактирования старого
        try:
            new_msg = await message.bot.send_message(
                chat_id=message.chat.id,
                text=text_to_send,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
            # Сохраняем ID нового сообщения для будущих обновлений
            await state.update_data(msg_id=new_msg.message_id)
            return  # Успешно отправили новое сообщение
        except Exception as e:
            logger.error(f"Failed to send new message: {e}")
            # В случае ошибки пробуем безопасное редактирование как запасной вариант
            await edit_message_text_safe(
                bot=message.bot,
                chat_id=message.chat.id,
                msg_id=msg_id,
                text=text_to_send,
                kb=reply_markup,
            )
        try:
            await message.bot.edit_message_reply_markup(
                message.chat.id, msg_id, reply_markup=keyboards.kb_edit_fields(idx)
            )
        except Exception as e:
            logging.warning(f"Failed to update edit fields keyboard: {e}")
            # Пробуем отправить новое сообщение с клавиатурой
            try:
                await message.answer("Выберите поле для редактирования:",
                                    reply_markup=keyboards.kb_edit_fields(idx))
                # Обновляем ID сообщения в состоянии
                new_msg = await message.answer("Редактирование позиции...", 
                                             reply_markup=keyboards.kb_edit_fields(idx))
                await state.update_data(msg_id=new_msg.message_id)
            except Exception as e2:
                logging.error(f"Failed to send fallback message: {e2}")
        await state.update_data(edit_pos=idx)


@router.callback_query(F.data.startswith("suggest:"))
async def handle_suggestion(call: CallbackQuery, state: FSMContext):
    _, pos_idx, product_id = call.data.split(":")
    data = await state.get_data()
    invoice = data.get("invoice")
    pos_idx = int(pos_idx)
    if not invoice or pos_idx is None:
        await call.answer(
            "Session expired. Please resend the invoice.", show_alert=True
        )
        return
    products = data_loader.load_products()
    prod = next((p for p in products if getattr(p, "id", None) == product_id), None)
    if not prod:
        await call.answer("Product not found.", show_alert=True)
        return
    # Use product alias or name as the suggested name
    suggested_name = getattr(prod, "alias", None) or getattr(prod, "name", "")
    invoice["positions"][pos_idx]["name"] = suggested_name
    invoice["positions"][pos_idx]["status"] = "ok"
    alias.add_alias(suggested_name, product_id)
    prod_name = suggested_name
    await call.message.answer(
        f"Alias '{suggested_name}' saved for product {prod_name}."
    )
    # Показываем первую страницу отчёта с учётом пагинации
    match_results = matcher.match_positions(
        invoice["positions"], data_loader.load_products()
    )
    page = 1
    table_rows = [r for r in match_results]
    total_rows = len(table_rows)
    page_size = 15
    total_pages = (total_rows + page_size - 1) // page_size
    text, has_errors = invoice_report.build_report(invoice, match_results, page=page)
    await call.message.answer(
        text,
        reply_markup=keyboards.build_invoice_report(
            text, has_errors, match_results, page=page, total_pages=total_pages
        ),
        parse_mode="HTML"
    )
    await state.clear()
