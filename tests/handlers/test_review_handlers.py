import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram.types import CallbackQuery, Message, User, Chat, ForceReply
from aiogram.fsm.context import FSMContext

from app.handlers.review_handlers import (
    handle_edit_choose, handle_choose_line, handle_field_choose,
    handle_cancel_row, handle_page_prev, handle_page_next, handle_cancel_edit,
    handle_submit, handle_submit_confirm, handle_submit_cancel, handle_page_n,
    handle_submit_anyway, handle_add_missing,
    process_name, process_qty, process_unit, process_price, # Wrappers for process_field_reply
    process_field_reply, handle_suggestion,
    router # Import router if needed for context, though individual handlers are tested
)
from app.fsm.states import EditFree, InvoiceReviewStates, EditPosition
# Assuming basic invoice structure
from app.ocr.models import OCRResult

# Helper to create a mock FSMContext
def get_mock_fsm_context(initial_data=None):
    mock_context = AsyncMock(spec=FSMContext)
    current_data = initial_data if initial_data is not None else {}
    current_state_val = None

    async def get_data():
        return current_data.copy()

    async def update_data(new_data=None, **kwargs):
        if new_data is None: new_data = {}
        new_data.update(kwargs)
        current_data.update(new_data)
        return current_data.copy()
    
    async def set_state(state_name):
        nonlocal current_state_val
        current_state_val = state_name
        # current_data['_state'] = state_name # Optional: also store in data if app uses it

    async def get_state():
        nonlocal current_state_val
        return current_state_val

    mock_context.get_data = AsyncMock(side_effect=get_data)
    mock_context.update_data = AsyncMock(side_effect=update_data)
    mock_context.set_state = AsyncMock(side_effect=set_state)
    mock_context.get_state = AsyncMock(side_effect=get_state)
    return mock_context

# Helper for CallbackQuery
def get_mock_callback(data_str: str, user_id=123, chat_id=456, message_id=789, bot_mock=None):
    mock_call = AsyncMock(spec=CallbackQuery)
    mock_call.from_user = AsyncMock(spec=User, id=user_id)
    mock_call.message = AsyncMock(spec=Message)
    mock_call.message.chat = AsyncMock(spec=Chat, id=chat_id)
    mock_call.message.message_id = message_id
    mock_call.message.answer = AsyncMock()
    mock_call.message.edit_text = AsyncMock()
    mock_call.message.edit_reply_markup = AsyncMock()
    mock_call.bot = bot_mock if bot_mock else AsyncMock()
    mock_call.data = data_str
    mock_call.answer = AsyncMock()
    return mock_call

# Helper for Message
def get_mock_message(text_str: str, user_id=123, chat_id=456, bot_mock=None):
    mock_msg = AsyncMock(spec=Message)
    mock_msg.from_user = AsyncMock(spec=User, id=user_id)
    mock_msg.chat = AsyncMock(spec=Chat, id=chat_id)
    mock_msg.text = text_str
    mock_msg.answer = AsyncMock()
    mock_msg.bot = bot_mock if bot_mock else AsyncMock()
    return mock_msg

@pytest.fixture
def mock_invoice_fixture():
    # A bit more complex invoice for pagination, etc.
    positions = [{"name": f"Prod {i}", "qty": i, "price": 10*i, "sum": 10*i*i, "status":"ok"} for i in range(1, 20)]
    return OCRResult(date=datetime.now(), supplier="Big Supplier", document_number="DOC001", positions=positions)

@pytest.fixture
def mock_state_with_invoice(mock_invoice_fixture):
    return get_mock_fsm_context({
        "invoice": mock_invoice_fixture, 
        "lang": "en", 
        "invoice_page": 1,
        "msg_id": 1000 # Assume an initial message ID for report
    })

# --- Test handle_edit_choose ---
@pytest.mark.asyncio
async def test_handle_edit_choose(mock_state_with_invoice):
    mock_call = get_mock_callback("edit:choose")
    await handle_edit_choose(mock_call, mock_state_with_invoice)
    
    await mock_state_with_invoice.set_state.called_once_with(EditFree.awaiting_input)
    mock_call.message.answer.assert_called_once_with(
        "Что нужно отредактировать? (пример: 'дата — 26 апреля' или 'строка 2 цена 90000')",
        reply_markup=None
    )

