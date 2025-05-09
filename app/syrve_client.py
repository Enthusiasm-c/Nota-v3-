"""
Syrve API client for Nota AI.
Provides integration with Syrve restaurant management system.
"""

import logging
import httpx
import asyncio
import json
from typing import Dict, Any, Optional, List, Union
import uuid
from datetime import datetime
from pathlib import Path

from app.utils.redis_cache import cache_get, cache_set
from app.utils.api_decorators import with_retry_backoff

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
            api_url: Base URL for the Syrve API
            login: API login username
            password: API login password
        """
        self.api_url = api_url.rstrip('/')
        self.login = login
        self.password = password
        self.timeout = 30  # Default timeout in seconds
        
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
        
        # Authenticate and get a new token
        auth_url = f"{self.api_url}/api/auth/login"
        auth_data = {
            "login": self.login,
            "password": self.password
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(auth_url, json=auth_data)
                response.raise_for_status()
                data = response.json()
                token = data.get("key")
                
                if not token:
                    raise ValueError("No auth token in response")
                
                # Cache the token with a 45-minute TTL
                cache_set(cache_key, token, ex=45*60)
                logger.info("Successfully authenticated with Syrve API")
                return token
        except httpx.HTTPStatusError as e:
            logger.error(f"Syrve auth failed with status {e.response.status_code}: {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Syrve auth failed: {str(e)}")
            raise
    
    async def logout(self, key: str) -> None:
        """
        Log out from the Syrve API.
        
        Args:
            key: Auth token to invalidate
            
        Returns:
            None
        """
        logout_url = f"{self.api_url}/api/auth/logout"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    logout_url,
                    headers={"Authorization": f"Bearer {key}"}
                )
                response.raise_for_status()
                
                # Remove from cache
                cache_key = f"syrve:key:{self.login}"
                cache_get(cache_key, None)
                
                logger.info("Successfully logged out from Syrve API")
        except Exception as e:
            logger.warning(f"Syrve logout failed: {str(e)}")
    
    async def get_suppliers(self, key: str) -> List[Dict[str, Any]]:
        """
        Get list of suppliers from Syrve.
        
        Args:
            key: Auth token
            
        Returns:
            List of supplier dictionaries
        """
        suppliers_url = f"{self.api_url}/api/suppliers"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    suppliers_url,
                    headers={"Authorization": f"Bearer {key}"}
                )
                response.raise_for_status()
                suppliers = response.json()
                logger.info(f"Retrieved {len(suppliers)} suppliers from Syrve")
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
        import_url = f"{self.api_url}/api/documents/import"
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    import_url,
                    content=xml,
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/xml"
                    }
                )
                
                # Handle 401 by refreshing token and retrying
                if response.status_code == 401:
                    logger.warning("Auth token expired, refreshing and retrying")
                    # Remove from cache to force re-auth
                    cache_key = f"syrve:key:{self.login}"
                    cache_set(cache_key, None)
                    # Let the retry decorator handle the retry
                    raise httpx.HTTPStatusError("Token expired", request=response.request, response=response)
                
                response.raise_for_status()
                result = response.json()
                
                logger.info(f"Invoice import result: {result}")
                return result
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            try:
                error_data = e.response.json()
                error_message = error_data.get("errorMessage", str(e))
            except Exception:
                error_message = e.response.text or str(e)
                
            logger.error(f"Invoice import failed with status {status_code}: {error_message}")
            
            # Return a structured error response
            return {
                "valid": False,
                "status": status_code,
                "errorMessage": error_message
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
        
        # Convert invoice data to JSON string
        invoice_json = json.dumps(invoice_data, indent=2)
        
        # Create messages for the API call
        messages = [
            {"role": "system", "content": _syrve_prompt_cache},
            {"role": "user", "content": f"Generate Syrve XML for this invoice:\n\n```json\n{invoice_json}\n```"}
        ]
        
        # Call OpenAI API with optimized parameters
        response = await openai_client.chat.completions.acreate(
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