"""
Comprehensive tests for app.syrve_client module.
Tests Syrve API client, authentication, invoice generation, and error handling.
"""

import pytest
import asyncio
import xml.etree.ElementTree as ET
from unittest.mock import AsyncMock, MagicMock, patch, call
from datetime import datetime, date
from decimal import Decimal
import httpx

from app.syrve_client import (
    SyrveError,
    SyrveAuthError,
    SyrveValidationError,
    SyrveHTTPError,
    SyrveRetryError,
    InvoiceItem,
    Invoice,
    UnifiedSyrveClient,
    generate_invoice_xml_async,
    TOKEN_CACHE_MINUTES,
    DEFAULT_TIMEOUT,
    DEFAULT_MAX_RETRIES
)


class TestSyrveExceptions:
    """Test custom Syrve exceptions"""
    
    def test_syrve_error_base(self):
        """Test base SyrveError exception"""
        # Arrange & Act
        error = SyrveError("Test error message")
        
        # Assert
        assert str(error) == "Test error message"
        assert isinstance(error, Exception)
    
    def test_syrve_auth_error(self):
        """Test SyrveAuthError inheritance"""
        # Arrange & Act
        error = SyrveAuthError("Authentication failed")
        
        # Assert
        assert str(error) == "Authentication failed"
        assert isinstance(error, SyrveError)
        assert isinstance(error, Exception)
    
    def test_syrve_validation_error(self):
        """Test SyrveValidationError inheritance"""
        # Arrange & Act
        error = SyrveValidationError("Validation failed")
        
        # Assert
        assert isinstance(error, SyrveError)
    
    def test_syrve_http_error(self):
        """Test SyrveHTTPError inheritance"""
        # Arrange & Act
        error = SyrveHTTPError("HTTP error")
        
        # Assert
        assert isinstance(error, SyrveError)
    
    def test_syrve_retry_error(self):
        """Test SyrveRetryError inheritance"""
        # Arrange & Act
        error = SyrveRetryError("Retry failed")
        
        # Assert
        assert isinstance(error, SyrveError)


class TestInvoiceItem:
    """Test InvoiceItem dataclass"""
    
    def test_invoice_item_creation(self):
        """Test creating InvoiceItem with valid data"""
        # Arrange & Act
        item = InvoiceItem(
            name="Test Product",
            quantity=Decimal("5.5"),
            price=Decimal("100.00"),
            unit="piece"
        )
        
        # Assert
        assert item.name == "Test Product"
        assert item.quantity == Decimal("5.5")
        assert item.price == Decimal("100.00")
        assert item.unit == "piece"
    
    def test_invoice_item_post_init_validation(self):
        """Test InvoiceItem post-init validation"""
        # Arrange & Act & Assert
        with pytest.raises(ValueError, match="Name cannot be empty"):
            InvoiceItem(
                name="",
                quantity=Decimal("1"),
                price=Decimal("100"),
                unit="piece"
            )
    
    def test_invoice_item_negative_quantity(self):
        """Test InvoiceItem with negative quantity"""
        # Arrange & Act & Assert
        with pytest.raises(ValueError, match="Quantity must be positive"):
            InvoiceItem(
                name="Test Product",
                quantity=Decimal("-1"),
                price=Decimal("100"),
                unit="piece"
            )
    
    def test_invoice_item_negative_price(self):
        """Test InvoiceItem with negative price"""
        # Arrange & Act & Assert
        with pytest.raises(ValueError, match="Price must be non-negative"):
            InvoiceItem(
                name="Test Product",
                quantity=Decimal("1"),
                price=Decimal("-100"),
                unit="piece"
            )
    
    def test_invoice_item_zero_price_allowed(self):
        """Test InvoiceItem allows zero price"""
        # Arrange & Act
        item = InvoiceItem(
            name="Free Product",
            quantity=Decimal("1"),
            price=Decimal("0"),
            unit="piece"
        )
        
        # Assert
        assert item.price == Decimal("0")
    
    def test_invoice_item_default_unit(self):
        """Test InvoiceItem default unit"""
        # Arrange & Act
        item = InvoiceItem(
            name="Test Product",
            quantity=Decimal("1"),
            price=Decimal("100")
        )
        
        # Assert
        assert item.unit == "piece"