# --- Test handle_choose_line ---
@pytest.mark.asyncio
async def test_handle_choose_line_valid_input(mock_state_with_invoice):
    mock_msg = get_mock_message("3") # User chooses line 3
    await mock_state_with_invoice.set_state(InvoiceReviewStates.choose_line) # Set initial state

    await handle_choose_line(mock_msg, mock_state_with_invoice)

    updated_data = await mock_state_with_invoice.get_data()
    assert updated_data["edit_pos"] == 2 # 0-indexed
    
    # Check that invoice is preserved in state (important!)
    assert updated_data["invoice"] is not None 

    await mock_state_with_invoice.set_state.called_with(EditFree.awaiting_input)
    mock_msg.answer.assert_called_with(
        "Что нужно отредактировать? (пример: 'дата — 26 апреля' или 'строка 2 цена 90000')",
        reply_markup=None
    )

@pytest.mark.asyncio
async def test_handle_choose_line_invalid_input(mock_state_with_invoice):
    mock_msg = get_mock_message("abc") # Invalid input
    await mock_state_with_invoice.set_state(InvoiceReviewStates.choose_line)
    
    await handle_choose_line(mock_msg, mock_state_with_invoice)
    
    mock_msg.answer.assert_called_once_with("Please enter a valid row number (e.g., '1', '2').")
    # Ensure state did not change away from choose_line (or check it wasn't set to EditFree)
    assert await mock_state_with_invoice.get_state() == InvoiceReviewStates.choose_line


# --- Test handle_field_choose ---
@pytest.mark.asyncio
async def test_handle_field_choose(mock_state_with_invoice):
    field, idx = "price", 1
    mock_call = get_mock_callback(f"field:{field}:{idx}")
    
    await handle_field_choose(mock_call, mock_state_with_invoice)

    updated_data = await mock_state_with_invoice.get_data()
    assert updated_data["edit_pos"] == idx
    assert updated_data["edit_field"] == field
    assert updated_data["msg_id"] == mock_call.message.message_id
    assert updated_data["invoice"] is not None # Invoice preserved

    await mock_state_with_invoice.set_state.called_once_with(EditPosition.waiting_price)
    mock_call.message.edit_text.assert_called_once_with(
        f"Send new {field} for line {idx+1}:", reply_markup=ForceReply()
    )

# --- Test handle_cancel_row ---
@pytest.mark.asyncio
@patch("app.handlers.review_handlers.keyboards.build_edit_keyboard") # Mock the keyboard builder
async def test_handle_cancel_row(mock_build_edit_kb, mock_state_with_invoice):
    idx = 0
    mock_call = get_mock_callback(f"cancel:{idx}")
    mock_build_edit_kb.return_value = MagicMock() # Dummy keyboard

    await handle_cancel_row(mock_call, mock_state_with_invoice)

    mock_call.answer.assert_called_once_with("Отмена редактирования строки")
    mock_call.message.edit_reply_markup.assert_called_once_with(reply_markup=mock_build_edit_kb.return_value)
    mock_build_edit_kb.assert_called_once_with(has_errors=True, lang="en")


# --- Test Pagination (Simplified: Prev, Next) ---
@pytest.mark.asyncio
@patch("app.handlers.review_handlers.matcher.match_positions")
@patch("app.handlers.review_handlers.data_loader.load_products")
@patch("app.handlers.review_handlers.invoice_report.build_report")
@patch("app.handlers.review_handlers.keyboards.build_invoice_report")
async def test_handle_page_prev_and_next(
    mock_build_inv_report_kb, mock_build_report_func, mock_load_prods, mock_match_pos,
    mock_state_with_invoice, mock_invoice_fixture
):
    mock_match_pos.return_value = [{"name": f"Prod {i}"} for i in range(1,20)] # Simplified match results
    mock_load_prods.return_value = [] # Dummy products DB
    mock_build_report_func.return_value = ("Report Page Text", False) # (text, has_errors)
    mock_build_inv_report_kb.return_value = MagicMock() # Dummy keyboard

    # Initial page is 1
    # 1. Test Next Page
    mock_call_next = get_mock_callback("inv_page_next")
    await mock_state_with_invoice.update_data(invoice_page=1) # Ensure starting page
    await handle_page_next(mock_call_next, mock_state_with_invoice)
    
    updated_data_next = await mock_state_with_invoice.get_data()
    assert updated_data_next["invoice_page"] == 2 # Page incremented
    mock_build_report_func.assert_called_with(mock_invoice_fixture, mock_match_pos.return_value, page=2)
    mock_call_next.message.edit_text.assert_called_with(
        "Report Page Text", reply_markup=ANY, parse_mode="HTML"
    )

    # 2. Test Prev Page
    mock_call_prev = get_mock_callback("inv_page_prev")
    # current page is 2 from previous step
    await handle_page_prev(mock_call_prev, mock_state_with_invoice)

    updated_data_prev = await mock_state_with_invoice.get_data()
    assert updated_data_prev["invoice_page"] == 1 # Page decremented
    mock_build_report_func.assert_called_with(mock_invoice_fixture, mock_match_pos.return_value, page=1)
    mock_call_prev.message.edit_text.assert_called_with(
        "Report Page Text", reply_markup=ANY, parse_mode="HTML"
    )

