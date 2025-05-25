import os
from datetime import date, datetime
from unittest.mock import AsyncMock, patch

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Chat, Message, User

from app.handlers.syrve_handler import get_syrve_client, prepare_invoice_data
from app.models import ParsedData, Position


# Helper to create a mock FSMContext
def get_mock_fsm_context(initial_data=None):
    mock_context = AsyncMock(spec=FSMContext)
    current_data = initial_data if initial_data is not None else {}

    async def get_data():
        return current_data.copy()

    async def update_data(new_data=None, **kwargs):
        if new_data is None:
            new_data = {}
        new_data.update(kwargs)
        current_data.update(new_data)
        return current_data.copy()

    async def set_state(state_name):
        current_data["_state"] = state_name

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
    mock_call.message.answer = AsyncMock(
        return_value=AsyncMock(spec=Message, message_id=message_id + 1)
    )
    mock_call.message.edit_text = AsyncMock()

    mock_call.bot = bot_mock if bot_mock else AsyncMock()
    if hasattr(mock_call.bot, "send_message"):
        mock_call.bot.send_message = AsyncMock()

    mock_call.answer = AsyncMock()
    return mock_call


@pytest.fixture
def mock_invoice_data_from_state():
    invoice = ParsedData(
        date=datetime(2023, 10, 26),
        supplier="Test Supplier Inc.",
        positions=[
            Position(name="Product A", qty=2.0, price=10.50, unit="pcs"),
            Position(name="Product B", qty=1.0, price=5.00, unit="kg"),
        ],
    )
    return invoice


@pytest.fixture
def mock_match_results_from_state():
    return [
        {
            "name": "Product A",
            "status": "ok",
            "product_id": "pA_db_id",
            "matched_name": "Product A DB",
        },
        {
            "name": "Product B",
            "status": "partial",
            "product_id": "pB_db_id",
            "matched_name": "Product B DB Partial",
        },
    ]


@pytest.fixture
def mock_state(mock_invoice_data_from_state, mock_match_results_from_state):
    return get_mock_fsm_context(
        {
            "invoice": mock_invoice_data_from_state,
            "match_results": mock_match_results_from_state,
            "lang": "en",
        }
    )


@pytest.fixture
def mock_syrve_client_instance():
    client = AsyncMock()
    client.auth = AsyncMock(return_value="test_auth_token")
    client.import_invoice = AsyncMock()
    return client


# --- Tests for prepare_invoice_data ---
def test_prepare_invoice_data_basic_conversion(
    mock_invoice_data_from_state, mock_match_results_from_state
):
    with patch.dict(
        os.environ,
        {
            "SYRVE_CONCEPTION_ID": "2609b25f-2180-bf98-5c1c-967664eea837",
            "SYRVE_STORE_ID": "1239d270-c24d-430c-b7ea-62d23a34f276",
            "SYRVE_DEFAULT_SUPPLIER_ID": "ec062e5a-b44a-46e5-ba58-d7e05960a184",
        },
    ):
        result = prepare_invoice_data(mock_invoice_data_from_state, mock_match_results_from_state)

    assert result["invoice_date"] == "2023-10-26"
    assert result["conception_id"] == "2609b25f-2180-bf98-5c1c-967664eea837"
    assert result["store_id"] == "1239d270-c24d-430c-b7ea-62d23a34f276"
    assert result["supplier_id"] == "ec062e5a-b44a-46e5-ba58-d7e05960a184"

    assert len(result["items"]) == 2
    assert result["items"][0]["product_id"] == "pA_db_id"
    assert result["items"][0]["quantity"] == 2.0
    assert result["items"][0]["price"] == 10.50
    assert result["items"][1]["product_id"] == "pB_db_id"
    assert result["items"][1]["quantity"] == 1.0
    assert result["items"][1]["price"] == 5.00


