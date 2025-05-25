import os
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.services.syrve_invoice_sender import (
    Invoice,
    InvoiceHTTPError,
    InvoiceItem,
    InvoiceValidationError,
    SyrveClient,
)

# --- Constants for testing ---
VALID_GUID = "12345678-1234-1234-1234-123456789abc"
VALID_GUID_2 = "abcdef01-2345-6789-abcd-ef0123456789"
VALID_GUID_3 = "fedcba98-7654-3210-fedc-ba9876543210"


@pytest.fixture
def minimal_invoice_item():
    return InvoiceItem(
        num=1,
        product_id=VALID_GUID,
        amount=Decimal("10"),
        price=Decimal("1.5"),
        sum=Decimal("15.00"),
    )


@pytest.fixture
def minimal_invoice(minimal_invoice_item):
    return Invoice(
        items=[minimal_invoice_item], supplier_id=VALID_GUID_2, default_store_id=VALID_GUID_3
    )


@pytest.fixture
def syrve_client_base_args():
    return {
        "base_url": "http://test.syrve.api",
        "login": "testlogin",
        "password_sha1": "testpasshash",
    }


@pytest.fixture
def syrve_client(syrve_client_base_args):
    # Mock httpx.Client to prevent actual HTTP calls during most unit tests
    with patch("app.services.syrve_invoice_sender.httpx.Client") as mock_http_client:
        client = SyrveClient(**syrve_client_base_args)
        client.http = mock_http_client.return_value  # Assign the instance of the mock
        yield client


# --- Tests for InvoiceItem and Invoice dataclasses (basic instantiation) ---
def test_invoice_item_creation():
    item = InvoiceItem(
        num=1, product_id="pid", amount=Decimal("1"), price=Decimal("10"), sum=Decimal("10")
    )
    assert item.num == 1
    assert item.product_id == "pid"


def test_invoice_creation(minimal_invoice_item):
    invoice = Invoice(items=[minimal_invoice_item], supplier_id="sid", default_store_id="dsid")
    assert len(invoice.items) == 1
    assert invoice.supplier_id == "sid"


# --- Tests for SyrveClient.from_env ---
@patch.dict(
    os.environ,
    {"SYRVE_BASE_URL": "http://env.url", "SYRVE_LOGIN": "env_login", "SYRVE_PASS_SHA1": "env_hash"},
)
def test_syrve_client_from_env_success():
    client = SyrveClient.from_env()
    assert client.base_url == "http://env.url"  # rstrip '/' is handled by __init__
    assert client.login == "env_login"
    assert client.password_sha1 == "env_hash"


@patch.dict(os.environ, {}, clear=True)  # Ensure relevant vars are not set
def test_syrve_client_from_env_missing_base_url():
    with pytest.raises(ValueError, match="Missing required environment variables"):
        SyrveClient.from_env()


@patch.dict(os.environ, {"SYRVE_BASE_URL": "http://env.url"}, clear=True)
def test_syrve_client_from_env_missing_login():
    with pytest.raises(ValueError, match="Missing required environment variables"):
        SyrveClient.from_env()


@patch.dict(os.environ, {"SYRVE_BASE_URL": "http://url", "SYRVE_LOGIN": "login"}, clear=True)
def test_syrve_client_from_env_missing_pass_sha1():
    with pytest.raises(ValueError, match="Missing required environment variables"):
        SyrveClient.from_env()


# --- Tests for SyrveClient._is_token_valid ---
def test_is_token_valid_no_token_or_expiry(syrve_client):
    syrve_client._token = None
    syrve_client._token_expiry = None
    assert not syrve_client._is_token_valid()

    syrve_client._token = "testtoken"
    syrve_client._token_expiry = None
    assert not syrve_client._is_token_valid()


def test_is_token_valid_token_expired(syrve_client):
    syrve_client._token = "testtoken"
    syrve_client._token_expiry = datetime.now() - timedelta(minutes=1)  # Expired 1 min ago
    assert not syrve_client._is_token_valid()


def test_is_token_valid_token_near_expiry(syrve_client):
    syrve_client._token = "testtoken"
    # Expires in less than TOKEN_REFRESH_THRESHOLD (e.g., 3 minutes if threshold is 5)
    syrve_client._token_expiry = datetime.now() + timedelta(
        minutes=SyrveClient.TOKEN_REFRESH_THRESHOLD - 2
    )
    assert not syrve_client._is_token_valid()


