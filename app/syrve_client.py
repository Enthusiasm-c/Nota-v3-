"""
Syrve API client for Nota AI.
Provides integration with Syrve restaurant management system.
"""

import hashlib
import httpx
import json
import logging
import xml.etree.ElementTree as ET
from typing import Dict, List, Any
from pathlib import Path

from app.utils.api_decorators import with_retry_backoff
from app.utils.redis_cache import cache_get, cache_set

logger = logging.getLogger(__name__)

SYRVE_PROMPT_PATH = Path(__file__).parent / "assistants" / "prompts" / "syrve.md"

class SyrveClient:
    """
    Client for interacting with the Syrve API.
    
    Provides methods for:
    - Authentication
    - Retrieving suppliers
    - Importing invoices
    """

    def __init__(self, api_url: str, login: str, password: str, is_password_hashed: bool = False):
        """
        Initialize the Syrve client.
        Args:
            api_url: Base URL for the Syrve API (e.g., https://host:port)
            login: API login username
            password: API login password (plain text or SHA1 hash)
            is_password_hashed: Whether the password is already SHA1 hashed
        """
        self.api_url = api_url.rstrip('/')
        self.login = login
        self.password = password
        self.is_password_hashed = is_password_hashed
        self.timeout = 30  # Default timeout in seconds

    def _get_sha1_password(self) -> str:
        # Если пароль уже хешированный - возвращаем как есть
        if self.is_password_hashed:
            return self.password
        # Иначе хешируем
        return hashlib.sha1(self.password.encode("utf-8")).hexdigest()

    async def auth(self) -> str:
        """
        Authenticate with the Syrve API and get an access token.
        Returns:
            Access token string
        Raises:
            Exception: If authentication fails
        """
        # Check if there's a cached token
        cache_key = f"syrve:key:{self.login}"
        cached_token = cache_get(cache_key)
        if cached_token:
            logger.info("Using cached Syrve auth token")
            return cached_token
        
        # Try GET /resto/api/auth with params (login, pass)
        auth_url = f"{self.api_url}/resto/api/auth"
        pass_hash = self._get_sha1_password()
        params = {"login": self.login, "pass": pass_hash}
        try:
            # Используем verify=False для работы с самоподписанными сертификатами
            # и отключаем предупреждения о незащищенных запросах
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            
            async with httpx.AsyncClient(timeout=self.timeout, verify=False) as client:
                response = await client.get(auth_url, params=params)
                response.raise_for_status()
                token = response.text.strip()
                if not token:
                    raise ValueError("No auth token in response")
                logger.info("Successfully authenticated with Syrve API (GET /resto/api/auth)")
                # Cache the token (45 минут)
                cache_set(cache_key, token, ex=45*60)
                return token
        except httpx.HTTPStatusError as e:
            if e.response.status_code in [404, 405, 501, 400]:
                logger.info("GET /resto/api/auth failed, trying POST")
            else:
                logger.error(f"GET /resto/api/auth failed with status {e.response.status_code}: {e.response.text}")
                raise
        except Exception as e:
            logger.error(f"GET /resto/api/auth failed: {str(e)}")
        
        # Try POST /resto/api/auth with Content-Type: application/x-www-form-urlencoded
        try:
            # Повторно отключаем предупреждения о SSL для этого запроса
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            
            async with httpx.AsyncClient(timeout=self.timeout, verify=False) as client:
                response = await client.post(
                    auth_url,
                    data=params,
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                )
                response.raise_for_status()
                token = response.text.strip()
                if not token:
                    raise ValueError("No auth token in response")
                logger.info("Successfully authenticated with Syrve API (POST /resto/api/auth)")
                # Cache the token (45 минут)
                cache_set(cache_key, token, ex=45*60)
                return token
        except httpx.HTTPStatusError as e:
            logger.error(f"POST /resto/api/auth failed with status {e.response.status_code}: {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"POST /resto/api/auth failed: {str(e)}")
            raise Exception("Both GET and POST authentication methods failed")

    async def logout(self, key: str) -> None:
        """
        Log out from the Syrve API.
        Args:
            key: Auth token to invalidate
        Returns:
            None
        """
        logout_url = f"{self.api_url}/resto/api/logout"
        params = {"key": key}
        cache_key = f"syrve:key:{self.login}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout, verify=False) as client:
                response = await client.post(logout_url, params=params)
                response.raise_for_status()
                # Remove from cache only on success
                cache_set(cache_key, None)
                logger.info("Successfully logged out from Syrve API")
        except Exception as e:
            logger.warning(f"Syrve logout failed: {str(e)}")

    async def get_suppliers(self, key: str) -> List[Dict[str, Any]]:
        """
        Get list of suppliers from Syrve.
        Args:
            key: Auth token (string)
        Returns:
            List of supplier dictionaries
        """
        suppliers_url = f"{self.api_url}/resto/api/suppliers"
        try:
            async with httpx.AsyncClient(timeout=self.timeout, verify=False) as client:
                response = await client.get(
                    suppliers_url,
                    cookies={"key": key}
                )
                response.raise_for_status()
                # Try to parse response as JSON
                try:
                    return response.json()
                except json.JSONDecodeError:
                    # If not JSON, try to parse as XML
                    logger.info("Response is not JSON, trying to parse as XML")
                    xml_content = response.text
                    root = ET.fromstring(xml_content)
                    suppliers = []
                    # Assume structure: <suppliers><supplier>...</supplier>...</suppliers>
                    # Or another hierarchical XML structure
                    for supplier in root.findall('.//employee'):  # Assume suppliers are stored in 'employee' tags
                        supplier_dict = {}
                        for child in supplier:
                            supplier_dict[child.tag] = child.text
                        suppliers.append(supplier_dict)
                    return suppliers
        except Exception as e:
            logger.error(f"Failed to get suppliers: {str(e)}")
            raise

    @with_retry_backoff(max_retries=1, initial_backoff=1.0, backoff_factor=2.0)
    async def import_invoice(self, key: str, xml: str) -> Dict[str, Any]:
        """
        Import an invoice to Syrve.
        Args:
            key: Auth token
            xml: XML invoice data
        Returns:
            Response data from Syrve API with document number if available
        Raises:
            Exception: If the import fails
        """
        import_url = f"{self.api_url}/resto/api/documents/import/incomingInvoice"
        try:
            # Отключаем предупреждения о SSL
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            
            # Логируем для отладки
            logger.info(f"Sending invoice to Syrve: {import_url}")
            logger.debug(f"Invoice XML: {xml[:100]}...")
            
            async with httpx.AsyncClient(timeout=self.timeout, verify=False) as client:
                response = await client.post(
                    import_url,
                    params={"key": key},
                    content=xml,
                    headers={
                        "Content-Type": "application/xml"
                    }
                )
                
                # Проверяем ответ
                if response.status_code == 200:
                    try:
                        # Парсим XML ответа
                        import xml.etree.ElementTree as ET
                        root = ET.fromstring(response.text)
                        
                        # Проверяем успешность операции
                        is_valid = root.find(".//valid")
                        if is_valid is not None and is_valid.text.lower() == "true":
                            # Получаем номер документа из ответа
                            doc_number = None
                            doc_number_elem = root.find(".//documentNumber")
                            if doc_number_elem is not None:
                                doc_number = doc_number_elem.text
                            
                            logger.info("Invoice successfully imported to Syrve")
                            if doc_number:
                                logger.info(f"Assigned document number: {doc_number}")
                            
                            return {
                                "valid": True,
                                "document_number": doc_number
                            }
                        else:
                            # Получаем сообщение об ошибке
                            error_msg = "Unknown validation error"
                            error_elem = root.find(".//errorMessage")
                            if error_elem is not None and error_elem.text:
                                error_msg = error_elem.text
                            
                            logger.warning(f"Syrve validation error: {error_msg}")
                            return {
                                "valid": False,
                                "status": response.status_code,
                                "errorMessage": error_msg
                            }
                    except ET.ParseError as e:
                        logger.error(f"Failed to parse Syrve response XML: {str(e)}")
                        return {
                            "valid": False,
                            "status": response.status_code,
                            "errorMessage": f"Invalid XML response: {str(e)}"
                        }
                else:
                    logger.warning(f"Syrve returned non-200 status: {response.status_code}")
                    logger.warning(f"Response body: {response.text}")
                    return {
                        "valid": False,
                        "status": response.status_code,
                        "errorMessage": f"Syrve API Error: {response.text}"
                    }
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error during invoice import: {e.response.status_code} - {e.response.text}")
            return {
                "valid": False,
                "status": e.response.status_code,
                "errorMessage": f"HTTP error: {e.response.text}"
            }
        except Exception as e:
            logger.error(f"Invoice import failed: {str(e)}")
            return {
                "valid": False,
                "status": 500,
                "errorMessage": f"Internal error: {str(e)}"
            }

# Cache for Syrve prompt to avoid repeated file reads
_syrve_prompt_cache = ""

async def generate_invoice_xml(invoice_data: Dict[str, Any], openai_client) -> str:
    """
    Generate Syrve-compatible XML from invoice data directly, without using OpenAI.
    
    Args:
        invoice_data: Dictionary with invoice information
        openai_client: Not used, kept for compatibility
        
    Returns:
        XML string for Syrve
    """
    global _syrve_prompt_cache
    
    try:
        # Check required fields (без invoice_number, так как он теперь опционален)
        required_fields = ["invoice_date", "conception_id", "supplier_id", "store_id", "items"]
        missing_fields = [field for field in required_fields if not invoice_data.get(field)]
        
        if missing_fields:
            error_msg = f"Missing required fields: {', '.join(missing_fields)}"
            logger.error(error_msg)
            # Return basic XML with error info
            return f'<?xml version="1.0" encoding="UTF-8"?>\n<e>{error_msg}</e>'
        
        # Fix missing fields with defaults if needed
        if "conception_id" not in invoice_data or not invoice_data["conception_id"]:
            # Use the value we found earlier
            invoice_data["conception_id"] = "bf3c0590-b204-f634-e054-0017f63ab3e6"
            
        if "store_id" not in invoice_data or not invoice_data["store_id"]:
            # Use the value we found earlier
            invoice_data["store_id"] = "1239d270-1bbe-f64f-b7ea-5f00518ef508"
            
        if "supplier_id" not in invoice_data or not invoice_data["supplier_id"]:
            # Use a default supplier from our tests
            invoice_data["supplier_id"] = "61c65f89-d940-4153-8c07-488188e16d50"
        
        # Start generating XML
        xml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        xml += '<document>\n'
        
        # Add items section
        xml += '  <items>\n'
        for idx, item in enumerate(invoice_data.get("items", []), 1):
            product_id = item.get("product_id")
            quantity = item.get("quantity", 0)
            price = item.get("price", 0)
            
            # Calculate sum
            item_sum = quantity * price
            
            xml += '    <item>\n'
            xml += f'      <num>{idx}</num>\n'
            xml += f'      <product>{product_id}</product>\n'
            xml += f'      <amount>{quantity:.2f}</amount>\n'
            xml += f'      <price>{price:.2f}</price>\n'
            xml += f'      <sum>{item_sum:.2f}</sum>\n'
            xml += f'      <store>{invoice_data["store_id"]}</store>\n'
            xml += '    </item>\n'
        xml += '  </items>\n'
        
        # Add other required elements
        xml += f'  <supplier>{invoice_data["supplier_id"]}</supplier>\n'
        xml += f'  <defaultStore>{invoice_data["store_id"]}</defaultStore>\n'
        
        # Add optional elements if present
        if invoice_data.get("invoice_date"):
            xml += f'  <dateIncoming>{invoice_data["invoice_date"]}T08:00:00</dateIncoming>\n'
            
        # Close document tag
        xml += '</document>'
        
        logger.info("Successfully generated Syrve XML")
        return xml
    
    except Exception as e:
        logger.error(f"Failed to generate Syrve XML: {str(e)}")
        raise