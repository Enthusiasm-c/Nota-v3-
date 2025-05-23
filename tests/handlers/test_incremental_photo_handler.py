import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram.types import Message, User, PhotoSize, File
from aiogram.fsm.context import FSMContext
from io import BytesIO

from app.handlers.incremental_photo_handler import photo_handler_incremental, router
from app.fsm.states import NotaStates # For state checking
from app.ocr.models import OCRResult # Assuming OCRResult structure
from app.matcher.models import MatchResult # Assuming MatchResult structure

# Helper to create a mock FSMContext
def get_mock_fsm_context(initial_data=None):
    mock_context = AsyncMock(spec=FSMContext)
    current_data = initial_data if initial_data is not None else {}

    async def get_data():
        return current_data.copy()

    async def update_data(new_data=None, **kwargs):
        if new_data is None: new_data = {}
        new_data.update(kwargs) # Allow updating with kwargs
        current_data.update(new_data)
        return current_data.copy()
    
    async def set_state(state_name):
        current_data['_state'] = state_name

    mock_context.get_data = AsyncMock(side_effect=get_data)
    mock_context.update_data = AsyncMock(side_effect=update_data)
    mock_context.set_state = AsyncMock(side_effect=set_state)
    return mock_context

# Helper to create a mock Message with Photo
def get_mock_photo_message(user_id=123, chat_id=456, photo_file_id="photo_id_123"):
    mock_msg = AsyncMock(spec=Message)
    mock_msg.from_user = AsyncMock(spec=User)
    mock_msg.from_user.id = user_id
    mock_msg.chat = MagicMock()
    mock_msg.chat.id = chat_id
    
    mock_photo_size = AsyncMock(spec=PhotoSize)
    mock_photo_size.file_id = photo_file_id
    mock_msg.photo = [mock_photo_size]
    
    mock_msg.bot = AsyncMock() # Mock bot object within message
    mock_msg.bot.get_file = AsyncMock(return_value=AsyncMock(spec=File, file_path="path/to/file.jpg"))
    mock_msg.bot.download_file = AsyncMock(return_value=BytesIO(b"fakedownloadedimagebytes"))
    mock_msg.answer = AsyncMock(return_value=AsyncMock(spec=Message, message_id=789)) # For report sending
    
    return mock_msg

@pytest.fixture
def mock_message_with_photo():
    return get_mock_photo_message()

@pytest.fixture
def mock_state():
    return get_mock_fsm_context({"lang": "en"})


@pytest.fixture
def mock_ocr_result():
    # Define a simple OCRResult structure based on its usage
    res = OCRResult(date=None, supplier=None, total=None, document_number=None, positions=[])
    res.positions = [{"name": "Product 1", "qty": 1, "price": 10.0, "sum": 10.0, "unit": "pcs"}]
    return res

@pytest.fixture
def mock_match_results():
    # Define a simple MatchResult structure
    return [{"name": "Product 1", "status": "ok", "product_id": "p1"}]