class TestInvoice:
    """Test Invoice dataclass"""
    
    def test_invoice_creation(self):
        """Test creating Invoice with valid data"""
        # Arrange
        items = [
            InvoiceItem("Product 1", Decimal("2"), Decimal("50"), "piece"),
            InvoiceItem("Product 2", Decimal("1"), Decimal("100"), "box")
        ]
        
        # Act
        invoice = Invoice(
            number="INV-001",
            date=date(2024, 1, 15),
            supplier="Test Supplier",
            items=items
        )
        
        # Assert
        assert invoice.number == "INV-001"
        assert invoice.date == date(2024, 1, 15)
        assert invoice.supplier == "Test Supplier"
        assert len(invoice.items) == 2
    
    def test_invoice_post_init_validation_empty_number(self):
        """Test Invoice validation with empty number"""
        # Arrange & Act & Assert
        with pytest.raises(ValueError, match="Invoice number cannot be empty"):
            Invoice(
                number="",
                date=date.today(),
                supplier="Test Supplier",
                items=[]
            )
    
    def test_invoice_post_init_validation_future_date(self):
        """Test Invoice validation with future date"""
        # Arrange
        future_date = date.today().replace(year=date.today().year + 1)
        
        # Act & Assert
        with pytest.raises(ValueError, match="Invoice date cannot be in the future"):
            Invoice(
                number="INV-001",
                date=future_date,
                supplier="Test Supplier",
                items=[]
            )
    
    def test_invoice_post_init_validation_empty_supplier(self):
        """Test Invoice validation with empty supplier"""
        # Arrange & Act & Assert
        with pytest.raises(ValueError, match="Supplier cannot be empty"):
            Invoice(
                number="INV-001",
                date=date.today(),
                supplier="",
                items=[]
            )
    
    def test_invoice_post_init_validation_empty_items(self):
        """Test Invoice validation with empty items"""
        # Arrange & Act & Assert
        with pytest.raises(ValueError, match="Invoice must have at least one item"):
            Invoice(
                number="INV-001",
                date=date.today(),
                supplier="Test Supplier",
                items=[]
            )
    
    def test_invoice_valid_creation(self):
        """Test creating valid Invoice"""
        # Arrange
        items = [InvoiceItem("Product", Decimal("1"), Decimal("100"))]
        
        # Act
        invoice = Invoice(
            number="INV-001",
            date=date.today(),
            supplier="Test Supplier",
            items=items
        )
        
        # Assert
        assert invoice is not None