def test_prepare_invoice_data_missing_env_vars_raises_error(
    mock_invoice_data_from_state, mock_match_results_from_state
):
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(
            ValueError, match="SYRVE_CONCEPTION_ID environment variable is required"
        ):
            prepare_invoice_data(mock_invoice_data_from_state, mock_match_results_from_state)


def test_prepare_invoice_data_no_items_raises_error():
    empty_invoice = ParsedData(date=date.today(), positions=[])
    empty_matches = []

    with patch.dict(
        os.environ,
        {
            "SYRVE_CONCEPTION_ID": "2609b25f-2180-bf98-5c1c-967664eea837",
            "SYRVE_STORE_ID": "1239d270-c24d-430c-b7ea-62d23a34f276",
            "SYRVE_DEFAULT_SUPPLIER_ID": "ec062e5a-b44a-46e5-ba58-d7e05960a184",
        },
    ):
        with pytest.raises(ValueError, match="Invoice contains no valid items with product IDs"):
            prepare_invoice_data(empty_invoice, empty_matches)


def test_prepare_invoice_data_item_without_product_id_is_skipped(mock_invoice_data_from_state):
    match_results_missing_pid = [
        {"name": "Product A", "status": "ok", "matched_name": "Product A DB"},
        {
            "name": "Product B",
            "status": "ok",
            "product_id": "pB_valid_id",
            "matched_name": "Product B DB",
        },
    ]

    with patch.dict(
        os.environ,
        {
            "SYRVE_CONCEPTION_ID": "2609b25f-2180-bf98-5c1c-967664eea837",
            "SYRVE_STORE_ID": "1239d270-c24d-430c-b7ea-62d23a34f276",
            "SYRVE_DEFAULT_SUPPLIER_ID": "ec062e5a-b44a-46e5-ba58-d7e05960a184",
        },
    ):
        result = prepare_invoice_data(mock_invoice_data_from_state, match_results_missing_pid)

    assert len(result["items"]) == 1
    assert result["items"][0]["product_id"] == "pB_valid_id"


# --- Tests for get_syrve_client ---
@patch.dict(
    os.environ,
    {
        "SYRVE_SERVER_URL": "http://test.syrve.com",
        "SYRVE_LOGIN": "user1",
        "SYRVE_PASS_SHA1": "hash123",
    },
)
@patch("app.handlers.syrve_handler.SyrveClient")
def test_get_syrve_client_with_sha1_pass(MockSyrveClient):
    client_instance = get_syrve_client()
    MockSyrveClient.assert_called_once_with(
        "http://test.syrve.com", "user1", "hash123", is_password_hashed=True
    )
    assert client_instance == MockSyrveClient.return_value


@patch.dict(
    os.environ,
    {"SYRVE_SERVER_URL": "test.syrve.com", "SYRVE_LOGIN": "user2", "SYRVE_PASSWORD": "rawpassword"},
)
@patch("app.handlers.syrve_handler.SyrveClient")
def test_get_syrve_client_with_raw_pass_and_no_protocol_in_url(MockSyrveClient):
    get_syrve_client()
    MockSyrveClient.assert_called_once_with(
        "https://test.syrve.com", "user2", "rawpassword", is_password_hashed=False
    )


def test_get_syrve_client_missing_url_raises_value_error():
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValueError, match="SYRVE_SERVER_URL environment variable is required"):
            get_syrve_client()


def test_get_syrve_client_missing_login_raises_value_error():
    with patch.dict(os.environ, {"SYRVE_SERVER_URL": "url"}, clear=True):
        with pytest.raises(ValueError, match="SYRVE_LOGIN environment variable is required"):
            get_syrve_client()


def test_get_syrve_client_missing_any_password_raises_value_error():
    with patch.dict(os.environ, {"SYRVE_SERVER_URL": "url", "SYRVE_LOGIN": "login"}, clear=True):
        with pytest.raises(
            ValueError,
            match="Either SYRVE_PASS_SHA1 or SYRVE_PASSWORD environment variable is required",
        ):
            get_syrve_client()