def test_is_token_valid_token_is_valid(syrve_client):
    syrve_client._token = "testtoken"
    syrve_client._token_expiry = datetime.now() + timedelta(minutes=SyrveClient.TOKEN_CACHE_MINUTES)
    assert syrve_client._is_token_valid()


# --- Tests for SyrveClient.validate_invoice ---
def test_validate_invoice_valid(syrve_client, minimal_invoice):
    try:
        syrve_client.validate_invoice(minimal_invoice)
    except InvoiceValidationError:
        pytest.fail(
            "validate_invoice raised InvoiceValidationError unexpectedly for a valid invoice"
        )


def test_validate_invoice_invalid_supplier_id(syrve_client, minimal_invoice):
    minimal_invoice.supplier_id = "invalid-guid"
    with pytest.raises(InvoiceValidationError, match="Invalid supplier_id format"):
        syrve_client.validate_invoice(minimal_invoice)


def test_validate_invoice_invalid_default_store_id(syrve_client, minimal_invoice):
    minimal_invoice.default_store_id = "invalid-guid"
    with pytest.raises(InvoiceValidationError, match="Invalid default_store_id format"):
        syrve_client.validate_invoice(minimal_invoice)


def test_validate_invoice_invalid_conception_id(syrve_client, minimal_invoice):
    minimal_invoice.conception_id = "invalid-guid"
    with pytest.raises(InvoiceValidationError, match="Invalid conception_id format"):
        syrve_client.validate_invoice(minimal_invoice)


def test_validate_invoice_no_items(syrve_client, minimal_invoice):
    minimal_invoice.items = []
    with pytest.raises(InvoiceValidationError, match="Invoice must contain at least one item"):
        syrve_client.validate_invoice(minimal_invoice)


def test_validate_invoice_date_too_far_future(syrve_client, minimal_invoice):
    minimal_invoice.date_incoming = date.today() + timedelta(days=2)
    with pytest.raises(InvoiceValidationError, match="cannot be later than"):
        syrve_client.validate_invoice(minimal_invoice)


def test_validate_invoice_item_invalid_product_id(syrve_client, minimal_invoice):
    minimal_invoice.items[0].product_id = "invalid-item-guid"
    with pytest.raises(InvoiceValidationError, match="Invalid product_id format"):
        syrve_client.validate_invoice(minimal_invoice)


def test_validate_invoice_item_invalid_store_id(syrve_client, minimal_invoice):
    minimal_invoice.items[0].store_id = "invalid-item-store-guid"
    with pytest.raises(InvoiceValidationError, match="Invalid store_id format"):
        syrve_client.validate_invoice(minimal_invoice)


@pytest.mark.parametrize(
    "amount, price, item_sum_str, expected_error_msg_part",
    [
        (Decimal("0"), Decimal("10"), "0.00", "amount must be positive"),
        (Decimal("-1"), Decimal("10"), "-10.00", "amount must be positive"),
        (Decimal("1"), Decimal("-1"), "-1.00", "price cannot be negative"),
        (
            Decimal("1"),
            Decimal("1"),
            "-1.00",
            "sum cannot be negative",
        ),  # Sum is negative, price positive
        (
            Decimal("10.00"),
            Decimal("1.50"),
            "14.99",
            "does not match price*amount",
        ),  # Sum mismatch (small diff)
        (
            Decimal("3.0"),
            Decimal("3.33"),
            "9.98",
            "does not match price*amount",
        ),  # Sum mismatch (rounding)
        (
            Decimal("3.0"),
            Decimal("3.33"),
            "10.00",
            "does not match price*amount",
        ),  # Sum mismatch (rounding)
    ],
)
def test_validate_invoice_item_numeric_and_sum_errors(
    syrve_client, minimal_invoice, amount, price, item_sum_str, expected_error_msg_part
):
    item_sum = Decimal(item_sum_str)
    minimal_invoice.items[0].amount = amount
    minimal_invoice.items[0].price = price
    minimal_invoice.items[0].sum = item_sum

    with pytest.raises(InvoiceValidationError, match=expected_error_msg_part):
        syrve_client.validate_invoice(minimal_invoice)


