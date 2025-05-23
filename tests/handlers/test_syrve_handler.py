import pytest
import os
from unittest.mock import AsyncMock, MagicMock, patch, call
from aiogram.types import CallbackQuery, Message, User, Chat
from aiogram.fsm.context import FSMContext
from datetime import datetime

from app.handlers.syrve_handler import handle_invoice_confirm, prepare_invoice_data, get_syrve_client, router
from app.fsm.states import NotaStates # For state checking
# Assuming OCRResult structure or similar dict for invoice_data
from app.ocr.models import OCRResult 

# Helper to create a mock FSMContext
def get_mock_fsm_context(initial_data=None):
    mock_context = AsyncMock(spec=FSMContext)
    current_data = initial_data if initial_data is not None else {}

    async def get_data():
        return current_data.copy()

    async def update_data(new_data=None, **kwargs): # Allow kwargs for update
        if new_data is None: new_data = {}
        new_data.update(kwargs)
        current_data.update(new_data)
        return current_data.copy()
    
    async def set_state(state_name):
        current_data['_state'] = state_name

    mock_context.get_data = AsyncMock(side_effect=get_data)
    mock_context.update_data = AsyncMock(side_effect=update_data)
    mock_context.set_state = AsyncMock(side_effect=set_state)
    return mock_context

# Helper to create a mock CallbackQuery
def get_mock_callback_query(user_id=123, chat_id=456, message_id=789, bot_mock=None):
    mock_call = AsyncMock(spec=CallbackQuery)
    mock_call.from_user = AsyncMock(spec=User)
    mock_call.from_user.id = user_id
    
    mock_call.message = AsyncMock(spec=Message)
    mock_call.message.chat = AsyncMock(spec=Chat)
    mock_call.message.chat.id = chat_id
    mock_call.message.message_id = message_id
    mock_call.message.answer = AsyncMock(return_value=AsyncMock(spec=Message, message_id=message_id + 1)) # For processing_msg
    mock_call.message.edit_text = AsyncMock() # For updating processing_msg

    mock_call.bot = bot_mock if bot_mock else AsyncMock()
    # Mock optimized_safe_edit if it's directly called on bot
    if hasattr(mock_call.bot, 'send_message'): # for admin error reporting
        mock_call.bot.send_message = AsyncMock()

    mock_call.answer = AsyncMock()
    return mock_call

@pytest.fixture
def mock_invoice_data_from_state():
    # Simulate a basic invoice structure as might be stored in FSM state
    # Based on prepare_invoice_data, it might be an OCRResult object or a dict
    invoice = OCRResult(
        date=datetime(2023, 10, 26),
        supplier="Test Supplier Inc.",
        document_number="INV-123",
        positions=[
            {"name": "Product A", "qty": 2.0, "price": 10.50, "sum": 21.00, "unit": "pcs", "product_id": "pA"},
            {"name": "Product B", "qty": 1.0, "price": 5.00, "sum": 5.00, "unit": "kg", "product_id": "pB_partial_match"}
        ]
    )
    return invoice

@pytest.fixture
def mock_match_results_from_state():
    return [
        {"name": "Product A", "status": "ok", "product_id": "pA_db_id", "matched_name": "Product A DB"},
        {"name": "Product B", "status": "partial", "product_id": "pB_db_id", "matched_name": "Product B DB Partial"}
    ]

@pytest.fixture
def mock_state(mock_invoice_data_from_state, mock_match_results_from_state):
    return get_mock_fsm_context({
        "invoice": mock_invoice_data_from_state,
        "match_results": mock_match_results_from_state,
        "lang": "en"
    })

@pytest.fixture
def mock_syrve_client_instance():
    client = AsyncMock()
    client.auth = AsyncMock(return_value="test_auth_token")
    client.import_invoice = AsyncMock() # Default: successful import
    return client

