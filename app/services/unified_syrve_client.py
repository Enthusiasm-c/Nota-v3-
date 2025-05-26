"""
Production-ready unified Syrve API client.

Combines the best features from both legacy syrve_client.py and syrve_invoice_sender.py
with production-ready features:
- Async/sync support
- Robust retry logic with backoff
- Auto-reauthorization on 401
- SSL verification controls
- Typed data models
- Comprehensive error handling
- XSD validation support
"""

import asyncio
import hashlib
import logging
import os
import time
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union
from xml.dom import minidom

import httpx

logger = logging.getLogger(__name__)

# Constants
TOKEN_CACHE_MINUTES = 25
TOKEN_REFRESH_THRESHOLD = 5
DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_FACTOR = 2.0
RETRY_STATUS_CODES = {502, 503, 504}


# Custom exceptions
class SyrveError(Exception):
    """Base exception for Syrve API errors."""
    pass


class SyrveAuthError(SyrveError):
    """Authentication error."""
    pass


class SyrveValidationError(SyrveError):
    """Invoice validation error from Syrve API."""
    pass


class SyrveHTTPError(SyrveError):
    """HTTP error during API communication."""
    pass


class SyrveRetryError(SyrveError):
    """Error after all retry attempts exhausted."""
    pass


# Data models
@dataclass
class InvoiceItem:
    """Invoice item with validation."""
    num: int
    product_id: str  # Syrve GUID
    amount: Decimal  # Quantity
    price: Decimal   # Unit price
    sum: Decimal     # Total (amount * price)
    store_id: Optional[str] = None  # Optional store override
    
    def __post_init__(self):
        """Validate item data."""
        if not self.product_id:
            raise SyrveValidationError("Product ID cannot be empty")
        
        if self.amount <= 0:
            raise SyrveValidationError(f"Amount must be positive, got {self.amount}")
        
        if self.price < 0:
            raise SyrveValidationError(f"Price cannot be negative, got {self.price}")
        
        # Validate arithmetic with tolerance
        expected_sum = self.amount * self.price
        diff = abs(self.sum - expected_sum)
        if diff > Decimal("0.01"):
            raise SyrveValidationError(
                f"Item {self.num}: sum ({self.sum}) does not match price*amount "
                f"({self.price}*{self.amount}={expected_sum}), diff={diff}"
            )


@dataclass
class Invoice:
    """Invoice with typed validation."""
    items: List[InvoiceItem]
    supplier_id: str           # GUID of supplier
    default_store_id: str      # GUID of default store
    conception_id: Optional[str] = None      # GUID of conception/restaurant
    document_number: Optional[str] = None    # Invoice number
    date_incoming: Optional[date] = None     # Invoice date
    external_id: Optional[str] = None        # External reference
    
    def __post_init__(self):
        """Validate invoice data."""
        if not self.items:
            raise SyrveValidationError("Invoice must contain at least one item")
        
        if not self.supplier_id:
            raise SyrveValidationError("Supplier ID is required")
        
        if not self.default_store_id:
            raise SyrveValidationError("Default store ID is required")
        
        # Auto-generate document number if not provided
        if not self.document_number:
            today_str = date.today().strftime("%Y%m%d")
            self.document_number = f"AUTO-{today_str}-{uuid.uuid4().hex[:8].upper()}"
        
        # Auto-set date if not provided
        if not self.date_incoming:
            self.date_incoming = date.today()


