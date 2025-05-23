from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message, User

from app.fsm.states import EditFree  # For setting state in reject handler
from app.handlers.name_picker import (
    handle_pick_name,
    handle_pick_name_reject,
    show_fuzzy_suggestions,
)


# Helper to create a mock FSMContext (similar to test_edit_core)
def get_mock_fsm_context(initial_data=None):
    mock_context = AsyncMock(spec=FSMContext)
    current_data = initial_data if initial_data is not None else {}

    async def get_data():
        return current_data.copy()

    async def update_data(new_data):
        # Make sure new_data is a dict if it's not None
        if new_data is not None:
            current_data.update(new_data)
        return current_data.copy()

    async def set_state(state_name):
        current_data["_state"] = state_name

    mock_context.get_data = AsyncMock(side_effect=get_data)
    mock_context.update_data = AsyncMock(side_effect=update_data)
    mock_context.set_state = AsyncMock(side_effect=set_state)
    return mock_context


# Helper to create a mock Message
def get_mock_message(user_id=123, text="some text", chat_id=456):
    mock_msg = AsyncMock(spec=Message)
    mock_msg.from_user = AsyncMock(spec=User)
    mock_msg.from_user.id = user_id
    mock_msg.text = text
    mock_msg.chat = MagicMock()
    mock_msg.chat.id = chat_id
    mock_msg.answer = AsyncMock()  # Add answer method
    mock_msg.edit_reply_markup = AsyncMock()  # Add edit_reply_markup method
    return mock_msg


# Helper to create a mock CallbackQuery
def get_mock_callback_query(data="pick_name:0:prod123", message=None, user_id=123):
    mock_call = AsyncMock(spec=CallbackQuery)
    mock_call.data = data
    mock_call.message = message if message else get_mock_message(user_id=user_id)
    mock_call.from_user = AsyncMock(spec=User)
    mock_call.from_user.id = user_id
    mock_call.answer = AsyncMock()
    return mock_call


@pytest.fixture
def mock_state_with_invoice():
    return get_mock_fsm_context(
        {
            "invoice": {
                "positions": [
                    {"name": "Original Product Name", "qty": 1, "price": 100, "id": "item1"},
                    {"name": "Another Product", "qty": 2, "price": 200, "id": "item2"},
                ]
            },
            "lang": "en",
        }
    )


@pytest.fixture
def mock_products_db():
    return [
        {"id": "prod123", "name": "Selected Product DB Name"},
        {"id": "prod456", "name": "Fuzzy Match Product 1"},
        {"id": "prod789", "name": "Fuzzy Match Product 2"},
    ]


@pytest.mark.asyncio
async def test_handle_pick_name_successful(mock_state_with_invoice, mock_products_db):
    row_idx, product_id = 0, "prod123"
    mock_call = get_mock_callback_query(data=f"pick_name:{row_idx}:{product_id}")

    initial_invoice = (await mock_state_with_invoice.get_data())["invoice"]
    original_name_in_invoice = initial_invoice["positions"][row_idx]["name"]

    # Expected name from DB
    expected_db_product_name = next(p["name"] for p in mock_products_db if p["id"] == product_id)

    # Mock external calls
    with patch(
        "app.handlers.name_picker.load_products", MagicMock(return_value=mock_products_db)
    ), patch("app.handlers.name_picker.set_name") as mock_set_name, patch(
        "app.handlers.name_picker.match_positions", MagicMock(return_value=[])
    ) as mock_match_positions, patch(
        "app.handlers.name_picker.report.build_report",
        MagicMock(return_value=("Report text", False)),
    ) as mock_build_report, patch(
        "app.handlers.name_picker.build_main_kb", MagicMock(return_value=None)
    ) as mock_build_kb, patch(
        "app.handlers.name_picker.add_alias", AsyncMock()
    ) as mock_add_alias, patch(
        "app.handlers.name_picker.parsed_to_dict", MagicMock(side_effect=lambda x: x)
    ):  # Bypass Pydantic

        # Simulate set_name updating the invoice
        def set_name_side_effect(invoice_data, r_idx, name_val, manual_edit=False):
            invoice_data["positions"][r_idx]["name"] = name_val
            # also set matched_name as in actual set_name or handle_pick_name
            invoice_data["positions"][r_idx]["matched_name"] = name_val
            return invoice_data

        mock_set_name.side_effect = set_name_side_effect

        await handle_pick_name(mock_call, mock_state_with_invoice)

    mock_call.answer.assert_called()
    mock_call.message.answer.assert_any_call("Applying changes...")  # Check for processing message

    # Check that set_name was called correctly
    mock_set_name.assert_called_once_with(initial_invoice, row_idx, expected_db_product_name)

    # Check that the invoice in state was updated
    updated_data = await mock_state_with_invoice.get_data()
    assert updated_data["invoice"]["positions"][row_idx]["name"] == expected_db_product_name
    assert updated_data["invoice"]["positions"][row_idx]["matched_name"] == expected_db_product_name

    mock_match_positions.assert_called_once()
    mock_build_report.assert_called_once()
    mock_build_kb.assert_called_once()
    mock_call.message.edit_reply_markup.assert_called_once_with(reply_markup=None)

    # Check alias was added if original name different from DB name
    if original_name_in_invoice.lower() != expected_db_product_name.lower():
        mock_add_alias.assert_called_once_with(original_name_in_invoice, product_id)
    else:
        mock_add_alias.assert_not_called()

    # Check the main report message
    args, kwargs = mock_call.message.answer.call_args_list[-2]  # Second to last call is the report
    assert args[0] == "Report text"
    assert kwargs["parse_mode"] == "HTML"


