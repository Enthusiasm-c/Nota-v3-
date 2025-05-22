import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram.types import Message, User, PhotoSize, File
from aiogram.fsm.context import FSMContext
from io import BytesIO

from app.handlers.optimized_photo_handler import optimized_photo_handler, router
from app.fsm.states import NotaStates
# Assuming similar OCRResult and MatchResult structures as used in incremental tests
from app.ocr.models import OCRResult 
# from app.matcher.models import MatchResult # Not strictly needed if mocking async_match_positions directly

# Helper to create a mock FSMContext (can be shared or redefined)
def get_mock_fsm_context(initial_data=None):
    mock_context = AsyncMock(spec=FSMContext)
    current_data = initial_data if initial_data is not None else {}

    async def get_data():
        return current_data.copy()

    async def update_data(new_data=None, **kwargs):
        if new_data is None: new_data = {}
        new_data.update(kwargs)
        current_data.update(new_data)
        return current_data.copy()
    
    async def set_state(state_name):
        current_data['_state'] = state_name
    
    async def get_state(): # Added for completeness
        return current_data.get('_state', None)


    mock_context.get_data = AsyncMock(side_effect=get_data)
    mock_context.update_data = AsyncMock(side_effect=update_data)
    mock_context.set_state = AsyncMock(side_effect=set_state)
    mock_context.get_state = AsyncMock(side_effect=get_state) # Mock get_state
    return mock_context

# Helper to create a mock Message with Photo (can be shared or redefined)
def get_mock_photo_message(user_id=123, chat_id=456, photo_file_id="photo_id_opt_123"):
    mock_msg = AsyncMock(spec=Message)
    mock_msg.from_user = AsyncMock(spec=User) # Ensure from_user is not None
    mock_msg.from_user.id = user_id
    mock_msg.chat = MagicMock()
    mock_msg.chat.id = chat_id
    
    mock_photo_size = AsyncMock(spec=PhotoSize)
    mock_photo_size.file_id = photo_file_id
    mock_msg.photo = [mock_photo_size]
    
    mock_msg.bot = AsyncMock()
    mock_msg.bot.get_file = AsyncMock(return_value=AsyncMock(spec=File, file_path="path/to/optimized_file.jpg"))
    mock_msg.bot.download_file = AsyncMock(return_value=BytesIO(b"fakeoptimizedimagebytes"))
    mock_msg.answer = AsyncMock(return_value=AsyncMock(spec=Message, message_id=987))
    
    return mock_msg

@pytest.fixture
def mock_opt_message(): # Renamed to avoid conflict
    return get_mock_photo_message()

@pytest.fixture
def mock_opt_state(): # Renamed
    return get_mock_fsm_context({"lang": "en"})

@pytest.fixture
def mock_opt_ocr_result(): # Renamed
    # OCRResult might be a dict in optimized_photo_handler based on `ocr_result["positions"]`
    return {"positions": [{"name": "Optimized Product 1", "qty": 1, "price": 10.0, "sum": 10.0, "unit": "pcs"}]}


@pytest.fixture
def mock_opt_match_results(): # Renamed
    return [{"name": "Optimized Product 1", "status": "ok", "product_id": "opt_p1"}]