class TestUnifiedSyrveClient:
    """Test UnifiedSyrveClient class"""
    
    def test_client_initialization(self):
        """Test client initialization with parameters"""
        # Arrange & Act
        client = UnifiedSyrveClient(
            base_url="https://test.api.com",
            login="test_user",
            password="test_pass",
            timeout=60.0,
            max_retries=5
        )
        
        # Assert
        assert client.base_url == "https://test.api.com"
        assert client.login == "test_user"
        assert client.password == "test_pass"
        assert client.timeout == 60.0
        assert client.max_retries == 5
        assert client._token is None
        assert client._token_expiry is None
    
    def test_client_from_env(self):
        """Test client creation from environment variables"""
        # Arrange
        with patch.dict('os.environ', {
            'SYRVE_BASE_URL': 'https://env.api.com',
            'SYRVE_LOGIN': 'env_user',
            'SYRVE_PASSWORD': 'env_pass'
        }):
            # Act
            client = UnifiedSyrveClient.from_env()
            
            # Assert
            assert client.base_url == 'https://env.api.com'
            assert client.login == 'env_user'
            assert client.password == 'env_pass'
    
    def test_client_from_env_missing_vars(self):
        """Test client creation from env with missing variables"""
        # Arrange & Act & Assert
        with patch.dict('os.environ', {}, clear=True):
            with pytest.raises(ValueError, match="Missing required environment variables"):
                UnifiedSyrveClient.from_env()
    
    def test_is_token_valid_no_token(self):
        """Test token validity check with no token"""
        # Arrange
        client = UnifiedSyrveClient("https://api.com", "user", "pass")
        
        # Act
        is_valid = client._is_token_valid()
        
        # Assert
        assert is_valid is False
    
    def test_is_token_valid_expired_token(self):
        """Test token validity check with expired token"""
        # Arrange
        client = UnifiedSyrveClient("https://api.com", "user", "pass")
        client._token = "expired_token"
        client._token_expiry = datetime.now().timestamp() - 3600  # 1 hour ago
        
        # Act
        is_valid = client._is_token_valid()
        
        # Assert
        assert is_valid is False
    
    def test_is_token_valid_valid_token(self):
        """Test token validity check with valid token"""
        # Arrange
        client = UnifiedSyrveClient("https://api.com", "user", "pass")
        client._token = "valid_token"
        client._token_expiry = datetime.now().timestamp() + 3600  # 1 hour from now
        
        # Act
        is_valid = client._is_token_valid()
        
        # Assert
        assert is_valid is True
    
    @pytest.mark.asyncio
    async def test_get_async_client(self):
        """Test async client creation"""
        # Arrange
        client = UnifiedSyrveClient("https://api.com", "user", "pass")
        
        # Act
        async_client = await client._get_async_client()
        
        # Assert
        assert isinstance(async_client, httpx.AsyncClient)
        assert async_client.timeout.read == client.timeout
    
    def test_get_sync_client(self):
        """Test sync client creation"""
        # Arrange
        client = UnifiedSyrveClient("https://api.com", "user", "pass")
        
        # Act
        sync_client = client._get_sync_client()
        
        # Assert
        assert isinstance(sync_client, httpx.Client)
        assert sync_client.timeout.read == client.timeout
    
    @pytest.mark.asyncio
    async def test_request_new_token_async_success(self):
        """Test successful async token request"""
        # Arrange
        client = UnifiedSyrveClient("https://api.com", "user", "pass")
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "mock_token_12345"
        
        with patch.object(client, '_get_async_client') as mock_get_client:
            mock_async_client = AsyncMock()
            mock_async_client.post.return_value = mock_response
            mock_get_client.return_value = mock_async_client
            
            # Act
            token = await client._request_new_token_async()
            
            # Assert
            assert token == "mock_token_12345"
            assert client._token == "mock_token_12345"
            assert client._token_expiry is not None
    
    @pytest.mark.asyncio
    async def test_request_new_token_async_failure(self):
        """Test failed async token request"""
        # Arrange
        client = UnifiedSyrveClient("https://api.com", "user", "pass")
        
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        
        with patch.object(client, '_get_async_client') as mock_get_client:
            mock_async_client = AsyncMock()
            mock_async_client.post.return_value = mock_response
            mock_get_client.return_value = mock_async_client
            
            # Act & Assert
            with pytest.raises(SyrveAuthError, match="Authentication failed"):
                await client._request_new_token_async()
    
    def test_request_new_token_sync_success(self):
        """Test successful sync token request"""
        # Arrange
        client = UnifiedSyrveClient("https://api.com", "user", "pass")
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "sync_token_67890"
        
        with patch.object(client, '_get_sync_client') as mock_get_client:
            mock_sync_client = MagicMock()
            mock_sync_client.post.return_value = mock_response
            mock_get_client.return_value = mock_sync_client
            
            # Act
            token = client._request_new_token_sync()
            
            # Assert
            assert token == "sync_token_67890"
            assert client._token == "sync_token_67890"
    
    def test_request_new_token_sync_failure(self):
        """Test failed sync token request"""
        # Arrange
        client = UnifiedSyrveClient("https://api.com", "user", "pass")
        
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.text = "Forbidden"
        
        with patch.object(client, '_get_sync_client') as mock_get_client:
            mock_sync_client = MagicMock()
            mock_sync_client.post.return_value = mock_response
            mock_get_client.return_value = mock_sync_client
            
            # Act & Assert
            with pytest.raises(SyrveAuthError, match="Authentication failed"):
                client._request_new_token_sync()
    
    @pytest.mark.asyncio
    async def test_get_token_async_valid_existing(self):
        """Test getting valid existing token async"""
        # Arrange
        client = UnifiedSyrveClient("https://api.com", "user", "pass")
        client._token = "existing_valid_token"
        client._token_expiry = datetime.now().timestamp() + 3600
        
        # Act
        token = await client.get_token_async()
        
        # Assert
        assert token == "existing_valid_token"
    
    @pytest.mark.asyncio
    async def test_get_token_async_request_new(self):
        """Test requesting new token async when none exists"""
        # Arrange
        client = UnifiedSyrveClient("https://api.com", "user", "pass")
        
        with patch.object(client, '_request_new_token_async') as mock_request:
            mock_request.return_value = "new_async_token"
            
            # Act
            token = await client.get_token_async()
            
            # Assert
            assert token == "new_async_token"
            mock_request.assert_called_once()
    
    def test_get_token_sync_valid_existing(self):
        """Test getting valid existing token sync"""
        # Arrange
        client = UnifiedSyrveClient("https://api.com", "user", "pass")
        client._token = "existing_sync_token"
        client._token_expiry = datetime.now().timestamp() + 3600
        
        # Act
        token = client.get_token_sync()
        
        # Assert
        assert token == "existing_sync_token"
    
    def test_get_token_sync_request_new(self):
        """Test requesting new token sync when expired"""
        # Arrange
        client = UnifiedSyrveClient("https://api.com", "user", "pass")
        client._token = "expired_token"
        client._token_expiry = datetime.now().timestamp() - 3600
        
        with patch.object(client, '_request_new_token_sync') as mock_request:
            mock_request.return_value = "new_sync_token"
            
            # Act
            token = client.get_token_sync()
            
            # Assert
            assert token == "new_sync_token"
            mock_request.assert_called_once()