@pytest.mark.asyncio
@patch("app.handlers.incremental_photo_handler.IncrementalUI")
@patch("app.handlers.incremental_photo_handler.ocr.call_openai_ocr")
@patch("app.handlers.incremental_photo_handler.cached_load_products")
@patch("app.handlers.incremental_photo_handler.matcher.match_positions")
@patch("app.handlers.incremental_photo_handler.build_report")
@patch("app.handlers.incremental_photo_handler.build_main_kb")
@patch("app.handlers.incremental_photo_handler.user_matches", {}) # Mock the global user_matches
async def test_photo_handler_incremental_successful_flow(
    mock_build_main_kb, mock_build_report, mock_match_positions, 
    mock_cached_load_products, mock_call_openai_ocr, MockIncrementalUI,
    mock_message_with_photo, mock_state, mock_ocr_result, mock_match_results
):
    # Setup mocks
    mock_ui_instance = MockIncrementalUI.return_value
    mock_ui_instance.start = AsyncMock()
    mock_ui_instance.start_spinner = AsyncMock()
    mock_ui_instance.stop_spinner = AsyncMock()
    mock_ui_instance.update = AsyncMock()
    mock_ui_instance.append = AsyncMock()
    mock_ui_instance.complete = AsyncMock()
    mock_ui_instance.error = AsyncMock()

    # Mock return values for dependencies
    mock_call_openai_ocr.return_value = mock_ocr_result
    mock_cached_load_products.return_value = [{"id": "p1", "name": "Product 1 DB"}] # Dummy products
    mock_match_positions.return_value = mock_match_results
    mock_build_report.return_value = ("<p>HTML Report</p>", False) # (report_text, has_errors)
    mock_build_main_kb.return_value = MagicMock() # Dummy keyboard markup

    # Call the handler
    await photo_handler_incremental(mock_message_with_photo, mock_state)

    # Assertions for UI interactions
    mock_ui_instance.start.assert_called_once_with("📸 Receiving image...")
    assert mock_ui_instance.start_spinner.call_count >= 3 # Download, OCR, Match, Report
    assert mock_ui_instance.stop_spinner.call_count >= 3
    mock_ui_instance.update.assert_any_call("✅ Image received")
    mock_ui_instance.update.assert_any_call("✅ Text recognized: found 1 items")
    mock_ui_instance.update.assert_any_call("✅ Matching completed: 1 ✓, 0 ❌, 0 ⚠️")
    mock_ui_instance.complete.assert_called_once_with("✅ Photo processing completed!")

    # Assertions for core logic calls
    mock_message_with_photo.bot.get_file.assert_called_once_with("photo_id_123")
    mock_message_with_photo.bot.download_file.assert_called_once_with("path/to/file.jpg")
    
    # Check that ocr.call_openai_ocr was called via asyncio.to_thread
    # We can't directly assert to_thread, but we check if the underlying function was called.
    # The actual call to mock_call_openai_ocr happens inside the to_thread wrapper.
    # To test this properly, you might need to patch asyncio.to_thread itself
    # or ensure your mock for call_openai_ocr is compatible with how to_thread calls it.
    # For simplicity here, we assume if it's called, to_thread worked.
    assert mock_call_openai_ocr.call_count == 1 
    
    mock_cached_load_products.assert_called_once()
    mock_match_positions.assert_called_once_with(mock_ocr_result.positions, mock_cached_load_products.return_value)
    mock_build_report.assert_called_once_with(mock_ocr_result, mock_match_results, escape_html=True)

    # Assertions for state updates
    final_state_data = await mock_state.get_data()
    assert final_state_data["invoice"] == mock_ocr_result
    assert final_state_data["invoice_msg_id"] == 789 # from mock_message_with_photo.answer
    assert final_state_data["processing_photo"] is False # Should be reset
    
    await mock_state.set_state.called_once_with(NotaStates.editing)

    # Assertion for report sending
    mock_message_with_photo.answer.assert_called_once_with(
        "<p>HTML Report</p>", reply_markup=mock_build_main_kb.return_value, parse_mode="HTML"
    )
    
    # Check user_matches (simplified check for existence of the key)
    user_id = mock_message_with_photo.from_user.id
    message_id = mock_message_with_photo.answer.return_value.message_id
    assert (user_id, message_id) in patch.object(globals()['__builtins__'], 'user_matches', {}) # Access patched global