@pytest.mark.asyncio
async def test_handle_pick_name_invalid_callback(mock_state_with_invoice):
    mock_call = get_mock_callback_query(data="pick_name:invalid_data")
    await handle_pick_name(mock_call, mock_state_with_invoice)
    mock_call.answer.assert_called_once_with("Invalid callback data.")


@pytest.mark.asyncio
async def test_handle_pick_name_no_invoice(mock_state_with_invoice):
    await mock_state_with_invoice.update_data({"invoice": None})  # Remove invoice
    mock_call = get_mock_callback_query()
    await handle_pick_name(mock_call, mock_state_with_invoice)
    mock_call.answer.assert_called_once_with("Invoice not found. Please try again.")


@pytest.mark.asyncio
async def test_handle_pick_name_product_not_found_in_db(mock_state_with_invoice, mock_products_db):
    mock_call = get_mock_callback_query(data="pick_name:0:unknown_prod_id")
    with patch("app.handlers.name_picker.load_products", MagicMock(return_value=mock_products_db)):
        await handle_pick_name(mock_call, mock_state_with_invoice)
    mock_call.answer.assert_called_once_with("Product not found in database.")
    # Ensure processing message was deleted
    mock_call.message.answer.assert_any_call("Applying changes...")
    # Assuming the processing message is the one that gets deleted
    processing_msg_mock = mock_call.message.answer.return_value
    processing_msg_mock.delete.assert_called_once()


@pytest.mark.asyncio
@patch("app.handlers.name_picker.load_products")
@patch("app.handlers.name_picker.fuzzy_find")
async def test_show_fuzzy_suggestions_found_and_shown(
    mock_fuzzy_find, mock_load_prod, mock_state_with_invoice
):
    mock_message = get_mock_message()
    unrecognized_name = "Unrec Prod"
    row_idx = 0
    lang = "en"

    mock_load_prod.return_value = mock_products_db()  # Use fixture
    mock_fuzzy_find.return_value = [{"id": "prod456", "name": "Fuzzy Match Product 1"}]

    result = await show_fuzzy_suggestions(
        mock_message, mock_state_with_invoice, unrecognized_name, row_idx, lang
    )

    assert result is True
    mock_fuzzy_find.assert_called_once_with(
        unrecognized_name, mock_load_prod.return_value, threshold=0.75
    )  # Default threshold for longer names
    mock_message.answer.assert_called_once()
    args, kwargs = mock_message.answer.call_args
    assert 'Did you mean "Fuzzy Match Product 1"?' in args[0]
    assert isinstance(kwargs["reply_markup"], InlineKeyboardMarkup)
    assert kwargs["reply_markup"].inline_keyboard[0][0].text == "✓ Yes"
    assert (
        kwargs["reply_markup"].inline_keyboard[0][0].callback_data == f"pick_name:{row_idx}:prod456"
    )

    updated_data = await mock_state_with_invoice.get_data()
    assert updated_data["fuzzy_original_text"] == unrecognized_name


