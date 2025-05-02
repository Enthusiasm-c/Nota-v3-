from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from app import matcher, alias, data_loader, keyboards

router = Router()


from aiogram.types import ForceReply

class EditPosition(StatesGroup):
    waiting_field = State()
    waiting_name = State()
    waiting_qty = State()
    waiting_unit = State()
    waiting_price = State()

# --- EDIT button pressed: show choose-field menu ---
@router.callback_query(F.data.startswith("edit:"))
async def handle_edit(call: CallbackQuery, state: FSMContext):
    idx = int(call.data.split(":")[1])
    await state.update_data(edit_pos=idx, msg_id=call.message.message_id)
    await call.message.edit_reply_markup(reply_markup=keyboards.kb_edit_fields(idx))

# --- Field selection: set FSM and ask for new value ---
@router.callback_query(F.data.startswith("field:"))
async def handle_field_choose(call: CallbackQuery, state: FSMContext):
    _, field, idx = call.data.split(":")
    idx = int(idx)
    await state.update_data(edit_pos=idx, edit_field=field, msg_id=call.message.message_id)
    await state.set_state(getattr(EditPosition, f"waiting_{field}"))
    await call.message.edit_text(f"Send new {field} for line {idx+1}:", reply_markup=ForceReply())

# --- Cancel for row: restore Edit button ---
@router.callback_query(F.data.startswith("cancel:"))
async def handle_cancel(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if call.data == "cancel:all":
        try:
            await call.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await call.message.edit_text("Editing cancelled. All keyboards removed.")
        await state.clear()
        return
    # cancel:<idx>
    idx = int(call.data.split(":")[1])
    await call.message.edit_reply_markup(reply_markup=keyboards.kb_edit(idx))
    await state.clear()

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
    invoice = data.get("invoice")
    idx = data.get("edit_pos")
    msg_id = data.get("msg_id")
    if invoice is None or idx is None or msg_id is None:
        await message.answer("Session expired. Please resend the invoice.")
        await state.clear()
        return
    value = message.text.strip()
    # Validation
    if field == "qty":
        try:
            value = float(value)
        except Exception:
            await message.answer("Enter a valid number for qty.", reply_markup=ForceReply())
            return
    elif field == "price":
        try:
            value = float(value)
        except Exception:
            await message.answer("Enter a valid number for price.", reply_markup=ForceReply())
            return
    invoice["positions"][idx][field] = value
    # Match
    products = data_loader.load_products()
    match = matcher.match_positions([invoice["positions"][idx]], products, return_suggestions=True)[0]
    invoice["positions"][idx]["status"] = match["status"]
    # Redraw
    from aiogram.utils.markdown import escape_md
    from aiogram.types import InlineKeyboardMarkup
    report = keyboards.build_invoice_report(invoice["positions"]) if hasattr(keyboards, "build_invoice_report") else ""
    if match["status"] == "ok":
        # Remove keyboard if ok
        await message.bot.edit_message_text(f"Updated!\n{report}", message.chat.id, msg_id)
        await message.bot.edit_message_reply_markup(message.chat.id, msg_id, reply_markup=None)
        await state.clear()
    else:
        await message.bot.edit_message_text(f"Updated!\n{report}", message.chat.id, msg_id)
        await message.bot.edit_message_reply_markup(message.chat.id, msg_id, reply_markup=keyboards.kb_edit_fields(idx))
        await state.update_data(edit_pos=idx)

@router.callback_query(F.data.startswith("suggest:"))
async def handle_suggestion(call: CallbackQuery, state: FSMContext):
    _, pos_idx, product_id = call.data.split(":")
    data = await state.get_data()
    invoice = data.get("invoice")
    suggested_name = data.get("suggested_name")
    pos_idx = int(pos_idx)
    if not invoice or pos_idx is None or not suggested_name:
        await call.answer("Session expired. Please resend the invoice.", show_alert=True)
        return
    # Update position with selected product
    products = data_loader.load_products()
    prod = next((p for p in products if p["id"] == product_id), None)
    if not prod:
        await call.answer("Product not found.", show_alert=True)
        return
    invoice["positions"][pos_idx]["name"] = suggested_name
    invoice["positions"][pos_idx]["status"] = "ok"
    alias.add_alias(suggested_name, product_id)
    await call.message.answer(f"Alias '{suggested_name}' saved for product {prod.get('alias', prod.get('name', ''))}.")
    await call.message.answer(keyboards.build_invoice_report(invoice["positions"]))
    await state.clear()
