from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from app import matcher, alias, data_loader, keyboards
from app.ocr import ParsedData, Position
import uuid

router = Router()

class EditPosition(StatesGroup):
    waiting_edit = State()

@router.callback_query(F.data.startswith("pos:"))
async def handle_position_action(call: CallbackQuery, state: FSMContext):
    # Parse callback data: pos:<uuid>:<action>
    _, pos_id, action = call.data.split(":")
    # Fetch invoice from state (should be set in photo handler)
    invoice = (await state.get_data()).get("invoice")
    if not invoice:
        await call.answer("Session expired. Please resend the invoice.", show_alert=True)
        return
    positions = invoice["positions"]
    pos_idx = int(pos_id)
    if action == "ok":
        positions[pos_idx]["status"] = "ok"
        await call.message.edit_reply_markup(reply_markup=keyboards.build_invoice_keyboard(positions))
    elif action == "remove":
        positions[pos_idx]["status"] = "removed"
        await call.message.edit_reply_markup(reply_markup=keyboards.build_invoice_keyboard(positions))
    elif action == "edit":
        await state.set_state(EditPosition.waiting_edit)
        await state.update_data(edit_pos=pos_idx)
        await call.message.answer("Send corrected value (e.g. Tuna loin 0.8 kg 75000)")

@router.message(EditPosition.waiting_edit)
async def process_edit(message: Message, state: FSMContext):
    data = await state.get_data()
    invoice = data.get("invoice")
    pos_idx = data.get("edit_pos")
    if not invoice or pos_idx is None:
        await message.answer("Session expired. Please resend the invoice.")
        return
    # Parse user input (very basic)
    parts = message.text.strip().split()
    if len(parts) < 3:
        await message.answer("Please enter: name qty unit [price]")
        return
    name = parts[0]
    qty = float(parts[1])
    unit = parts[2]
    price = float(parts[3]) if len(parts) > 3 else None
    invoice["positions"][pos_idx].update({"name": name, "qty": qty, "unit": unit})
    if price:
        invoice["positions"][pos_idx]["price"] = price
    # Re-run matcher for this row, with suggestions
    products = data_loader.load_products()
    match = matcher.match_positions([invoice["positions"][pos_idx]], products, return_suggestions=True)[0]
    invoice["positions"][pos_idx]["status"] = match["status"]
    if match["status"] == "ok" and name.lower() != products[0]["alias"].lower():
        alias.add_alias(name, match["product_id"])
        await message.answer("Updated! See new report below.")
        await message.answer(keyboards.build_invoice_report(invoice["positions"]))
        await state.clear()
        return
    # If still unknown, offer suggestions
    if match["status"] == "unknown" and match.get("suggestions"):
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=p.get("alias", p.get("name", "")), callback_data=f"suggest:{pos_idx}:{p['id']}")]
                for p in match["suggestions"]
            ]
        )
        await message.answer("Not recognized. Pick the correct product:", reply_markup=kb)
        await state.update_data(suggested_name=name)
        return
    await message.answer("No match found and no suggestions available.")
    await state.clear()

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