# --- Tests for handle_invoice_confirm ---
@pytest.mark.asyncio
@patch("app.handlers.syrve_handler.get_syrve_client")
@patch("app.handlers.syrve_handler.learn_from_invoice", return_value=(1, ["Product B -> Product B DB Partial"]))
@patch("app.handlers.syrve_handler.prepare_invoice_data")
@patch("app.handlers.syrve_handler.generate_invoice_xml", AsyncMock(return_value="<xml>Test Invoice</xml>"))
@patch("app.handlers.syrve_handler.settings", MagicMock()) # Mock settings if accessed
@patch("app.handlers.syrve_handler.increment_counter")
@patch("app.handlers.syrve_handler.cache_set")
@patch("app.handlers.syrve_handler.optimized_safe_edit", AsyncMock()) # Mock this utility
@patch("app.handlers.syrve_handler.get_ocr_client", return_value=AsyncMock(spec=['completions'])) # Mock OpenAI client
async def test_handle_invoice_confirm_successful(
    mock_get_ocr_cli, mock_optimized_safe_edit, mock_cache_set, mock_increment_counter,
    mock_prepare_invoice, mock_learn_from_invoice, mock_get_syrve_cli,
    mock_state, mock_syrve_client_instance, mock_invoice_data_from_state, mock_match_results_from_state
):
    mock_get_syrve_cli.return_value = mock_syrve_client_instance
    mock_syrve_client_instance.import_invoice.return_value = {"valid": True, "document_number": "SYRVE-DOC-001"}
    
    prepared_syrve_data = {"invoice_date": "2023-10-26", "items": [{"product_id": "pA_db_id", "quantity": 2.0, "price": 10.50}]}
    mock_prepare_invoice.return_value = prepared_syrve_data
    
    mock_call = get_mock_callback_query()

    await handle_invoice_confirm(mock_call, mock_state)

    mock_call.answer.assert_called_once_with(show_alert=False)
    mock_call.message.answer.assert_called_once_with("Sending to Syrve...") # Check processing message
    
    mock_get_syrve_cli.assert_called_once()
    mock_learn_from_invoice.assert_called_once() # With positions from match_results that are "partial"
    
    # Check that only partial matches are passed to learn_from_invoice
    learn_call_args = mock_learn_from_invoice.call_args[0][0]
    assert len(learn_call_args) == 1 # Only one partial match in fixture
    assert learn_call_args[0]["name"] == "Product B"
    assert learn_call_args[0]["matched_product"]["id"] == "pB_db_id"

    mock_prepare_invoice.assert_called_once_with(mock_invoice_data_from_state, mock_match_results_from_state)
    # generate_invoice_xml is AsyncMocked at module level
    patch.object(globals()['__builtins__'], 'generate_invoice_xml', AsyncMock(return_value="<xml>Test Invoice</xml>"))
    # generate_invoice_xml.assert_called_once_with(prepared_syrve_data, ANY) # ANY for openai_client

    mock_syrve_client_instance.auth.assert_called_once()
    mock_syrve_client_instance.import_invoice.assert_called_once_with("test_auth_token", "<xml>Test Invoice</xml>")

    mock_optimized_safe_edit.assert_called_once()
    assert "✅ Импорт OK · № SYRVE-DOC-001" in mock_optimized_safe_edit.call_args[0][3] # Check success message
    
    mock_increment_counter.assert_called_with("nota_invoices_total", {"status": "ok"})
    mock_cache_set.assert_called_once_with("invoice:SYRVE-DOC-001", json.dumps(prepared_syrve_data), ex=86400)
    
    await mock_state.set_state.called_once_with(NotaStates.main_menu)

@pytest.mark.asyncio
@patch("app.handlers.syrve_handler.get_syrve_client")
async def test_handle_invoice_confirm_no_invoice_in_state(mock_get_syrve_cli, mock_state):
    await mock_state.update_data({"invoice": None}) # Remove invoice
    mock_call = get_mock_callback_query()

    await handle_invoice_confirm(mock_call, mock_state)

    mock_call.message.answer.assert_called_once_with("Invoice not found. Please try again.")
    mock_get_syrve_cli.assert_not_called()


@pytest.mark.asyncio
@patch("app.handlers.syrve_handler.get_syrve_client")
@patch("app.handlers.syrve_handler.prepare_invoice_data", MagicMock(return_value={}))
@patch("app.handlers.syrve_handler.generate_invoice_xml", AsyncMock(side_effect=Exception("XML Gen Error")))
@patch("app.handlers.syrve_handler.increment_counter")
async def test_handle_invoice_confirm_xml_generation_error(
    mock_increment_counter_xml_err, mock_get_syrve_cli_xml_err,
    mock_state, mock_syrve_client_instance
):
    mock_get_syrve_cli_xml_err.return_value = mock_syrve_client_instance
    mock_call = get_mock_callback_query()
    processing_msg_mock = mock_call.message.answer.return_value # The message returned by "Sending to Syrve..."

    await handle_invoice_confirm(mock_call, mock_state)

    processing_msg_mock.edit_text.assert_called_once()
    assert "Ошибка генерации XML: XML Gen Error" in processing_msg_mock.edit_text.call_args[0][0]
    mock_increment_counter_xml_err.assert_called_with("nota_invoices_total", {"status": "failed"})
    mock_syrve_client_instance.auth.assert_not_called() # Should not proceed to auth


