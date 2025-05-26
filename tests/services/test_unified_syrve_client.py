"""
Unit tests for UnifiedSyrveClient.
"""

import asyncio
import pytest
from decimal import Decimal
from unittest.mock import Mock, patch, AsyncMock
from datetime import date

from app.services.unified_syrve_client import (
    UnifiedSyrveClient,
    Invoice,
    InvoiceItem,
    SyrveError,
    SyrveAuthError,
    SyrveValidationError,
    SyrveHTTPError,
    SyrveRetryError,
)


# Test fixtures
@pytest.fixture
def sample_invoice_item():
    return InvoiceItem(
        num=1,
        product_id="12345678-1234-1234-1234-123456789abc",
        amount=Decimal("5.0"),
        price=Decimal("10.50"),
        sum=Decimal("52.50"),  # 5.0 * 10.50
    )


@pytest.fixture
def sample_invoice(sample_invoice_item):
    return Invoice(
        items=[sample_invoice_item],
        supplier_id="supplier-guid-1234",
        default_store_id="store-guid-5678",
        conception_id="conception-guid-9012",
        document_number="TEST-001",
        date_incoming=date(2025, 5, 26),
    )


@pytest.fixture
def mock_client():
    return UnifiedSyrveClient(
        base_url="https://test.syrve.api",
        login="testuser",
        password_sha1="da39a3ee5e6b4b0d3255bfef95601890afd80709",  # SHA1 of empty string
        verify_ssl=False,
        max_retries=1,  # Reduce for faster tests
    )


@pytest.fixture
def success_xml_response():
    return """<?xml version="1.0" encoding="UTF-8"?>
<documentValidationResult>
    <valid>true</valid>
    <documentNumber>SYRVE-123456</documentNumber>
</documentValidationResult>"""


@pytest.fixture
def error_xml_response():
    return """<?xml version="1.0" encoding="UTF-8"?>
<documentValidationResult>
    <valid>false</valid>
    <error>Invalid supplier ID</error>
</documentValidationResult>"""


class TestInvoiceItem:
    """Test InvoiceItem validation."""
    
    def test_valid_invoice_item(self, sample_invoice_item):
        """Test valid invoice item creation."""
        item = sample_invoice_item
        assert item.num == 1
        assert item.product_id == "12345678-1234-1234-1234-123456789abc"
        assert item.amount == Decimal("5.0")
        assert item.price == Decimal("10.50")
        assert item.sum == Decimal("52.50")
    
    def test_empty_product_id_raises_error(self):
        """Test that empty product ID raises validation error."""
        with pytest.raises(SyrveValidationError, match="Product ID cannot be empty"):
            InvoiceItem(
                num=1,
                product_id="",
                amount=Decimal("5.0"),
                price=Decimal("10.50"),
                sum=Decimal("52.50"),
            )
    
    def test_negative_amount_raises_error(self):
        """Test that negative amount raises validation error."""
        with pytest.raises(SyrveValidationError, match="Amount must be positive"):
            InvoiceItem(
                num=1,
                product_id="test-guid",
                amount=Decimal("-1.0"),
                price=Decimal("10.50"),
                sum=Decimal("52.50"),
            )
    
    def test_negative_price_raises_error(self):
        """Test that negative price raises validation error."""
        with pytest.raises(SyrveValidationError, match="Price cannot be negative"):
            InvoiceItem(
                num=1,
                product_id="test-guid",
                amount=Decimal("5.0"),
                price=Decimal("-10.50"),
                sum=Decimal("52.50"),
            )
    
    def test_arithmetic_validation_error(self):
        """Test that incorrect sum raises validation error."""
        with pytest.raises(SyrveValidationError, match="sum .* does not match price\\*amount"):
            InvoiceItem(
                num=1,
                product_id="test-guid",
                amount=Decimal("5.0"),
                price=Decimal("10.50"),
                sum=Decimal("100.00"),  # Wrong sum
            )