# Patching the decorators and guard functions for optimized_photo_handler
@pytest.mark.asyncio
@patch("app.handlers.optimized_photo_handler.IncrementalUI")
@patch("app.handlers.optimized_photo_handler.async_ocr")
@patch("app.handlers.optimized_photo_handler.cached_load_products")
@patch("app.handlers.optimized_photo_handler.async_match_positions")
@patch("app.handlers.optimized_photo_handler.build_report")
@patch("app.handlers.optimized_photo_handler.build_main_kb")
@patch("app.handlers.optimized_photo_handler.user_matches", {})
@patch("app.handlers.optimized_photo_handler.is_processing_photo", AsyncMock(return_value=False)) # Not processing
@patch("app.handlers.optimized_photo_handler.set_processing_photo", AsyncMock()) # Mock set_processing_photo
@patch("app.handlers.optimized_photo_handler.require_user_free", lambda **params: lambda func: func) # Bypass decorator
@patch("app.handlers.optimized_photo_handler.async_timed", lambda **params: lambda func: func) # Bypass decorator
async def test_optimized_photo_handler_successful_flow(
    mock_build_main_kb_opt, mock_build_report_opt, mock_async_match_positions, 
    mock_cached_load_products_opt, mock_async_ocr, MockIncrementalUI_opt,
    mock_opt_message, mock_opt_state, mock_opt_ocr_result, mock_opt_match_results,
    mock_set_processing_photo_func, mock_is_processing_photo_func # Injected patched mocks
):
    # Setup mocks for UI and dependencies
    mock_ui_instance = MockIncrementalUI_opt.return_value
    mock_ui_instance.start, mock_ui_instance.start_spinner, mock_ui_instance.stop_spinner = AsyncMock(), AsyncMock(), AsyncMock()
    mock_ui_instance.update, mock_ui_instance.append, mock_ui_instance.complete, mock_ui_instance.error = AsyncMock(), AsyncMock(), AsyncMock(), AsyncMock()

    mock_async_ocr.return_value = mock_opt_ocr_result
    mock_cached_load_products_opt.return_value = [{"id": "opt_p1", "name": "Optimized Product DB"}]
    mock_async_match_positions.return_value = mock_opt_match_results
    mock_build_report_opt.return_value = ("<p>Optimized HTML Report</p>", False)
    mock_build_main_kb_opt.return_value = MagicMock()

    # Call the handler
    await optimized_photo_handler(mock_opt_message, mock_opt_state)

    # Assertions for processing guard
    mock_is_processing_photo_func.assert_called_once_with(mock_opt_message.from_user.id)
    mock_set_processing_photo_func.assert_any_call(mock_opt_message.from_user.id, True) # Initial set
    
    # Assertions for UI interactions (similar to incremental, adjust text if different)
    mock_ui_instance.start.assert_called_once_with("Processing...") # Default text if t() fails or specific key
    
    # Assertions for core logic
    mock_async_ocr.assert_called_once() # Check args if necessary, e.g., req_id
    mock_async_match_positions.assert_called_once_with(
        mock_opt_ocr_result["positions"], mock_cached_load_products_opt.return_value
    )
    mock_build_report_opt.assert_called_once_with(mock_opt_ocr_result, mock_opt_match_results, escape_html=True)

    # Assertions for state updates
    final_state_data = await mock_opt_state.get_data()
    assert final_state_data["invoice"] == mock_opt_ocr_result
    assert final_state_data["invoice_msg_id"] == 987
    assert final_state_data["processing_photo"] is False # Should be reset by finally block

    await mock_opt_state.set_state.called_once_with(NotaStates.editing)
    mock_opt_message.answer.assert_called_once_with(
        "<p>Optimized HTML Report</p>", reply_markup=mock_build_main_kb_opt.return_value, parse_mode="HTML"
    )
    mock_set_processing_photo_func.assert_any_call(mock_opt_message.from_user.id, False) # Reset in finally

@pytest.mark.asyncio
@patch("app.handlers.optimized_photo_handler.is_processing_photo", AsyncMock(return_value=True))
@patch("app.handlers.optimized_photo_handler.set_processing_photo", AsyncMock())
@patch("app.handlers.optimized_photo_handler.require_user_free", lambda **params: lambda func: func)
@patch("app.handlers.optimized_photo_handler.async_timed", lambda **params: lambda func: func)
async def test_optimized_photo_handler_already_processing(
    mock_set_processing_photo_func_already, mock_is_processing_photo_func_already, # Renamed to avoid fixture conflict
    mock_opt_message, mock_opt_state
):
    await optimized_photo_handler(mock_opt_message, mock_opt_state)
    
    mock_is_processing_photo_func_already.assert_called_once_with(mock_opt_message.from_user.id)
    mock_opt_message.answer.assert_called_once_with("Processing previous photo")
    # Ensure set_processing_photo(True) was NOT called again if already processing.
    # The current structure calls set_processing_photo(True) right after the check.
    # This test verifies the initial check prevents further execution.
    # If the intent is to not even call set_processing_photo(True) if already processing,
    # the guard `is_processing_photo` should prevent that.
    # Let's assume the current code structure: check, then set.
    # So, set_processing_photo(True) would still be called before the return.
    # The important part is that it returns early.
    mock_set_processing_photo_func_already.assert_not_called() # Because the handler should return early
                                                           # However, the `set_processing_photo(True)` is outside the `if`
                                                           # This means it will be called.
                                                           # If the `require_user_free` decorator was active and worked,
                                                           # the whole handler might not even be entered.
                                                           # Given bypassed decorators, this tests the internal `is_processing_photo`