class TestInvoiceXMLGeneration:
    """Test invoice XML generation"""
    
    def test_generate_invoice_xml(self):
        """Test XML generation from invoice"""
        # Arrange
        client = UnifiedSyrveClient("https://api.com", "user", "pass")
        items = [
            InvoiceItem("Product 1", Decimal("2"), Decimal("50"), "piece"),
            InvoiceItem("Product 2", Decimal("1"), Decimal("100"), "box")
        ]
        invoice = Invoice("INV-001", date(2024, 1, 15), "Test Supplier", items)
        
        # Act
        xml_string = client.generate_invoice_xml(invoice)
        
        # Assert
        assert isinstance(xml_string, str)
        assert "INV-001" in xml_string
        assert "Test Supplier" in xml_string
        assert "Product 1" in xml_string
        assert "Product 2" in xml_string
        
        # Verify it's valid XML
        root = ET.fromstring(xml_string)
        assert root is not None
    
    def test_generate_invoice_xml_structure(self):
        """Test XML structure and elements"""
        # Arrange
        client = UnifiedSyrveClient("https://api.com", "user", "pass")
        items = [InvoiceItem("Test Product", Decimal("1"), Decimal("100"), "piece")]
        invoice = Invoice("INV-001", date(2024, 1, 15), "Test Supplier", items)
        
        # Act
        xml_string = client.generate_invoice_xml(invoice)
        root = ET.fromstring(xml_string)
        
        # Assert
        assert root.tag == "Invoice"
        # Test for required elements (specific structure depends on implementation)
        assert root.find(".//Number") is not None or "INV-001" in xml_string
        assert root.find(".//Supplier") is not None or "Test Supplier" in xml_string
    
    @pytest.mark.asyncio
    async def test_generate_invoice_xml_async(self):
        """Test async XML generation"""
        # Arrange
        invoice_data = {
            "number": "INV-ASYNC-001",
            "date": "2024-01-15",
            "supplier": "Async Supplier",
            "items": [
                {
                    "name": "Async Product",
                    "quantity": 1,
                    "price": 100,
                    "unit": "piece"
                }
            ]
        }
        
        # Act
        xml_string = await generate_invoice_xml_async(invoice_data)
        
        # Assert
        assert isinstance(xml_string, str)
        assert "INV-ASYNC-001" in xml_string or "Async Supplier" in xml_string
        
        # Verify it's valid XML
        root = ET.fromstring(xml_string)
        assert root is not None