class TestInvoice:
    """Test Invoice validation."""
    
    def test_valid_invoice(self, sample_invoice):
        """Test valid invoice creation."""
        invoice = sample_invoice
        assert len(invoice.items) == 1
        assert invoice.supplier_id == "supplier-guid-1234"
        assert invoice.default_store_id == "store-guid-5678"
        assert invoice.document_number == "TEST-001"
    
    def test_empty_items_raises_error(self):
        """Test that empty items list raises validation error."""
        with pytest.raises(SyrveValidationError, match="Invoice must contain at least one item"):
            Invoice(
                items=[],
                supplier_id="supplier-guid",
                default_store_id="store-guid",
            )
    
    def test_auto_generate_document_number(self, sample_invoice_item):
        """Test auto-generation of document number."""
        invoice = Invoice(
            items=[sample_invoice_item],
            supplier_id="supplier-guid",
            default_store_id="store-guid",
        )
        assert invoice.document_number.startswith("AUTO-")
        assert len(invoice.document_number) > 10
    
    def test_auto_set_date(self, sample_invoice_item):
        """Test auto-setting of incoming date."""
        invoice = Invoice(
            items=[sample_invoice_item],
            supplier_id="supplier-guid",
            default_store_id="store-guid",
        )
        assert invoice.date_incoming == date.today()


