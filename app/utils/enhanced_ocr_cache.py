"""
Enhanced OCR caching with support for both sync and async operations.
"""

import hashlib
import json
import logging
from datetime import date
from typing import Optional, Union

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
        data = image_bytes.encode("utf-8")
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


def get_from_cache(image_bytes: bytes) -> Optional[ParsedData]:
    """
    Получает данные из кэша по ключу, вычисленному из байтов изображения
    """
    try:
        key = _compute_cache_key(image_bytes)
        logger.info(f"Looking up cache with key: {key}")
        # Implementation of actual cache retrieval goes here
        # This is just a placeholder
        return None
    except Exception as e:
        logger.error(f"Error retrieving from cache: {e}")
        return None


def store_in_cache(image_bytes: bytes, data: ParsedData) -> None:
    """
    Сохраняет данные в кэш с ключом, вычисленным из байтов изображения
    """
    try:
        key = _compute_cache_key(image_bytes)
        serialized = _serialize_parsed_data(data)
        # Implementation of actual cache storage goes here
        # This is just a placeholder
        logger.info(f"Stored data in cache with key {key}, serialized size: {len(serialized)}")
    except Exception as e:
        logger.error(f"Error storing in cache: {e}")


async def async_get_from_cache(image_bytes: bytes) -> Optional[ParsedData]:
    """
    Асинхронно получает данные из кэша
    """
    try:
        key = _compute_cache_key(image_bytes)
        # Implementation of actual async cache retrieval goes here
        # This is just a placeholder
        logger.info(f"Async cache lookup for key: {key}")
        return None
    except Exception as e:
        logger.error(f"Error in async cache retrieval: {e}")
        return None


async def async_store_in_cache(image_bytes: bytes, data: ParsedData) -> None:
    """
    Асинхронно сохраняет данные в кэш
    """
    try:
        key = _compute_cache_key(image_bytes)
        serialized = _serialize_parsed_data(data)
        # Implementation of actual async cache storage goes here
        # This is just a placeholder
        logger.info(
            f"Async stored data in cache with key {key}, serialized size: {len(serialized)}"
        )
    except Exception as e:
        logger.error(f"Error in async cache storage: {e}")

        logger.error(f"Async cache write error: {e}")