@pytest.mark.asyncio
@patch("app.handlers.incremental_photo_handler.IncrementalUI")
@patch("app.handlers.incremental_photo_handler.ocr.call_openai_ocr", side_effect=asyncio.TimeoutError)
async def test_photo_handler_ocr_timeout(
    mock_call_openai_ocr, MockIncrementalUI,
    mock_message_with_photo, mock_state
):
    mock_ui_instance = MockIncrementalUI.return_value # Standard mock setup
    # ... (mock other UI methods as in the successful test)
    mock_ui_instance.start = AsyncMock()
    mock_ui_instance.start_spinner = AsyncMock()
    mock_ui_instance.stop_spinner = AsyncMock()
    mock_ui_instance.update = AsyncMock()
    mock_ui_instance.append = AsyncMock()
    mock_ui_instance.error = AsyncMock() # Important for error case

    await photo_handler_incremental(mock_message_with_photo, mock_state)

    mock_ui_instance.update.assert_any_call("⏱️ Время обработки фото превышено. Пожалуйста, попробуйте снова с другим фото.")
    final_state_data = await mock_state.get_data()
    assert final_state_data["processing_photo"] is False
    # Ensure it doesn't proceed to matching, report etc.
    mock_ui_instance.complete.assert_not_called() 
    mock_message_with_photo.answer.assert_not_called() # No report sent


@pytest.mark.asyncio
@patch("app.handlers.incremental_photo_handler.IncrementalUI")
@patch("app.handlers.incremental_photo_handler.ocr.call_openai_ocr", side_effect=Exception("OCR Failed Miserably"))
async def test_photo_handler_ocr_general_error(
    mock_call_openai_ocr, MockIncrementalUI,
    mock_message_with_photo, mock_state
):
    mock_ui_instance = MockIncrementalUI.return_value
    mock_ui_instance.start = AsyncMock()
    mock_ui_instance.start_spinner = AsyncMock()
    mock_ui_instance.stop_spinner = AsyncMock()
    mock_ui_instance.update = AsyncMock()
    mock_ui_instance.append = AsyncMock()
    mock_ui_instance.error = AsyncMock()

    await photo_handler_incremental(mock_message_with_photo, mock_state)
    
    mock_ui_instance.update.assert_any_call("❌ Ошибка при распознавании текста. Попробуйте другое фото или сделайте снимок более четким.")
    final_state_data = await mock_state.get_data()
    assert final_state_data["processing_photo"] is False


@pytest.mark.asyncio
@patch("app.handlers.incremental_photo_handler.IncrementalUI")
# Assume download is fine, OCR is fine, but matching fails
@patch("app.handlers.incremental_photo_handler.ocr.call_openai_ocr") 
@patch("app.handlers.incremental_photo_handler.cached_load_products")
@patch("app.handlers.incremental_photo_handler.matcher.match_positions", side_effect=Exception("Matching Failed"))
async def test_photo_handler_matching_error(
    mock_match_positions, mock_cached_load_products, mock_call_openai_ocr, MockIncrementalUI,
    mock_message_with_photo, mock_state, mock_ocr_result
):
    mock_ui_instance = MockIncrementalUI.return_value
    mock_ui_instance.start, mock_ui_instance.start_spinner, mock_ui_instance.stop_spinner = AsyncMock(), AsyncMock(), AsyncMock()
    mock_ui_instance.update, mock_ui_instance.append, mock_ui_instance.error = AsyncMock(), AsyncMock(), AsyncMock()
    
    mock_call_openai_ocr.return_value = mock_ocr_result
    mock_cached_load_products.return_value = []

    await photo_handler_incremental(mock_message_with_photo, mock_state)

    mock_ui_instance.update.assert_any_call("❌ Error matching products. Please try again.")
    final_state_data = await mock_state.get_data()
    assert final_state_data["processing_photo"] is False