def test_validate_invoice_item_sum_correct_rounding(syrve_client, minimal_invoice):
    # Test correct rounding for sum: 1/3 * 3 = 0.99, but price * qty might be 0.999...
    # Example: amount=1, price=0.33, sum should be 0.33.  amount=3, price=0.33, sum=0.99
    # Example: amount=Decimal("0.333"), price=Decimal("3"), sum should be Decimal("1.00") if product is 0.999
    # Let's use a clear case: 2 items at 0.005 each. Sum for one should be 0.01.
    minimal_invoice.items = [
        InvoiceItem(
            num=1,
            product_id=VALID_GUID,
            amount=Decimal("1"),
            price=Decimal("0.005"),
            sum=Decimal("0.01"),
        )
    ]
    try:  # Should pass if sum is rounded correctly (0.005 rounds up to 0.01)
        syrve_client.validate_invoice(minimal_invoice)
    except InvoiceValidationError as e:
        pytest.fail(f"Validation failed for correct rounding: {e}")

    minimal_invoice.items = (
        [  # sum = 0.004, price*amount = 0.005. diff = 0.001. This should pass as diff <= 0.01
            InvoiceItem(
                num=1,
                product_id=VALID_GUID,
                amount=Decimal("1"),
                price=Decimal("0.005"),
                sum=Decimal("0.00"),
            )
        ]
    )
    # This was expected to fail before, but the check is `diff > Decimal('0.01')`
    # 0.005 (expected) vs 0.00 (actual). diff is 0.005. 0.005 is not > 0.01. So it should pass.
    # Let's try a case that should fail: sum=0.02, price*amount=0.005. diff=0.015
    minimal_invoice.items = [
        InvoiceItem(
            num=1,
            product_id=VALID_GUID,
            amount=Decimal("1"),
            price=Decimal("0.005"),
            sum=Decimal("0.02"),
        )
    ]
    with pytest.raises(InvoiceValidationError, match="does not match price*amount"):
        syrve_client.validate_invoice(minimal_invoice)


# --- Tests for SyrveClient.generate_invoice_xml ---
def test_generate_invoice_xml_minimal(syrve_client, minimal_invoice):
    xml_string = syrve_client.generate_invoice_xml(minimal_invoice)

    assert "<document>" in xml_string
    assert f"<productId>{minimal_invoice.items[0].product_id}</productId>" in xml_string
    assert f"<amount>{minimal_invoice.items[0].amount}</amount>" in xml_string
    assert f"<price>{minimal_invoice.items[0].price}</price>" in xml_string
    assert f"<sum>{minimal_invoice.items[0].sum}</sum>" in xml_string
    assert f"<supplier>{minimal_invoice.supplier_id}</supplier>" in xml_string
    assert f"<defaultStore>{minimal_invoice.default_store_id}</defaultStore>" in xml_string
    assert "<externalId>" in xml_string  # Auto-generated

    # Optional fields that should NOT be present for minimal_invoice
    assert "<conception>" not in xml_string
    assert "<documentNumber>" not in xml_string
    assert "<dateIncoming>" not in xml_string
    assert "<storeId>" not in xml_string  # Item specific storeId


def test_generate_invoice_xml_all_fields(syrve_client, minimal_invoice):
    minimal_invoice.conception_id = VALID_GUID
    minimal_invoice.document_number = "DOC123"
    minimal_invoice.date_incoming = date(2023, 1, 15)
    minimal_invoice.external_id = "EXT001"
    minimal_invoice.items[0].store_id = VALID_GUID_2  # Item specific storeId

    xml_string = syrve_client.generate_invoice_xml(minimal_invoice)

    assert f"<conception>{minimal_invoice.conception_id}</conception>" in xml_string
    assert f"<documentNumber>{minimal_invoice.document_number}</documentNumber>" in xml_string
    assert "<dateIncoming>2023-01-15</dateIncoming>" in xml_string
    assert f"<externalId>{minimal_invoice.external_id}</externalId>" in xml_string
    assert f"<storeId>{minimal_invoice.items[0].store_id}</storeId>" in xml_string


@patch("app.services.syrve_invoice_sender.uuid.uuid4")
def test_generate_invoice_xml_auto_external_id(mock_uuid, syrve_client, minimal_invoice):
    mock_uuid.return_value = MagicMock(hex="testhexuuid")
    minimal_invoice.external_id = None  # Ensure it's not set

    xml_string = syrve_client.generate_invoice_xml(minimal_invoice)

    assert "<externalId>testhexuuid</externalId>" in xml_string
    mock_uuid.assert_called_once()