@pytest.mark.asyncio
@patch("app.handlers.syrve_handler.get_syrve_client")
@patch("app.handlers.syrve_handler.prepare_invoice_data", MagicMock(return_value={}))
@patch("app.handlers.syrve_handler.generate_invoice_xml", AsyncMock(return_value="<xml></xml>"))
@patch("app.handlers.syrve_handler.increment_counter")
async def test_handle_invoice_confirm_syrve_client_auth_error(
    mock_increment_counter_auth_err, mock_get_syrve_cli_auth_err,
    mock_state, mock_syrve_client_instance
):
    mock_get_syrve_cli_auth_err.return_value = mock_syrve_client_instance
    mock_syrve_client_instance.auth.side_effect = Exception("Syrve Auth Failed")
    mock_call = get_mock_callback_query()
    processing_msg_mock = mock_call.message.answer.return_value

    await handle_invoice_confirm(mock_call, mock_state)

    processing_msg_mock.edit_text.assert_called_once()
    assert "Ошибка отправки в Syrve: Syrve Auth Failed" in processing_msg_mock.edit_text.call_args[0][0]
    mock_increment_counter_auth_err.assert_called_with("nota_invoices_total", {"status": "failed"})
    mock_syrve_client_instance.import_invoice.assert_not_called()


@pytest.mark.asyncio
@patch("app.handlers.syrve_handler.get_syrve_client")
@patch("app.handlers.syrve_handler.prepare_invoice_data", MagicMock(return_value={}))
@patch("app.handlers.syrve_handler.generate_invoice_xml", AsyncMock(return_value="<xml></xml>"))
@patch("app.handlers.syrve_handler.increment_counter")
async def test_handle_invoice_confirm_syrve_import_error_with_admin_alert(
    mock_increment_counter_import_err, mock_get_syrve_cli_import_err,
    mock_state, mock_syrve_client_instance
):
    mock_get_syrve_cli_import_err.return_value = mock_syrve_client_instance
    # Simulate a 500 error from Syrve
    mock_syrve_client_instance.import_invoice.return_value = {
        "valid": False, 
        "errorMessage": "Internal Syrve Error 500", 
        "status": 500,
        "document_number": "ErrorDoc1" # Even with error, a doc number might be present
    }
    
    # Mock os.getenv for ADMIN_CHAT_ID
    with patch.dict(os.environ, {"ADMIN_CHAT_ID": "admin123"}):
        # Mock the bot instance on the callback to check send_message
        mock_bot_instance = AsyncMock()
        mock_bot_instance.send_message = AsyncMock()
        mock_call = get_mock_callback_query(bot_mock=mock_bot_instance)
        processing_msg_mock = mock_call.message.answer.return_value

        await handle_invoice_confirm(mock_call, mock_state)

    processing_msg_mock.edit_text.assert_called_once()
    assert "Internal Syrve Error 500"[:50] in processing_msg_mock.edit_text.call_args[0][0] # Shortened error
    mock_increment_counter_import_err.assert_called_with("nota_invoices_total", {"status": "failed"})
    
    # Check if admin was notified
    mock_bot_instance.send_message.assert_called_once_with(
        "admin123", 
        "⚠️ Syrve error (ID: ErrorDoc1):\nInternal Syrve Error 500"
    )


# --- Tests for prepare_invoice_data ---
def test_prepare_invoice_data_basic_conversion(mock_invoice_data_from_state, mock_match_results_from_state):
    # Mock os.getenv for default IDs
    with patch.dict(os.environ, {
        "SYRVE_CONCEPTION_ID": "env_conception_id",
        "SYRVE_STORE_ID": "env_store_id",
        "SYRVE_DEFAULT_SUPPLIER_ID": "env_supplier_id",
    }):
        result = prepare_invoice_data(mock_invoice_data_from_state, mock_match_results_from_state)

    assert result["invoice_date"] == "2023-10-26"
    assert result["conception_id"] == "env_conception_id"
    assert result["store_id"] == "env_store_id"
    assert result["supplier_id"] == "env_supplier_id" # Default used as invoice.supplier is just a name
    assert result["invoice_number"] == "INV-123"
    
    assert len(result["items"]) == 2
    # First item was 'ok'
    assert result["items"][0]["product_id"] == "pA_db_id"
    assert result["items"][0]["quantity"] == 2.0
    assert result["items"][0]["price"] == 10.50
    # Second item was 'partial'
    assert result["items"][1]["product_id"] == "pB_db_id"
    assert result["items"][1]["quantity"] == 1.0
    assert result["items"][1]["price"] == 5.00