# --- Test process_field_reply (core logic for name, qty, price, unit updates) ---
@pytest.mark.asyncio
@patch("app.handlers.review_handlers.data_loader.load_products")
@patch("app.handlers.review_handlers.matcher.match_positions")
@patch("app.handlers.review_handlers.invoice_report.build_report")
@patch("app.handlers.review_handlers.keyboards.build_main_kb")
@patch("app.handlers.review_handlers.edit_message_text_safe", new_callable=AsyncMock) # Mock the safe edit util
async def test_process_field_reply_successful_update(
    mock_edit_safe, mock_build_main_kb, mock_build_report_func, mock_match_pos, mock_load_prods,
    mock_state_with_invoice, mock_invoice_fixture
):
    bot_mock = AsyncMock() # For message.bot.send_message
    mock_msg = get_mock_message("New Product Name", bot_mock=bot_mock)
    field_to_edit, idx_to_edit = "name", 0
    
    await mock_state_with_invoice.update_data(edit_pos=idx_to_edit, edit_field=field_to_edit, msg_id=1000)
    await mock_state_with_invoice.set_state(EditPosition.waiting_name)

    mock_load_prods.return_value = []
    # Simulate match_positions: first for the single item, then for the whole invoice
    single_item_match = [{"name": "New Product Name", "status": "ok"}]
    full_invoice_match = [{"name": "New Product Name", "status": "ok"}] + mock_invoice_fixture.positions[1:]
    mock_match_pos.side_effect = [single_item_match, full_invoice_match, full_invoice_match] # Called multiple times
    
    mock_build_report_func.return_value = ("Updated Report Text", False)
    mock_build_main_kb.return_value = MagicMock() # Dummy keyboard

    await process_field_reply(mock_msg, mock_state_with_invoice, field_to_edit)

    updated_invoice_data = (await mock_state_with_invoice.get_data())["invoice"]
    assert updated_invoice_data.positions[idx_to_edit][field_to_edit] == "New Product Name"
    assert updated_invoice_data.positions[idx_to_edit]["status"] == "ok"

    # Check if send_message was called (primary way to update)
    bot_mock.send_message.assert_called_once()
    args_sent, kwargs_sent = bot_mock.send_message.call_args
    assert "<b>Updated!</b><br>Updated Report Text" in args_sent[0] # Check text
    assert kwargs_sent['chat_id'] == mock_msg.chat.id
    assert kwargs_sent['reply_markup'] == mock_build_main_kb.return_value
    
    # Ensure edit_message_text_safe was NOT called if send_message succeeded
    mock_edit_safe.assert_not_called()

    updated_fsm_data = await mock_state_with_invoice.get_data()
    # msg_id should be updated to the new message's ID
    assert updated_fsm_data['msg_id'] == bot_mock.send_message.return_value.message_id


@pytest.mark.asyncio
async def test_process_field_reply_invalid_number_for_qty(mock_state_with_invoice):
    mock_msg = get_mock_message("not a number")
    await mock_state_with_invoice.update_data(edit_pos=0, edit_field="qty", msg_id=1000)
    await mock_state_with_invoice.set_state(EditPosition.waiting_qty)

    await process_field_reply(mock_msg, mock_state_with_invoice, "qty")
    mock_msg.answer.assert_called_once_with(
        "⚠️ Введите корректное число для qty.", reply_markup=ForceReply()
    )

# --- Test handle_submit (before confirmation) ---
@pytest.mark.asyncio
@patch("app.handlers.review_handlers.matcher.match_positions")
@patch("app.handlers.review_handlers.data_loader.load_products")
@patch("app.handlers.review_handlers.invoice_report.build_report")
async def test_handle_submit_no_errors_shows_confirmation(
    mock_build_report_func, mock_load_prods, mock_match_pos,
    mock_state_with_invoice
):
    mock_call = get_mock_callback("inv_submit")
    mock_match_pos.return_value = [] # Assume no errors means empty or all 'ok'
    mock_load_prods.return_value = []
    mock_build_report_func.return_value = ("Report Text", False) # has_errors = False

    await handle_submit(mock_call, mock_state_with_invoice)

    mock_call.message.edit_text.assert_called_once()
    args, kwargs = mock_call.message.edit_text.call_args
    assert "Вы уверены, что хотите отправить инвойс?" in args[0]
    assert kwargs["reply_markup"] is not None
    assert kwargs["reply_markup"].inline_keyboard[0][0].text == "Да, отправить"
    assert kwargs["reply_markup"].inline_keyboard[0][0].callback_data == "inv_submit_confirm"

