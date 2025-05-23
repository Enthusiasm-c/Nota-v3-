"""
Enhanced OCR caching with support for both sync and async operations.
"""
import json
import hashlib
import logging
from datetime import date
from typing import Optional, Union, Dict, Any
from app.models import ParsedData

logger = logging.getLogger(__name__)

class DateJSONEncoder(json.JSONEncoder):
    """JSON encoder that can handle dates."""
    def default(self, obj):
        if isinstance(obj, date):
            return obj.isoformat()
        return super().default(obj)

def _compute_cache_key(image_bytes: Union[str, bytes]) -> str:
    """
    Compute cache key for image data.
    
    Args:
        image_bytes: Raw image bytes or base64 string
        
    Returns:
        Cache key string
    """
    if isinstance(image_bytes, str):
        data = image_bytes.encode('utf-8')
    else:
        data = image_bytes
    return hashlib.sha256(data).hexdigest()

def _serialize_parsed_data(data: ParsedData) -> str:
    """
    Serialize ParsedData to JSON string.
    
    Args:
        data: ParsedData instance
        
    Returns:
        JSON string
    """
    return json.dumps(data.model_dump(), cls=DateJSONEncoder)

def _deserialize_parsed_data(data_str: str) -> Optional[ParsedData]:
    """
    Deserialize JSON string to ParsedData.
    
    Args:
        data_str: JSON string
        
    Returns:
        ParsedData instance or None if deserialization fails
    """
    try:
        data = json.loads(data_str)
        return ParsedData.model_validate(data)
    except Exception as e:
        logger.error(f"Failed to deserialize cached data: {e}")
        return None

def get_from_cache(image_bytes: Union[str, bytes]) -> Optional[ParsedData]:
    """
    Get parsed data from cache.
    
    Args:
        image_bytes: Raw image bytes or base64 string
        
    Returns:
        ParsedData instance or None if not found
    """
    try:
        key = _compute_cache_key(image_bytes)
        # Implementation of actual cache retrieval goes here
        # This is just a placeholder
        return None
    except Exception as e:
        logger.error(f"Cache read error: {e}")
        return None

def save_to_cache(image_bytes: Union[str, bytes], data: ParsedData) -> None:
    """
    Save parsed data to cache.
    
    Args:
        image_bytes: Raw image bytes or base64 string
        data: ParsedData instance to cache
    """
    try:
        key = _compute_cache_key(image_bytes)
        serialized = _serialize_parsed_data(data)
        # Implementation of actual cache storage goes here
        # This is just a placeholder
    except Exception as e:
        logger.error(f"Cache write error: {e}")

async def get_from_cache_async(image_bytes: Union[str, bytes]) -> Optional[ParsedData]:
    """
    Async version of get_from_cache.
    
    Args:
        image_bytes: Raw image bytes or base64 string
        
    Returns:
        ParsedData instance or None if not found
    """
    try:
        key = _compute_cache_key(image_bytes)
        # Implementation of actual async cache retrieval goes here
        # This is just a placeholder
        return None
    except Exception as e:
        logger.error(f"Async cache read error: {e}")
        return None

async def save_to_cache_async(image_bytes: Union[str, bytes], data: ParsedData) -> None:
    """
    Async version of save_to_cache.
    
    Args:
        image_bytes: Raw image bytes or base64 string
        data: ParsedData instance to cache
    """
    try:
        key = _compute_cache_key(image_bytes)
        serialized = _serialize_parsed_data(data)
        # Implementation of actual async cache storage goes here
        # This is just a placeholder
    except Exception as e:
        logger.error(f"Async cache write error: {e}")