"""
Syrve API client for Nota AI.
Provides integration with Syrve restaurant management system.
"""

import hashlib
import httpx
import json
import logging
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Any, Union
from pathlib import Path
from typing import Dict, Any, List

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

    def __init__(self, api_url: str, login: str, password: str):
        """
        Initialize the Syrve client.
        Args:
            api_url: Base URL for the Syrve API (e.g., https://host:port)
            login: API login username
            password: API login password (plain text)
        """
        self.api_url = api_url.rstrip('/')
        self.login = login
        self.password = password
        self.timeout = 30  # Default timeout in seconds

    def _get_sha1_password(self) -> str:
        # Syrve Resto API: для данной конфигурации используем sha1(password) без префикса
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
            Response data from Syrve API
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
                    logger.info("Invoice successfully imported to Syrve")
                    return {"response": response.text, "valid": True}
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
    Generate Syrve-compatible XML from invoice data using OpenAI.
    
    Args:
        invoice_data: Dictionary with invoice information
        openai_client: OpenAI client instance
        
    Returns:
        XML string for Syrve
    """
    global _syrve_prompt_cache
    
    try:
        # Read the prompt template from cache or file
        if not _syrve_prompt_cache:
            try:
                with open(SYRVE_PROMPT_PATH, "r", encoding="utf-8") as f:
                    _syrve_prompt_cache = f.read()
                    logger.debug("Loaded Syrve prompt from file")
            except Exception as e:
                logger.error(f"Error loading Syrve prompt: {e}")
                _syrve_prompt_cache = "Generate a valid Syrve XML document for the provided invoice data."
        
        # Convert invoice data to JSON string with custom serialization for date objects
        def json_serial(obj):
            """Custom serializer for objects not serializable by default json module"""
            if hasattr(obj, 'isoformat'):
                # Handle date, datetime, and time objects
                return obj.isoformat()
            raise TypeError(f"Type {type(obj)} not serializable")
        
        # Use custom serializer for invoice data
        invoice_json = json.dumps(invoice_data, indent=2, default=json_serial)
        
        # Create messages for the API call
        messages = [
            {"role": "system", "content": _syrve_prompt_cache},
            {"role": "user", "content": f"Generate Syrve XML for this invoice:\n\n```json\n{invoice_json}\n```"}
        ]
        
        # Call OpenAI API with optimized parameters
        response = await openai_client.chat.completions.create(
            model="gpt-4o",  # Using the latest model for best results
            messages=messages,
            temperature=0.1,  # Low temperature for deterministic output
            max_tokens=1500,  # Limit token usage
            timeout=45.0     # Set explicit timeout
        )
        
        # Extract XML from response
        xml_content = response.choices[0].message.content.strip()
        
        # Remove code block markers if present
        if xml_content.startswith("```xml"):
            xml_content = xml_content.split("```xml", 1)[1]
        elif xml_content.startswith("```"):
            xml_content = xml_content.split("```", 1)[1]
            
        if xml_content.endswith("```"):
            xml_content = xml_content.rsplit("```", 1)[0]
            
        xml_content = xml_content.strip()
        
        # Validate basic XML structure
        if not xml_content.startswith("<?xml") and not xml_content.startswith("<"):
            logger.warning("Generated XML is missing XML declaration or root element")
            # Try to fix by adding XML declaration
            xml_content = f"<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n{xml_content}"
        
        logger.info("Successfully generated Syrve XML")
        return xml_content
    
    except Exception as e:
        logger.error(f"Failed to generate Syrve XML: {str(e)}")
        raise