@pytest.mark.asyncio
@patch("app.handlers.review_handlers.matcher.match_positions")
@patch("app.handlers.review_handlers.data_loader.load_products")
@patch("app.handlers.review_handlers.invoice_report.build_report")
async def test_handle_submit_with_errors_shows_alert(
    mock_build_report_func, mock_load_prods, mock_match_pos,
    mock_state_with_invoice
):
    mock_call = get_mock_callback("inv_submit")
    mock_match_pos.return_value = [{"status":"unknown"}] 
    mock_load_prods.return_value = []
    mock_build_report_func.return_value = ("Report Text", True) # has_errors = True

    await handle_submit(mock_call, mock_state_with_invoice)

    mock_call.answer.assert_called_once_with("⚠️ Исправьте ошибки перед отправкой.", show_alert=True)
    mock_call.message.edit_text.assert_not_called() # Should not proceed to confirmation

# --- Test handle_submit_confirm ---
@pytest.mark.asyncio
async def test_handle_submit_confirm(mock_state_with_invoice):
    mock_call = get_mock_callback("inv_submit_confirm")
    # Assume invoice is present
    
    await handle_submit_confirm(mock_call, mock_state_with_invoice)

    mock_call.message.edit_text.assert_called_once_with("Инвойс успешно отправлен!")
    # In a real scenario, this would trigger export_to_syrve, which needs mocking if we test that far.
    # The current handler just edits the message.

# --- Test handle_submit_anyway ---
@pytest.mark.asyncio
@patch("app.handlers.review_handlers.export_to_syrve", new_callable=AsyncMock)
@patch("app.handlers.review_handlers.matcher.match_positions")
@patch("app.handlers.review_handlers.data_loader.load_products")
@patch("app.handlers.review_handlers.invoice_report.build_report")
@patch("app.handlers.review_handlers.keyboards.build_invoice_report")
async def test_handle_submit_anyway_success(
    mock_build_inv_report_kb_sa, mock_build_report_func_sa, mock_load_prods_sa, mock_match_pos_sa,
    mock_export_syrve, mock_state_with_invoice, mock_invoice_fixture
):
    mock_call = get_mock_callback("inv_submit_anyway")
    mock_match_pos_sa.return_value = []
    mock_load_prods_sa.return_value = []
    mock_build_report_func_sa.return_value = ("Final Report Text", False)
    mock_build_inv_report_kb_sa.return_value = MagicMock()

    await handle_submit_anyway(mock_call, mock_state_with_invoice)

    mock_export_syrve.assert_called_once_with(mock_invoice_fixture)
    # Check if it tries to display the report after successful export
    mock_call.message.answer.assert_called_once_with(
        "Final Report Text", reply_markup=ANY, parse_mode="HTML"
    )

@pytest.mark.asyncio
@patch("app.handlers.review_handlers.export_to_syrve", new_callable=AsyncMock, side_effect=Exception("Syrve Export Failed"))
@patch("app.handlers.review_handlers.matcher.match_positions")
@patch("app.handlers.review_handlers.data_loader.load_products")
@patch("app.handlers.review_handlers.invoice_report.build_report")
@patch("app.handlers.review_handlers.keyboards.build_invoice_report")
async def test_handle_submit_anyway_export_fails(
    mock_build_inv_report_kb_sa_fail, mock_build_report_func_sa_fail, mock_load_prods_sa_fail, mock_match_pos_sa_fail,
    mock_export_syrve_fail, mock_state_with_invoice
):
    mock_call = get_mock_callback("inv_submit_anyway")
    mock_match_pos_sa_fail.return_value = []
    mock_load_prods_sa_fail.return_value = []
    mock_build_report_func_sa_fail.return_value = ("Error Fallback Report", False) # Report after error
    mock_build_inv_report_kb_sa_fail.return_value = MagicMock()

    await handle_submit_anyway(mock_call, mock_state_with_invoice)
    
    mock_export_syrve_fail.assert_called_once()
    # Check if it tries to display the report even after export error
    mock_call.message.answer.assert_called_once_with(
        "Error Fallback Report", reply_markup=ANY, parse_mode="HTML"
    )
```