class TestUnifiedSyrveClient:
    """Test UnifiedSyrveClient functionality."""
    
    def test_client_initialization(self, mock_client):
        """Test client initialization."""
        assert mock_client.base_url == "https://test.syrve.api"
        assert mock_client.login == "testuser"
        assert mock_client.password_sha1 == "da39a3ee5e6b4b0d3255bfef95601890afd80709"
        assert mock_client.verify_ssl is False
        assert mock_client.max_retries == 1
    
    def test_from_env_missing_url(self):
        """Test that missing SYRVE_SERVER_URL raises error."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(SyrveAuthError, match="SYRVE_SERVER_URL environment variable is required"):
                UnifiedSyrveClient.from_env()
    
    def test_from_env_missing_credentials(self):
        """Test that missing credentials raise error."""
        with patch.dict("os.environ", {"SYRVE_SERVER_URL": "https://test.com"}, clear=True):
            with pytest.raises(SyrveAuthError, match="SYRVE_LOGIN environment variable is required"):
                UnifiedSyrveClient.from_env()
    
    @patch.dict("os.environ", {
        "SYRVE_SERVER_URL": "https://test.syrve.api",
        "SYRVE_LOGIN": "testuser",
        "SYRVE_PASS_SHA1": "testhash",
        "VERIFY_SSL": "1"
    })
    def test_from_env_success(self):
        """Test successful client creation from environment."""
        client = UnifiedSyrveClient.from_env()
        assert client.base_url == "https://test.syrve.api"
        assert client.login == "testuser"
        assert client.password_sha1 == "testhash"
        assert client.verify_ssl is True
    
    def test_generate_invoice_xml(self, mock_client, sample_invoice):
        """Test XML generation."""
        xml = mock_client.generate_invoice_xml(sample_invoice)
        
        # Basic structure checks
        assert "<?xml version=" in xml
        assert "<document>" in xml
        assert "</document>" in xml
        assert "<items>" in xml
        assert "<item>" in xml
        
        # Content checks
        assert "supplier-guid-1234" in xml
        assert "store-guid-5678" in xml
        assert "TEST-001" in xml
        assert "2025-05-26T08:00:00" in xml
        assert "12345678-1234-1234-1234-123456789abc" in xml
        assert "5.0" in xml
        assert "10.50" in xml
        assert "52.50" in xml


class TestAsyncOperations:
    """Test async operations."""
    
    @pytest.mark.asyncio
    async def test_get_token_async_success(self, mock_client):
        """Test successful token retrieval."""
        mock_response = Mock()
        mock_response.text = "test-token-12345"
        mock_response.raise_for_status = Mock()
        
        with patch("httpx.AsyncClient") as mock_http_client:
            mock_client_instance = AsyncMock()
            mock_http_client.return_value.__aenter__.return_value = mock_client_instance
            mock_client_instance.get.return_value = mock_response
            
            token = await mock_client.get_token_async()
            
            assert token == "test-token-12345"
            assert mock_client._token == "test-token-12345"
            assert mock_client._token_timestamp is not None
    
    @pytest.mark.asyncio
    async def test_get_token_async_auth_error(self, mock_client):
        """Test authentication error handling."""
        from httpx import HTTPStatusError, Response, Request
        
        mock_request = Mock(spec=Request)
        mock_response = Mock(spec=Response)
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        
        with patch("httpx.AsyncClient") as mock_http_client:
            mock_client_instance = AsyncMock()
            mock_http_client.return_value.__aenter__.return_value = mock_client_instance
            mock_client_instance.get.side_effect = HTTPStatusError(
                "401 Unauthorized", request=mock_request, response=mock_response
            )
            
            with pytest.raises(SyrveAuthError, match="Authentication failed: 401"):
                await mock_client.get_token_async()
    
    @pytest.mark.asyncio
    async def test_send_invoice_async_success(self, mock_client, sample_invoice, success_xml_response):
        """Test successful invoice sending."""
        # Mock token request
        mock_token_response = Mock()
        mock_token_response.text = "test-token"
        mock_token_response.raise_for_status = Mock()
        
        # Mock invoice send request
        mock_send_response = Mock()
        mock_send_response.status_code = 200
        mock_send_response.text = success_xml_response
        
        with patch("httpx.AsyncClient") as mock_http_client:
            mock_client_instance = AsyncMock()
            mock_http_client.return_value.__aenter__.return_value = mock_client_instance
            
            # Setup mock responses in order
            mock_client_instance.get.return_value = mock_token_response
            mock_client_instance.post.return_value = mock_send_response
            
            result = await mock_client.send_invoice_async(sample_invoice)
            
            assert result["success"] is True
            assert result["document_number"] == "SYRVE-123456"
            assert result["invoice_number"] == "TEST-001"
            assert "response_time" in result
    
    @pytest.mark.asyncio
    async def test_send_invoice_async_validation_error(self, mock_client, sample_invoice, error_xml_response):
        """Test invoice validation error handling."""
        # Mock token request
        mock_token_response = Mock()
        mock_token_response.text = "test-token"
        mock_token_response.raise_for_status = Mock()
        
        # Mock invoice send request with validation error
        mock_send_response = Mock()
        mock_send_response.status_code = 200
        mock_send_response.text = error_xml_response
        
        with patch("httpx.AsyncClient") as mock_http_client:
            mock_client_instance = AsyncMock()
            mock_http_client.return_value.__aenter__.return_value = mock_client_instance
            
            mock_client_instance.get.return_value = mock_token_response
            mock_client_instance.post.return_value = mock_send_response
            
            with pytest.raises(SyrveValidationError, match="Syrve validation failed: Invalid supplier ID"):
                await mock_client.send_invoice_async(sample_invoice)
    
    @pytest.mark.asyncio
    async def test_retry_on_server_error(self, mock_client, sample_invoice):
        """Test retry logic on server errors."""
        # Mock token request
        mock_token_response = Mock()
        mock_token_response.text = "test-token"
        mock_token_response.raise_for_status = Mock()
        
        # Mock server error responses
        mock_error_response = Mock()
        mock_error_response.status_code = 502
        mock_error_response.text = "Bad Gateway"
        
        with patch("httpx.AsyncClient") as mock_http_client:
            mock_client_instance = AsyncMock()
            mock_http_client.return_value.__aenter__.return_value = mock_client_instance
            
            mock_client_instance.get.return_value = mock_token_response
            mock_client_instance.post.return_value = mock_error_response
            
            with pytest.raises(SyrveHTTPError, match="HTTP 502"):
                await mock_client.send_invoice_async(sample_invoice)
            
            # Should have retried (max_retries + 1 total attempts)
            assert mock_client_instance.post.call_count == 2  # 1 + 1 retry
    
    @pytest.mark.asyncio
    async def test_auto_reauth_on_401(self, mock_client, sample_invoice, success_xml_response):
        """Test automatic reauthorization on 401 error."""
        # Mock initial token request
        mock_token_response = Mock()
        mock_token_response.text = "initial-token"
        mock_token_response.raise_for_status = Mock()
        
        # Mock 401 response, then success response
        mock_401_response = Mock()
        mock_401_response.status_code = 401
        mock_401_response.text = "Unauthorized"
        
        mock_success_response = Mock()
        mock_success_response.status_code = 200
        mock_success_response.text = success_xml_response
        
        # Mock new token request
        mock_new_token_response = Mock()
        mock_new_token_response.text = "new-token"
        mock_new_token_response.raise_for_status = Mock()
        
        with patch("httpx.AsyncClient") as mock_http_client:
            mock_client_instance = AsyncMock()
            mock_http_client.return_value.__aenter__.return_value = mock_client_instance
            
            # Setup sequence: get token, post (401), get new token, post (success)
            mock_client_instance.get.side_effect = [mock_token_response, mock_new_token_response]
            mock_client_instance.post.side_effect = [mock_401_response, mock_success_response]
            
            result = await mock_client.send_invoice_async(sample_invoice)
            
            assert result["success"] is True
            # Should have made 2 token requests (initial + reauth)
            assert mock_client_instance.get.call_count == 2
            # Should have made 2 post requests (401 + success)
            assert mock_client_instance.post.call_count == 2


class TestSyncOperations:
    """Test sync operations."""
    
    def test_get_token_sync_success(self, mock_client):
        """Test successful sync token retrieval."""
        mock_response = Mock()
        mock_response.text = "sync-token-12345"
        mock_response.raise_for_status = Mock()
        
        with patch("httpx.Client") as mock_http_client:
            mock_client_instance = Mock()
            mock_http_client.return_value.__enter__.return_value = mock_client_instance
            mock_client_instance.get.return_value = mock_response
            
            token = mock_client.get_token_sync()
            
            assert token == "sync-token-12345"
            assert mock_client._token == "sync-token-12345"
    
    def test_send_invoice_sync_success(self, mock_client, sample_invoice, success_xml_response):
        """Test successful sync invoice sending."""
        # Mock token request
        mock_token_response = Mock()
        mock_token_response.text = "sync-token"
        mock_token_response.raise_for_status = Mock()
        
        # Mock invoice send request
        mock_send_response = Mock()
        mock_send_response.status_code = 200
        mock_send_response.text = success_xml_response
        
        with patch("httpx.Client") as mock_http_client:
            mock_client_instance = Mock()
            mock_http_client.return_value.__enter__.return_value = mock_client_instance
            
            mock_client_instance.get.return_value = mock_token_response
            mock_client_instance.post.return_value = mock_send_response
            
            result = mock_client.send_invoice_sync(sample_invoice)
            
            assert result["success"] is True
            assert result["document_number"] == "SYRVE-123456"


class TestResultCallback:
    """Test result callback functionality."""
    
    @pytest.mark.asyncio
    async def test_callback_on_success(self, sample_invoice, success_xml_response):
        """Test callback is called on successful operation."""
        callback_mock = Mock()
        
        client = UnifiedSyrveClient(
            base_url="https://test.syrve.api",
            login="testuser",
            password_sha1="testhash",
            on_result=callback_mock,
            max_retries=0,
        )
        
        # Mock successful flow
        mock_token_response = Mock()
        mock_token_response.text = "test-token"
        mock_token_response.raise_for_status = Mock()
        
        mock_send_response = Mock()
        mock_send_response.status_code = 200
        mock_send_response.text = success_xml_response
        
        with patch("httpx.AsyncClient") as mock_http_client:
            mock_client_instance = AsyncMock()
            mock_http_client.return_value.__aenter__.return_value = mock_client_instance
            
            mock_client_instance.get.return_value = mock_token_response
            mock_client_instance.post.return_value = mock_send_response
            
            await client.send_invoice_async(sample_invoice)
            
            # Verify callback was called with success
            callback_mock.assert_called_once()
            args = callback_mock.call_args[0]
            assert args[0] is True  # success
            assert isinstance(args[1], float)  # elapsed_time
            assert args[2] is None  # exception
    
    @pytest.mark.asyncio
    async def test_callback_on_error(self, sample_invoice):
        """Test callback is called on error."""
        callback_mock = Mock()
        
        client = UnifiedSyrveClient(
            base_url="https://test.syrve.api",
            login="testuser",
            password_sha1="testhash",
            on_result=callback_mock,
            max_retries=0,
        )
        
        # Mock auth error
        with patch("httpx.AsyncClient") as mock_http_client:
            mock_client_instance = AsyncMock()
            mock_http_client.return_value.__aenter__.return_value = mock_client_instance
            mock_client_instance.get.side_effect = Exception("Network error")
            
            with pytest.raises(SyrveAuthError):
                await client.send_invoice_async(sample_invoice)
            
            # Verify callback was called with error
            callback_mock.assert_called_once()
            args = callback_mock.call_args[0]
            assert args[0] is False  # success
            assert isinstance(args[1], float)  # elapsed_time
            assert isinstance(args[2], Exception)  # exception


if __name__ == "__main__":
    pytest.main([__file__])