@pytest.mark.asyncio
@patch("app.handlers.incremental_photo_handler.IncrementalUI")
@patch("app.handlers.incremental_photo_handler.ocr.call_openai_ocr")
@patch("app.handlers.incremental_photo_handler.cached_load_products")
@patch("app.handlers.incremental_photo_handler.matcher.match_positions")
@patch("app.handlers.incremental_photo_handler.build_report")
@patch("app.handlers.incremental_photo_handler.user_matches", {})
async def test_photo_handler_report_send_html_error_fallback_to_plain(
    mock_build_report, mock_match_positions, mock_cached_load_products, 
    mock_call_openai_ocr, MockIncrementalUI,
    mock_message_with_photo, mock_state, mock_ocr_result, mock_match_results
):
    mock_ui_instance = MockIncrementalUI.return_value 
    # ... (setup all UI mocks)
    mock_ui_instance.start, mock_ui_instance.start_spinner, mock_ui_instance.stop_spinner = AsyncMock(), AsyncMock(), AsyncMock()
    mock_ui_instance.update, mock_ui_instance.append, mock_ui_instance.complete, mock_ui_instance.error = AsyncMock(), AsyncMock(), AsyncMock(), AsyncMock()

    mock_call_openai_ocr.return_value = mock_ocr_result
    mock_cached_load_products.return_value = []
    mock_match_positions.return_value = mock_match_results
    # Report has HTML tags, but assume sending it with parse_mode="HTML" fails
    html_report_text = "<b>Bold report</b> with <i>italics</i>."
    mock_build_report.return_value = (html_report_text, False)

    # Simulate HTML send failure, then success on fallback
    mock_message_with_photo.answer.side_effect = [
        Exception("Telegram HTML parse error"), # First call (HTML) fails
        AsyncMock(spec=Message, message_id=790) # Second call (plain text) succeeds
    ]
    
    with patch("app.handlers.incremental_photo_handler.clean_html", return_value="Bold report with italics.") as mock_clean_html:
        await photo_handler_incremental(mock_message_with_photo, mock_state)

    assert mock_message_with_photo.answer.call_count == 2
    # First call (HTML)
    assert mock_message_with_photo.answer.call_args_list[0][1]['parse_mode'] == "HTML"
    # Second call (fallback, no parse_mode or default)
    assert 'parse_mode' not in mock_message_with_photo.answer.call_args_list[1][1] 
    
    mock_clean_html.assert_called_once_with(html_report_text)
    
    final_state_data = await mock_state.get_data()
    assert final_state_data["invoice_msg_id"] == 790 # Message ID from fallback send
    assert final_state_data["processing_photo"] is False


@pytest.mark.asyncio
async def test_photo_handler_no_photo_in_message(mock_state):
    mock_msg_no_photo = get_mock_photo_message()
    mock_msg_no_photo.photo = [] # No photo sizes
    
    await photo_handler_incremental(mock_msg_no_photo, mock_state)
    
    mock_msg_no_photo.answer.assert_called_once_with("Ошибка: фотография не найдена. Попробуйте отправить еще раз.")


@pytest.mark.asyncio
@patch("app.handlers.incremental_photo_handler.IncrementalUI")
@patch("app.handlers.incremental_photo_handler.Message.bot", new_callable=AsyncMock) # Mock bot at Message level
async def test_photo_handler_general_exception_in_flow(
    MockBot, MockIncrementalUI,
    mock_state, mock_ocr_result # Use some fixtures to get past initial steps
):
    # Create a message where bot.get_file will raise an unexpected error
    mock_message_problematic = get_mock_photo_message()
    mock_message_problematic.bot.get_file = AsyncMock(side_effect=Exception("Unexpected bot error"))

    mock_ui_instance = MockIncrementalUI.return_value
    mock_ui_instance.start, mock_ui_instance.start_spinner, mock_ui_instance.stop_spinner = AsyncMock(), AsyncMock(), AsyncMock()
    mock_ui_instance.update, mock_ui_instance.append, mock_ui_instance.error = AsyncMock(), AsyncMock(), AsyncMock()

    await photo_handler_incremental(mock_message_problematic, mock_state)

    mock_ui_instance.error.assert_called_once_with("Error processing photo. Please try again.")
    final_state_data = await mock_state.get_data()
    assert final_state_data["processing_photo"] is False
    await mock_state.set_state.called_once_with(NotaStates.main_menu)

```