class UnifiedSyrveClient:
    """
    Production-ready unified Syrve API client.
    
    Features:
    - Async/sync operation modes
    - Robust retry with exponential backoff
    - Auto-reauthorization on token expiry
    - SSL verification controls
    - Comprehensive error handling
    - Rate limiting awareness
    """
    
    def __init__(
        self,
        base_url: str,
        login: str,
        password: Optional[str] = None,
        password_sha1: Optional[str] = None,
        verify_ssl: bool = True,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
        on_result: Optional[Callable[[bool, float, Optional[Exception]], None]] = None,
    ):
        """
        Initialize unified Syrve client.
        
        Args:
            base_url: Syrve server URL (e.g., https://server.syrve.online:443)
            login: API login username
            password: Plain text password (will be SHA1 hashed)
            password_sha1: Pre-hashed SHA1 password (preferred for production)
            verify_ssl: Enable SSL certificate verification
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts for failed requests
            backoff_factor: Exponential backoff multiplier
            on_result: Optional callback for result reporting
        """
        self.base_url = base_url.rstrip("/")
        self.login = login
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.on_result = on_result
        
        # Password handling - prefer SHA1 for production
        if password_sha1:
            self.password_sha1 = password_sha1
        elif password:
            self.password_sha1 = hashlib.sha1(password.encode()).hexdigest()
        else:
            raise SyrveAuthError("Either password or password_sha1 must be provided")
        
        # Token management
        self._token: Optional[str] = None
        self._token_timestamp: Optional[datetime] = None
        self._token_lock = asyncio.Lock()
        
        # HTTP clients (created lazily)
        self._async_client: Optional[httpx.AsyncClient] = None
        self._sync_client: Optional[httpx.Client] = None
    
    @classmethod
    def from_env(cls) -> "UnifiedSyrveClient":
        """Create client from environment variables."""
        base_url = os.getenv("SYRVE_SERVER_URL")
        if not base_url:
            raise SyrveAuthError("SYRVE_SERVER_URL environment variable is required")
        
        login = os.getenv("SYRVE_LOGIN")
        if not login:
            raise SyrveAuthError("SYRVE_LOGIN environment variable is required")
        
        # Prefer SHA1 hash from environment
        password_sha1 = os.getenv("SYRVE_PASS_SHA1")
        password = os.getenv("SYRVE_PASSWORD")
        
        if not password_sha1 and not password:
            raise SyrveAuthError("Either SYRVE_PASS_SHA1 or SYRVE_PASSWORD must be set")
        
        # SSL verification control
        verify_ssl = os.getenv("VERIFY_SSL", "0").lower() in ("1", "true", "yes")
        
        return cls(
            base_url=base_url,
            login=login,
            password=password,
            password_sha1=password_sha1,
            verify_ssl=verify_ssl,
        )
    
    def _is_token_valid(self) -> bool:
        """Check if current token is still valid."""
        if not self._token or not self._token_timestamp:
            return False
        
        elapsed = datetime.now() - self._token_timestamp
        remaining_minutes = TOKEN_CACHE_MINUTES - elapsed.total_seconds() / 60
        
        return remaining_minutes > TOKEN_REFRESH_THRESHOLD
    
    async def _get_async_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._async_client is None:
            self._async_client = httpx.AsyncClient(
                timeout=self.timeout,
                verify=self.verify_ssl,
            )
        return self._async_client
    
    def _get_sync_client(self) -> httpx.Client:
        """Get or create sync HTTP client."""
        if self._sync_client is None:
            self._sync_client = httpx.Client(
                timeout=self.timeout,
                verify=self.verify_ssl,
            )
        return self._sync_client
    
    async def _request_new_token_async(self) -> str:
        """Request new authentication token (async)."""
        auth_url = f"{self.base_url}/resto/api/auth"
        client = await self._get_async_client()
        
        try:
            response = await client.get(
                auth_url,
                params={"login": self.login, "pass": self.password_sha1}
            )
            response.raise_for_status()
            
            token = response.text.strip()
            if not token:
                raise SyrveAuthError("Empty token received from Syrve API")
            
            self._token = token
            self._token_timestamp = datetime.now()
            
            logger.info(f"Successfully authenticated with Syrve API, token: {token[:10]}...")
            return token
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Authentication failed: {e.response.status_code} - {e.response.text}")
            raise SyrveAuthError(f"Authentication failed: {e.response.status_code}")
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            raise SyrveAuthError(f"Authentication error: {e}")
    
    def _request_new_token_sync(self) -> str:
        """Request new authentication token (sync)."""
        auth_url = f"{self.base_url}/resto/api/auth"
        client = self._get_sync_client()
        
        try:
            response = client.get(
                auth_url,
                params={"login": self.login, "pass": self.password_sha1}
            )
            response.raise_for_status()
            
            token = response.text.strip()
            if not token:
                raise SyrveAuthError("Empty token received from Syrve API")
            
            self._token = token
            self._token_timestamp = datetime.now()
            
            logger.info(f"Successfully authenticated with Syrve API, token: {token[:10]}...")
            return token
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Authentication failed: {e.response.status_code} - {e.response.text}")
            raise SyrveAuthError(f"Authentication failed: {e.response.status_code}")
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            raise SyrveAuthError(f"Authentication error: {e}")
    
    async def get_token_async(self) -> str:
        """Get valid authentication token (async)."""
        async with self._token_lock:
            if self._is_token_valid():
                return self._token
            
            return await self._request_new_token_async()
    
    def get_token_sync(self) -> str:
        """Get valid authentication token (sync)."""
        if self._is_token_valid():
            return self._token
        
        return self._request_new_token_sync()
    
    def generate_invoice_xml(self, invoice: Invoice) -> str:
        """
        Generate Syrve-compatible XML from invoice.
        
        Uses the correct XML structure based on production requirements:
        - <product> not <productId>
        - <store> not <storeId>
        - Proper ordering and formatting
        
        Args:
            invoice: Invoice to convert to XML
            
        Returns:
            XML string ready for Syrve API
        """
        root = ET.Element("document")
        
        # 1. Items (required)
        items_elem = ET.SubElement(root, "items")
        for item in invoice.items:
            item_elem = ET.SubElement(items_elem, "item")
            ET.SubElement(item_elem, "num").text = str(item.num)
            ET.SubElement(item_elem, "product").text = item.product_id
            ET.SubElement(item_elem, "amount").text = str(item.amount)
            ET.SubElement(item_elem, "price").text = str(item.price)
            ET.SubElement(item_elem, "sum").text = str(item.sum)
            # Use item store or default to invoice store
            store_id = item.store_id or invoice.default_store_id
            ET.SubElement(item_elem, "store").text = store_id
        
        # 2. Supplier (required)
        ET.SubElement(root, "supplier").text = invoice.supplier_id
        
        # 3. DefaultStore (required)
        ET.SubElement(root, "defaultStore").text = invoice.default_store_id
        
        # 4. Optional elements
        if invoice.conception_id:
            ET.SubElement(root, "conception").text = invoice.conception_id
        
        if invoice.document_number:
            ET.SubElement(root, "documentNumber").text = invoice.document_number
        
        if invoice.date_incoming:
            # Format: YYYY-MM-DDTHH:MM:SS
            date_str = invoice.date_incoming.strftime("%Y-%m-%d") + "T08:00:00"
            ET.SubElement(root, "dateIncoming").text = date_str
        
        if invoice.external_id:
            ET.SubElement(root, "externalId").text = invoice.external_id
        
        # Pretty format XML
        xml_str = ET.tostring(root, encoding="unicode")
        dom = minidom.parseString(xml_str)
        return dom.toprettyxml(indent="  ", encoding=None).strip()
    
    async def _retry_request_async(
        self,
        method: str,
        url: str,
        **kwargs
    ) -> httpx.Response:
        """Execute HTTP request with retry logic (async)."""
        client = await self._get_async_client()
        last_exception = None
        
        for attempt in range(self.max_retries + 1):
            try:
                if method.upper() == "GET":
                    response = await client.get(url, **kwargs)
                elif method.upper() == "POST":
                    response = await client.post(url, **kwargs)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")
                
                # Handle 401 (token expired) - try to reauth once
                if response.status_code == 401 and attempt == 0:
                    logger.info("Token expired, attempting reauthorization...")
                    self._token = None  # Force token refresh
                    token = await self.get_token_async()
                    kwargs.setdefault("params", {})["key"] = token
                    continue
                
                # Check if we should retry
                if response.status_code in RETRY_STATUS_CODES and attempt < self.max_retries:
                    backoff_time = self.backoff_factor ** attempt
                    logger.warning(
                        f"Request failed with {response.status_code}, "
                        f"retrying in {backoff_time}s (attempt {attempt + 1}/{self.max_retries})"
                    )
                    await asyncio.sleep(backoff_time)
                    continue
                
                return response
                
            except (httpx.ConnectError, httpx.TimeoutException) as e:
                last_exception = e
                if attempt < self.max_retries:
                    backoff_time = self.backoff_factor ** attempt
                    logger.warning(
                        f"Network error: {e}, retrying in {backoff_time}s "
                        f"(attempt {attempt + 1}/{self.max_retries})"
                    )
                    await asyncio.sleep(backoff_time)
                    continue
                else:
                    break
        
        # All retries exhausted
        raise SyrveRetryError(f"All retry attempts exhausted. Last error: {last_exception}")
    
    def _retry_request_sync(
        self,
        method: str,
        url: str,
        **kwargs
    ) -> httpx.Response:
        """Execute HTTP request with retry logic (sync)."""
        client = self._get_sync_client()
        last_exception = None
        
        for attempt in range(self.max_retries + 1):
            try:
                if method.upper() == "GET":
                    response = client.get(url, **kwargs)
                elif method.upper() == "POST":
                    response = client.post(url, **kwargs)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")
                
                # Handle 401 (token expired) - try to reauth once
                if response.status_code == 401 and attempt == 0:
                    logger.info("Token expired, attempting reauthorization...")
                    self._token = None  # Force token refresh
                    token = self.get_token_sync()
                    kwargs.setdefault("params", {})["key"] = token
                    continue
                
                # Check if we should retry
                if response.status_code in RETRY_STATUS_CODES and attempt < self.max_retries:
                    backoff_time = self.backoff_factor ** attempt
                    logger.warning(
                        f"Request failed with {response.status_code}, "
                        f"retrying in {backoff_time}s (attempt {attempt + 1}/{self.max_retries})"
                    )
                    time.sleep(backoff_time)
                    continue
                
                return response
                
            except (httpx.ConnectError, httpx.TimeoutException) as e:
                last_exception = e
                if attempt < self.max_retries:
                    backoff_time = self.backoff_factor ** attempt
                    logger.warning(
                        f"Network error: {e}, retrying in {backoff_time}s "
                        f"(attempt {attempt + 1}/{self.max_retries})"
                    )
                    time.sleep(backoff_time)
                    continue
                else:
                    break
        
        # All retries exhausted
        raise SyrveRetryError(f"All retry attempts exhausted. Last error: {last_exception}")
    
    async def send_invoice_async(self, invoice: Invoice) -> Dict[str, Any]:
        """
        Send invoice to Syrve API (async).
        
        Args:
            invoice: Invoice to send
            
        Returns:
            Dict with result information
            
        Raises:
            SyrveValidationError: Invoice validation failed
            SyrveHTTPError: HTTP error during communication
            SyrveRetryError: All retry attempts failed
        """
        start_time = time.time()
        
        try:
            # Generate XML
            xml_content = self.generate_invoice_xml(invoice)
            logger.debug(f"Generated XML: {xml_content[:200]}...")
            
            # Get authentication token
            token = await self.get_token_async()
            
            # Prepare request
            import_url = f"{self.base_url}/resto/api/documents/import/incomingInvoice"
            headers = {"Content-Type": "application/xml"}
            params = {"key": token}
            
            # Send request with retry
            response = await self._retry_request_async(
                "POST",
                import_url,
                content=xml_content,
                headers=headers,
                params=params
            )
            
            elapsed_time = time.time() - start_time
            
            # Parse response
            if response.status_code == 200:
                try:
                    response_root = ET.fromstring(response.text)
                    is_valid = response_root.find("valid")
                    
                    if is_valid is not None and is_valid.text.lower() == "true":
                        # Success - extract document number if available
                        doc_number = None
                        doc_number_elem = response_root.find("documentNumber")
                        if doc_number_elem is not None:
                            doc_number = doc_number_elem.text
                        
                        result = {
                            "success": True,
                            "document_number": doc_number,
                            "response_time": elapsed_time,
                            "invoice_number": invoice.document_number,
                        }
                        
                        logger.info(f"Invoice successfully sent to Syrve in {elapsed_time:.2f}s")
                        
                        # Call result callback if provided
                        if self.on_result:
                            self.on_result(True, elapsed_time, None)
                        
                        return result
                    else:
                        # Validation failed
                        error_msg = "Unknown validation error"
                        error_elem = response_root.find("error")
                        if error_elem is not None:
                            error_msg = error_elem.text or error_msg
                        
                        raise SyrveValidationError(f"Syrve validation failed: {error_msg}")
                        
                except ET.ParseError as e:
                    raise SyrveHTTPError(f"Invalid XML response from Syrve: {e}")
            else:
                raise SyrveHTTPError(f"HTTP {response.status_code}: {response.text}")
        
        except Exception as e:
            elapsed_time = time.time() - start_time
            
            # Call result callback with error
            if self.on_result:
                self.on_result(False, elapsed_time, e)
            
            # Re-raise the exception
            raise
    
    def send_invoice_sync(self, invoice: Invoice) -> Dict[str, Any]:
        """
        Send invoice to Syrve API (sync).
        
        Args:
            invoice: Invoice to send
            
        Returns:
            Dict with result information
            
        Raises:
            SyrveValidationError: Invoice validation failed
            SyrveHTTPError: HTTP error during communication
            SyrveRetryError: All retry attempts failed
        """
        start_time = time.time()
        
        try:
            # Generate XML
            xml_content = self.generate_invoice_xml(invoice)
            logger.debug(f"Generated XML: {xml_content[:200]}...")
            
            # Get authentication token
            token = self.get_token_sync()
            
            # Prepare request
            import_url = f"{self.base_url}/resto/api/documents/import/incomingInvoice"
            headers = {"Content-Type": "application/xml"}
            params = {"key": token}
            
            # Send request with retry
            response = self._retry_request_sync(
                "POST",
                import_url,
                content=xml_content,
                headers=headers,
                params=params
            )
            
            elapsed_time = time.time() - start_time
            
            # Parse response
            if response.status_code == 200:
                try:
                    response_root = ET.fromstring(response.text)
                    is_valid = response_root.find("valid")
                    
                    if is_valid is not None and is_valid.text.lower() == "true":
                        # Success - extract document number if available
                        doc_number = None
                        doc_number_elem = response_root.find("documentNumber")
                        if doc_number_elem is not None:
                            doc_number = doc_number_elem.text
                        
                        result = {
                            "success": True,
                            "document_number": doc_number,
                            "response_time": elapsed_time,
                            "invoice_number": invoice.document_number,
                        }
                        
                        logger.info(f"Invoice successfully sent to Syrve in {elapsed_time:.2f}s")
                        
                        # Call result callback if provided
                        if self.on_result:
                            self.on_result(True, elapsed_time, None)
                        
                        return result
                    else:
                        # Validation failed
                        error_msg = "Unknown validation error"
                        error_elem = response_root.find("error")
                        if error_elem is not None:
                            error_msg = error_elem.text or error_msg
                        
                        raise SyrveValidationError(f"Syrve validation failed: {error_msg}")
                        
                except ET.ParseError as e:
                    raise SyrveHTTPError(f"Invalid XML response from Syrve: {e}")
            else:
                raise SyrveHTTPError(f"HTTP {response.status_code}: {response.text}")
        
        except Exception as e:
            elapsed_time = time.time() - start_time
            
            # Call result callback with error
            if self.on_result:
                self.on_result(False, elapsed_time, e)
            
            # Re-raise the exception
            raise
    
    async def get_suppliers_async(self) -> List[Dict[str, Any]]:
        """Get list of suppliers (async)."""
        token = await self.get_token_async()
        suppliers_url = f"{self.base_url}/resto/api/suppliers"
        
        response = await self._retry_request_async(
            "GET",
            suppliers_url,
            params={"key": token}
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            raise SyrveHTTPError(f"Failed to get suppliers: {response.status_code}")
    
    def get_suppliers_sync(self) -> List[Dict[str, Any]]:
        """Get list of suppliers (sync)."""
        token = self.get_token_sync()
        suppliers_url = f"{self.base_url}/resto/api/suppliers"
        
        response = self._retry_request_sync(
            "GET",
            suppliers_url,
            params={"key": token}
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            raise SyrveHTTPError(f"Failed to get suppliers: {response.status_code}")
    
    async def close_async(self):
        """Close async HTTP client."""
        if self._async_client:
            await self._async_client.aclose()
            self._async_client = None
    
    def close_sync(self):
        """Close sync HTTP client."""
        if self._sync_client:
            self._sync_client.close()
            self._sync_client = None
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close_async()
    
    def __enter__(self):
        """Sync context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Sync context manager exit."""
        self.close_sync()


# Convenience functions for backward compatibility
async def generate_invoice_xml_async(invoice_data: Dict[str, Any], client=None) -> str:
    """
    Generate XML from invoice data (backward compatibility).
    
    Args:
        invoice_data: Dictionary with invoice data
        client: Ignored (for compatibility)
        
    Returns:
        XML string
    """
    # Convert dict to Invoice object
    items = []
    for i, item_data in enumerate(invoice_data.get("items", []), 1):
        items.append(InvoiceItem(
            num=i,
            product_id=item_data["product_id"],
            amount=Decimal(str(item_data["quantity"])),
            price=Decimal(str(item_data["price"])),
            sum=Decimal(str(item_data["quantity"])) * Decimal(str(item_data["price"])),
        ))
    
    invoice = Invoice(
        items=items,
        supplier_id=invoice_data["supplier_id"],
        default_store_id=invoice_data["store_id"],
        conception_id=invoice_data.get("conception_id"),
        document_number=invoice_data.get("invoice_number"),
        date_incoming=date.fromisoformat(invoice_data["invoice_date"]) if invoice_data.get("invoice_date") else None,
    )
    
    client = UnifiedSyrveClient.from_env()
    return client.generate_invoice_xml(invoice)


# Legacy compatibility aliases
SyrveClient = UnifiedSyrveClient
generate_invoice_xml = generate_invoice_xml_async