# --- Tests for SyrveClient.send_invoice (orchestration) ---
@patch.object(SyrveClient, "validate_invoice", MagicMock())
@patch.object(SyrveClient, "generate_invoice_xml", MagicMock(return_value="<xml></xml>"))
@patch.object(SyrveClient, "validate_xml_schema", MagicMock())  # Assume valid for now
@patch.object(
    SyrveClient, "send_invoice_xml", MagicMock(return_value=True)
)  # Simulate successful send
def test_send_invoice_successful_flow(syrve_client, minimal_invoice):
    # Ensure document_number and date_incoming are initially None to test auto-generation
    minimal_invoice.document_number = None
    minimal_invoice.date_incoming = None

    original_external_id = minimal_invoice.external_id  # Could be None or set

    result = syrve_client.send_invoice(minimal_invoice)

    assert result is True  # from send_invoice_xml mock

    SyrveClient.validate_invoice.assert_called_once_with(minimal_invoice)
    SyrveClient.generate_invoice_xml.assert_called_once_with(minimal_invoice)
    SyrveClient.validate_xml_schema.assert_called_once_with("<xml></xml>")
    SyrveClient.send_invoice_xml.assert_called_once_with("<xml></xml>")

    # Check auto-generated fields
    assert minimal_invoice.document_number is not None
    assert minimal_invoice.document_number.startswith(f"AUTO-{date.today().strftime('%Y%m%d')}-")
    assert minimal_invoice.date_incoming == date.today()

    # External ID should either be the original one or a new UUID if original was None
    if original_external_id:
        assert minimal_invoice.external_id == original_external_id
    else:
        # If it was None, generate_invoice_xml would have created one.
        # We can't easily check its value here without re-mocking uuid inside generate_invoice_xml
        # but we know it was called.
        pass


def test_send_invoice_validation_fails(syrve_client, minimal_invoice):
    with patch.object(
        SyrveClient, "validate_invoice", side_effect=InvoiceValidationError("Validation Failed")
    ):
        with pytest.raises(InvoiceValidationError, match="Validation Failed"):
            syrve_client.send_invoice(minimal_invoice)
        SyrveClient.generate_invoice_xml.assert_not_called()  # Should not proceed


# --- Test for on_result callback in send_invoice_xml ---
# This requires more complex mocking of httpx.Client behavior, similar to test_api_integration.py
# but using pytest and direct client instantiation.


@pytest.mark.parametrize(
    "response_status, response_text, expected_on_result_success, expected_exception_type",
    [
        (
            200,
            "<documentValidationResult><valid>true</valid></documentValidationResult>",
            True,
            None,
        ),
        (
            200,
            "<documentValidationResult><valid>false</valid><errorMessage>Bad data</errorMessage></documentValidationResult>",
            False,
            InvoiceValidationError,
        ),
        (
            503,
            "Service Unavailable",
            False,
            InvoiceHTTPError,
        ),  # Retriable, but assume max_retries = 0 for this test
        (400, "Bad Request", False, InvoiceHTTPError),
    ],
)
@patch.object(SyrveClient, "get_token", MagicMock(return_value="mock_token"))  # Mock get_token
def test_send_invoice_xml_on_result_callback(
    syrve_client_base_args,
    response_status,
    response_text,
    expected_on_result_success,
    expected_exception_type,
    caplog,
):
    mock_on_result_callback = MagicMock()

    # Re-initialize client for this specific test to set max_retries and on_result
    # and to use a fresh mock for http.post
    client = SyrveClient(**syrve_client_base_args, max_retries=0, on_result=mock_on_result_callback)

    # Mock the HTTP response
    mock_http_response = MagicMock(spec=httpx.Response)
    mock_http_response.status_code = response_status
    mock_http_response.text = response_text
    mock_http_response.headers = {}  # Default headers

    # Configure the client's http mock to return this response
    client.http = MagicMock()
    if response_status >= 400:  # httpx.HTTPStatusError
        http_error = httpx.HTTPStatusError(
            message="Error", request=MagicMock(), response=mock_http_response
        )
        client.http.post = MagicMock(side_effect=http_error)
    else:  # Successful HTTP status, but potentially failed validation by Syrve
        client.http.post = MagicMock(return_value=mock_http_response)

    xml_to_send = "<invoice_data/>"

    if expected_exception_type:
        with pytest.raises(expected_exception_type):
            client.send_invoice_xml(xml_to_send)
    else:
        client.send_invoice_xml(xml_to_send)

    mock_on_result_callback.assert_called_once()
    args, _ = mock_on_result_callback.call_args
    assert args[0] == expected_on_result_success  # success (bool)
    assert isinstance(args[1], float)  # elapsed_time (float)
    if expected_exception_type:
        assert isinstance(args[2], expected_exception_type)  # exception
    else:
        assert args[2] is None  # No exception