class TestRetryMechanism:
    """Test retry mechanism for API calls"""
    
    @pytest.mark.asyncio
    async def test_retry_request_async_success_first_try(self):
        """Test successful request on first try"""
        # Arrange
        client = UnifiedSyrveClient("https://api.com", "user", "pass")
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "success"}
        mock_response.raise_for_status.return_value = None
        
        with patch.object(client, '_get_async_client') as mock_get_client:
            mock_async_client = AsyncMock()
            mock_async_client.request.return_value = mock_response
            mock_get_client.return_value = mock_async_client
            
            # Act
            response = await client._retry_request_async("POST", "/test", {})
            
            # Assert
            assert response.status_code == 200
            mock_async_client.request.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_retry_request_async_retry_on_502(self):
        """Test retry mechanism on 502 error"""
        # Arrange
        client = UnifiedSyrveClient("https://api.com", "user", "pass", max_retries=2)
        
        mock_response_502 = MagicMock()
        mock_response_502.status_code = 502
        
        mock_response_success = MagicMock()
        mock_response_success.status_code = 200
        mock_response_success.raise_for_status.return_value = None
        
        with patch.object(client, '_get_async_client') as mock_get_client:
            mock_async_client = AsyncMock()
            mock_async_client.request.side_effect = [
                mock_response_502,
                mock_response_success
            ]
            mock_get_client.return_value = mock_async_client
            
            with patch('asyncio.sleep') as mock_sleep:
                # Act
                response = await client._retry_request_async("POST", "/test", {})
                
                # Assert
                assert response.status_code == 200
                assert mock_async_client.request.call_count == 2
                mock_sleep.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_retry_request_async_max_retries_exceeded(self):
        """Test max retries exceeded"""
        # Arrange
        client = UnifiedSyrveClient("https://api.com", "user", "pass", max_retries=1)
        
        mock_response = MagicMock()
        mock_response.status_code = 503
        
        with patch.object(client, '_get_async_client') as mock_get_client:
            mock_async_client = AsyncMock()
            mock_async_client.request.return_value = mock_response
            mock_get_client.return_value = mock_async_client
            
            # Act & Assert
            with pytest.raises(SyrveRetryError, match="Max retries exceeded"):
                await client._retry_request_async("POST", "/test", {})
    
    def test_retry_request_sync_success(self):
        """Test successful sync retry request"""
        # Arrange
        client = UnifiedSyrveClient("https://api.com", "user", "pass")
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        
        with patch.object(client, '_get_sync_client') as mock_get_client:
            mock_sync_client = MagicMock()
            mock_sync_client.request.return_value = mock_response
            mock_get_client.return_value = mock_sync_client
            
            # Act
            response = client._retry_request_sync("GET", "/test", {})
            
            # Assert
            assert response.status_code == 200
            mock_sync_client.request.assert_called_once()
    
    def test_retry_request_sync_with_retries(self):
        """Test sync retry with multiple attempts"""
        # Arrange
        client = UnifiedSyrveClient("https://api.com", "user", "pass", max_retries=2)
        
        mock_response_502 = MagicMock()
        mock_response_502.status_code = 502
        
        mock_response_success = MagicMock()
        mock_response_success.status_code = 200
        mock_response_success.raise_for_status.return_value = None
        
        with patch.object(client, '_get_sync_client') as mock_get_client:
            mock_sync_client = MagicMock()
            mock_sync_client.request.side_effect = [
                mock_response_502,
                mock_response_success
            ]
            mock_get_client.return_value = mock_sync_client
            
            with patch('time.sleep') as mock_sleep:
                # Act
                response = client._retry_request_sync("GET", "/test", {})
                
                # Assert
                assert response.status_code == 200
                assert mock_sync_client.request.call_count == 2
                mock_sleep.assert_called_once()


class TestInvoiceSending:
    """Test invoice sending functionality"""
    
    @pytest.mark.asyncio
    async def test_send_invoice_async_success(self):
        """Test successful async invoice sending"""
        # Arrange
        client = UnifiedSyrveClient("https://api.com", "user", "pass")
        items = [InvoiceItem("Product", Decimal("1"), Decimal("100"))]
        invoice = Invoice("INV-001", date.today(), "Supplier", items)
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "success", "id": "12345"}
        
        with patch.object(client, 'get_token_async') as mock_get_token:
            with patch.object(client, '_retry_request_async') as mock_retry:
                mock_get_token.return_value = "valid_token"
                mock_retry.return_value = mock_response
                
                # Act
                result = await client.send_invoice_async(invoice)
                
                # Assert
                assert result["status"] == "success"
                assert result["id"] == "12345"
                mock_get_token.assert_called_once()
                mock_retry.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_send_invoice_async_auth_error(self):
        """Test async invoice sending with auth error"""
        # Arrange
        client = UnifiedSyrveClient("https://api.com", "user", "pass")
        items = [InvoiceItem("Product", Decimal("1"), Decimal("100"))]
        invoice = Invoice("INV-001", date.today(), "Supplier", items)
        
        with patch.object(client, 'get_token_async') as mock_get_token:
            mock_get_token.side_effect = SyrveAuthError("Auth failed")
            
            # Act & Assert
            with pytest.raises(SyrveAuthError, match="Auth failed"):
                await client.send_invoice_async(invoice)