def test_prepare_invoice_data_missing_env_vars_uses_hardcoded_defaults(
    mock_invoice_data_from_state, mock_match_results_from_state, caplog # caplog to check warnings
):
    # Ensure relevant env vars are NOT set to test fallback to hardcoded defaults
    with patch.dict(os.environ, {}, clear=True): # Clear all env vars for this test scope
      with caplog.at_level("INFO"):
        result = prepare_invoice_data(mock_invoice_data_from_state, mock_match_results_from_state)

    assert result["conception_id"] == "bf3c0590-b204-f634-e054-0017f63ab3e6"
    assert result["store_id"] == "1239d270-1bbe-f64f-b7ea-5f00518ef508"
    assert result["supplier_id"] == "61c65f89-d940-4153-8c07-488188e16d50"
    
    assert "Используем значение conception_id по умолчанию" in caplog.text
    assert "Используем значение store_id по умолчанию" in caplog.text
    assert "Используем значение supplier_id по умолчанию" in caplog.text


def test_prepare_invoice_data_no_items_adds_test_item(caplog):
    empty_invoice = OCRResult(date=datetime.now(), positions=[]) # No positions
    empty_matches = []
    with caplog.at_level("WARNING"):
        result = prepare_invoice_data(empty_invoice, empty_matches)
    
    assert len(result["items"]) == 1
    assert result["items"][0]["product_id"] == "61aa6384-2fe2-4d0c-aad8-73c5d5dc79c5" # Test product
    assert "Нет товаров в накладной, добавляем тестовый товар" in caplog.text

def test_prepare_invoice_data_item_without_product_id_is_skipped(mock_invoice_data_from_state):
    # Match result for the first item does not contain 'product_id'
    match_results_missing_pid = [
        {"name": "Product A", "status": "ok", "matched_name": "Product A DB"}, # No product_id
        {"name": "Product B", "status": "ok", "product_id": "pB_valid_id", "matched_name": "Product B DB"}
    ]
    result = prepare_invoice_data(mock_invoice_data_from_state, match_results_missing_pid)
    assert len(result["items"]) == 1 # Only Product B should be included
    assert result["items"][0]["product_id"] == "pB_valid_id"


# --- Tests for get_syrve_client ---
@patch.dict(os.environ, {
    "SYRVE_SERVER_URL": "http://test.syrve.com",
    "SYRVE_LOGIN": "user1",
    "SYRVE_PASS_SHA1": "hash123"
})
@patch("app.handlers.syrve_handler.SyrveClient")
def test_get_syrve_client_with_sha1_pass(MockSyrveClient):
    client_instance = get_syrve_client()
    MockSyrveClient.assert_called_once_with(
        "https://test.syrve.com", # Ensure https is added if http is provided
        "user1", 
        "hash123", 
        is_password_hashed=True
    )
    assert client_instance == MockSyrveClient.return_value

@patch.dict(os.environ, {
    "SYRVE_SERVER_URL": "test.syrve.com", # No protocol
    "SYRVE_LOGIN": "user2",
    "SYRVE_PASSWORD": "rawpassword" 
    # SYRVE_PASS_SHA1 is not set, so raw SYRVE_PASSWORD should be used
})
@patch("app.handlers.syrve_handler.SyrveClient")
def test_get_syrve_client_with_raw_pass_and_no_protocol_in_url(MockSyrveClient):
    get_syrve_client()
    MockSyrveClient.assert_called_once_with(
        "https://test.syrve.com", # https added
        "user2", 
        "rawpassword", 
        is_password_hashed=False
    )

def test_get_syrve_client_missing_url_raises_value_error():
    with patch.dict(os.environ, {}, clear=True): # Ensure URL is not set
        with pytest.raises(ValueError, match="SYRVE_SERVER_URL environment variable is required"):
            get_syrve_client()

def test_get_syrve_client_missing_login_raises_value_error():
    with patch.dict(os.environ, {"SYRVE_SERVER_URL": "url"}, clear=True):
        with pytest.raises(ValueError, match="SYRVE_LOGIN environment variable is required"):
            get_syrve_client()

def test_get_syrve_client_missing_any_password_raises_value_error():
    with patch.dict(os.environ, {"SYRVE_SERVER_URL": "url", "SYRVE_LOGIN": "login"}, clear=True):
        with pytest.raises(ValueError, match="Either SYRVE_PASS_SHA1 or SYRVE_PASSWORD environment variable is required"):
            get_syrve_client()

```