@pytest.mark.asyncio
@patch("app.handlers.name_picker.load_products")
@patch("app.handlers.name_picker.fuzzy_find")
async def test_show_fuzzy_suggestions_not_found(
    mock_fuzzy_find, mock_load_prod, mock_state_with_invoice
):
    mock_message = get_mock_message()
    unrecognized_name = "Very Unique Name"
    row_idx = 0
    lang = "en"

    mock_load_prod.return_value = []
    mock_fuzzy_find.return_value = []  # No matches

    result = await show_fuzzy_suggestions(
        mock_message, mock_state_with_invoice, unrecognized_name, row_idx, lang
    )

    assert result is False
    mock_message.answer.assert_not_called()


@pytest.mark.asyncio
async def test_show_fuzzy_suggestions_reserved_keyword(mock_state_with_invoice):
    mock_message = get_mock_message()
    # Name contains a reserved keyword
    result = await show_fuzzy_suggestions(
        mock_message, mock_state_with_invoice, "product with date", 0, "en"
    )
    assert result is False
    mock_message.answer.assert_not_called()


@pytest.mark.asyncio
async def test_show_fuzzy_suggestions_skip_flag(mock_state_with_invoice):
    mock_message = get_mock_message()
    await mock_state_with_invoice.update_data({"skip_fuzzy_matching": True})
    result = await show_fuzzy_suggestions(
        mock_message, mock_state_with_invoice, "some name", 0, "en"
    )
    assert result is False
    mock_message.answer.assert_not_called()
    # Ensure flag is reset
    updated_data = await mock_state_with_invoice.get_data()
    assert updated_data["skip_fuzzy_matching"] is False


@pytest.mark.asyncio
async def test_handle_pick_name_reject_successful(mock_state_with_invoice):
    row_idx = 0
    original_user_text = "User Typed This Name"
    await mock_state_with_invoice.update_data({"fuzzy_original_text": original_user_text})

    mock_call = get_mock_callback_query(data=f"pick_name_reject:{row_idx}")
    initial_invoice = (await mock_state_with_invoice.get_data())["invoice"]

    with patch("app.handlers.name_picker.load_products", MagicMock(return_value=[])), patch(
        "app.handlers.name_picker.set_name"
    ) as mock_set_name, patch(
        "app.handlers.name_picker.match_positions", MagicMock(return_value=[])
    ) as mock_match_positions, patch(
        "app.handlers.name_picker.report.build_report",
        MagicMock(return_value=("Report after reject", False)),
    ) as mock_build_report, patch(
        "app.handlers.name_picker.build_main_kb", MagicMock(return_value=None)
    ) as mock_build_kb, patch(
        "app.handlers.name_picker.parsed_to_dict", MagicMock(side_effect=lambda x: x)
    ):

        # Simulate set_name updating the invoice
        def set_name_side_effect(invoice_data, r_idx, name_val, manual_edit=False):
            assert manual_edit is True  # Ensure manual_edit flag is passed
            invoice_data["positions"][r_idx]["name"] = name_val
            return invoice_data

        mock_set_name.side_effect = set_name_side_effect

        await handle_pick_name_reject(mock_call, mock_state_with_invoice)

    mock_call.answer.assert_called_once()
    mock_call.message.edit_reply_markup.assert_called_once_with(reply_markup=None)

    mock_set_name.assert_called_once_with(
        initial_invoice, row_idx, original_user_text, manual_edit=True
    )

    updated_data = await mock_state_with_invoice.get_data()
    assert updated_data["invoice"]["positions"][row_idx]["name"] == original_user_text

    # Check for report message and confirmation message
    assert mock_call.message.answer.call_count == 2
    report_call_args, _ = mock_call.message.answer.call_args_list[0]  # First call is the report
    assert report_call_args[0] == "Report after reject"

    confirm_call_args, _ = mock_call.message.answer.call_args_list[1]  # Second call is confirmation
    assert f'Your input "{original_user_text}" has been accepted' in confirm_call_args[0]

    mock_state_with_invoice.set_state.assert_called_once_with(EditFree.awaiting_input)


@pytest.mark.asyncio
async def test_handle_pick_name_reject_no_original_text(mock_state_with_invoice):
    # fuzzy_original_text is not in state
    await mock_state_with_invoice.update_data({"fuzzy_original_text": None})
    mock_call = get_mock_callback_query(data="pick_name_reject:0")

    with patch("app.handlers.name_picker.set_name") as mock_set_name:
        await handle_pick_name_reject(mock_call, mock_state_with_invoice)

    mock_set_name.assert_not_called()  # set_name should not be called
    mock_call.message.answer.assert_called_once_with(
        "Suggestion rejected. You can try a different name.", parse_mode="HTML"
    )
    mock_state_with_invoice.set_state.assert_called_once_with(EditFree.awaiting_input)