@pytest.mark.asyncio
@patch("app.handlers.optimized_photo_handler.IncrementalUI")
@patch("app.handlers.optimized_photo_handler.async_ocr", side_effect=asyncio.TimeoutError)
@patch("app.handlers.optimized_photo_handler.is_processing_photo", AsyncMock(return_value=False))
@patch("app.handlers.optimized_photo_handler.set_processing_photo", AsyncMock())
@patch("app.handlers.optimized_photo_handler.require_user_free", lambda **params: lambda func: func)
@patch("app.handlers.optimized_photo_handler.async_timed", lambda **params: lambda func: func)
async def test_optimized_photo_handler_ocr_timeout(
    mock_async_ocr_timeout, MockIncrementalUI_opt_timeout,
    mock_opt_message, mock_opt_state, mock_set_processing_photo_func_ocr_timeout
):
    mock_ui_instance = MockIncrementalUI_opt_timeout.return_value
    mock_ui_instance.start, mock_ui_instance.start_spinner, mock_ui_instance.stop_spinner = AsyncMock(), AsyncMock(), AsyncMock()
    mock_ui_instance.update, mock_ui_instance.append, mock_ui_instance.error = AsyncMock(), AsyncMock(), AsyncMock()

    await optimized_photo_handler(mock_opt_message, mock_opt_state)

    mock_ui_instance.error.assert_called_once_with("Try another photo")
    final_state_data = await mock_opt_state.get_data()
    assert final_state_data["processing_photo"] is False
    mock_set_processing_photo_func_ocr_timeout.assert_any_call(mock_opt_message.from_user.id, True)
    mock_set_processing_photo_func_ocr_timeout.assert_any_call(mock_opt_message.from_user.id, False)


@pytest.mark.asyncio
@patch("app.handlers.optimized_photo_handler.IncrementalUI")
@patch("app.handlers.optimized_photo_handler.build_report")
@patch("app.handlers.optimized_photo_handler.async_ocr")
@patch("app.handlers.optimized_photo_handler.cached_load_products")
@patch("app.handlers.optimized_photo_handler.async_match_positions")
@patch("app.handlers.optimized_photo_handler.user_matches", {})
@patch("app.handlers.optimized_photo_handler.is_processing_photo", AsyncMock(return_value=False))
@patch("app.handlers.optimized_photo_handler.set_processing_photo", AsyncMock())
@patch("app.handlers.optimized_photo_handler.require_user_free", lambda **params: lambda func: func)
@patch("app.handlers.optimized_photo_handler.async_timed", lambda **params: lambda func: func)
async def test_optimized_photo_handler_long_report_split(
    mock_async_match_pos_split, mock_cached_load_split, mock_async_ocr_split,
    mock_build_report_split, MockIncrementalUI_split,
    mock_opt_message, mock_opt_state, mock_opt_ocr_result, mock_opt_match_results,
    mock_set_processing_photo_func_split
):
    mock_ui_instance = MockIncrementalUI_split.return_value
    # ... (setup all UI mocks)
    mock_ui_instance.start, mock_ui_instance.start_spinner, mock_ui_instance.stop_spinner = AsyncMock(), AsyncMock(), AsyncMock()
    mock_ui_instance.update, mock_ui_instance.append, mock_ui_instance.complete, mock_ui_instance.error = AsyncMock(), AsyncMock(), AsyncMock(), AsyncMock()


    mock_async_ocr_split.return_value = mock_opt_ocr_result
    mock_cached_load_split.return_value = []
    mock_async_match_pos_split.return_value = mock_opt_match_results
    
    long_report_text = "a" * 4001 # Longer than 4000
    # Simulate HTML send failing, then plain text split
    mock_build_report_split.return_value = (f"<b>{long_report_text}</b>", False) # HTML report

    # First answer fails (HTML), subsequent answers for split plain text succeed
    mock_opt_message.answer.side_effect = [
        Exception("HTML send failed"), # HTML attempt
        AsyncMock(spec=Message, message_id=1001), # Part 1 of plain
        AsyncMock(spec=Message, message_id=1002)  # Part 2 of plain with keyboard
    ]

    with patch("app.handlers.optimized_photo_handler.clean_html", return_value=long_report_text) as mock_clean_html:
        await optimized_photo_handler(mock_opt_message, mock_opt_state)

    assert mock_opt_message.answer.call_count == 3
    mock_clean_html.assert_called_once_with(f"<b>{long_report_text}</b>")
    
    # Check first part of split
    assert mock_opt_message.answer.call_args_list[1][0][0] == "a" * 4000 
    # Check second part of split
    assert mock_opt_message.answer.call_args_list[2][0][0] == "a" 
    assert mock_opt_message.answer.call_args_list[2][1]['reply_markup'] is not None # Keyboard on last part

    final_state_data = await mock_opt_state.get_data()
    assert final_state_data["invoice_msg_id"] == 1002 # Message ID from the last part

# Test for from_user being None (should be caught early)
@pytest.mark.asyncio
@patch("app.handlers.optimized_photo_handler.require_user_free", lambda **params: lambda func: func)
@patch("app.handlers.optimized_photo_handler.async_timed", lambda **params: lambda func: func)
async def test_optimized_photo_handler_no_from_user(mock_opt_state):
    mock_msg_no_user = get_mock_photo_message()
    mock_msg_no_user.from_user = None # Simulate no user
    
    await optimized_photo_handler(mock_msg_no_user, mock_opt_state)
    mock_msg_no_user.answer.assert_called_once_with("Error: Could not identify user")

```