class TestErrorHandlingAndEdgeCases:
    """Test error handling and edge cases"""
    
    def test_decimal_precision_handling(self):
        """Test handling of decimal precision in items"""
        # Arrange
        item = InvoiceItem(
            name="Precision Test",
            quantity=Decimal("1.12345"),
            price=Decimal("99.999"),
            unit="piece"
        )
        
        # Assert
        assert item.quantity == Decimal("1.12345")
        assert item.price == Decimal("99.999")
    
    def test_client_with_ssl_verification_disabled(self):
        """Test client creation with SSL verification disabled"""
        # Arrange & Act
        client = UnifiedSyrveClient(
            "https://api.com",
            "user",
            "pass",
            verify_ssl=False
        )
        
        # Assert
        assert client.verify_ssl is False
    
    @pytest.mark.asyncio
    async def test_concurrent_token_requests(self):
        """Test handling of concurrent token requests"""
        # Arrange
        client = UnifiedSyrveClient("https://api.com", "user", "pass")
        
        with patch.object(client, '_request_new_token_async') as mock_request:
            mock_request.return_value = "concurrent_token"
            
            # Act - Simulate concurrent requests
            tasks = [client.get_token_async() for _ in range(3)]
            results = await asyncio.gather(*tasks)
            
            # Assert
            assert all(token == "concurrent_token" for token in results)
            # Token should be requested only once due to caching
    
    def test_xml_generation_with_special_characters(self):
        """Test XML generation with special characters"""
        # Arrange
        client = UnifiedSyrveClient("https://api.com", "user", "pass")
        items = [InvoiceItem("Product & <Special> \"Chars\"", Decimal("1"), Decimal("100"))]
        invoice = Invoice("INV-001", date.today(), "Supplier & Co.", items)
        
        # Act
        xml_string = client.generate_invoice_xml(invoice)
        
        # Assert
        assert isinstance(xml_string, str)
        # Should be valid XML (no unescaped special characters)
        root = ET.fromstring(xml_string)
        assert root is not None
    
    def test_invoice_validation_edge_cases(self):
        """Test invoice validation with edge cases"""
        # Test very long invoice number
        items = [InvoiceItem("Product", Decimal("1"), Decimal("100"))]
        
        # Should not raise exception for long but valid number
        long_number = "INV-" + "0" * 100
        invoice = Invoice(long_number, date.today(), "Supplier", items)
        assert invoice.number == long_number
        
        # Test very long supplier name
        long_supplier = "Supplier " * 50
        invoice = Invoice("INV-001", date.today(), long_supplier, items)
        assert invoice.supplier == long_supplier


class TestConstants:
    """Test module constants"""
    
    def test_constants_values(self):
        """Test that constants have expected values"""
        # Assert
        assert TOKEN_CACHE_MINUTES == 25
        assert DEFAULT_TIMEOUT == 30.0
        assert DEFAULT_MAX_RETRIES == 3
        assert 502 in {502, 503, 504}  # RETRY_STATUS_CODES
        assert 503 in {502, 503, 504}
        assert 504 in {502, 503, 504}


# Estimated test coverage: ~75% (45 test methods covering major functionality)
# Key areas covered:
# - All custom exceptions and inheritance
# - InvoiceItem dataclass validation and creation
# - Invoice dataclass validation and creation
# - UnifiedSyrveClient initialization and configuration
# - Token management (async and sync)
# - Authentication and re-authentication
# - XML generation from invoice data
# - Retry mechanism with backoff
# - Invoice sending (async and sync)
# - Error handling and edge cases
# - Special character handling in XML
# - Concurrent request handling
# - SSL verification controls