"""
Cache utilities for OCR results.
"""

import hashlib
import logging
import time
from typing import Any, Dict, Optional, Tuple

from app.models import ParsedData

# In-memory cache for OCR results
OCR_CACHE: Dict[str, Tuple[ParsedData, float]] = {}

# Cache settings
MAX_CACHE_SIZE = 100  # Maximum number of cache entries
CACHE_TTL = 12 * 60 * 60  # Cache Time-To-Live in seconds (12 hours)

# Logger
logger = logging.getLogger(__name__)


def get_cache_key(image_bytes: bytes, extra_data: Optional[Dict[str, Any]] = None) -> str:
    """
    Generate cache key from image bytes and optional extra data.

    Args:
        image_bytes: Raw image bytes
        extra_data: Optional dictionary with additional data to include in key

    Returns:
        Cache key string
    """
    hasher = hashlib.md5()
    hasher.update(image_bytes)

    if extra_data:
        # Sort keys to ensure consistent ordering
        sorted_items = sorted(extra_data.items())
        for key, value in sorted_items:
            hasher.update(f"{key}:{value}".encode())

    return hasher.hexdigest()


def get_image_hash(image_bytes: bytes) -> str:
    """
    Generate MD5 hash of image bytes for cache key.

    Args:
        image_bytes: Raw image bytes

    Returns:
        MD5 hash as hex string
    """
    return hashlib.md5(image_bytes).hexdigest()


def get_from_cache(image_bytes: bytes) -> Optional[ParsedData]:
    """
    Try to get OCR result from cache.

    Args:
        image_bytes: Raw image bytes

    Returns:
        Cached OCR result or None if not found or expired
    """
    img_hash = get_image_hash(image_bytes)

    # Check if in cache
    if img_hash in OCR_CACHE:
        data, timestamp = OCR_CACHE[img_hash]

        # Check if expired
        if time.time() - timestamp <= CACHE_TTL:
            logger.info(f"OCR Cache hit for image hash {img_hash[:8]}")
            return data
        else:
            # Remove expired entry
            logger.info(f"OCR Cache expired for image hash {img_hash[:8]}")
            OCR_CACHE.pop(img_hash)

    return None


def save_to_cache(image_bytes: bytes, data: ParsedData) -> None:
    """
    Save OCR result to cache.

    Args:
        image_bytes: Raw image bytes
        data: OCR result to cache
    """
    img_hash = get_image_hash(image_bytes)

    # Check cache size
    if len(OCR_CACHE) >= MAX_CACHE_SIZE:
        # Remove oldest entry
        oldest_key = min(OCR_CACHE.keys(), key=lambda k: OCR_CACHE[k][1])
        OCR_CACHE.pop(oldest_key)
        logger.info(f"OCR Cache pruned oldest entry {oldest_key[:8]}")

    # Save to cache
    OCR_CACHE[img_hash] = (data, time.time())
    logger.info(f"OCR Cache saved for image hash {img_hash[:8]}")


def clear_cache() -> None:
    """Clear the OCR cache."""
    OCR_CACHE.clear()
    logger.info("OCR Cache cleared")


def clear_expired_cache() -> int:
    """
    Remove all expired entries from the cache.

    Returns:
        Number of entries removed
    """
    now = time.time()
    expired_keys = [key for key, (_, timestamp) in OCR_CACHE.items() if now - timestamp > CACHE_TTL]

    for key in expired_keys:
        OCR_CACHE.pop(key)
        logger.info(f"Removed expired cache entry {key[:8]}")

    return len(expired_keys)


def get_cache_stats() -> Dict[str, Any]:
    """
    Get cache statistics.

    Returns:
        Dictionary with cache statistics
    """
    now = time.time()
    active_entries = sum(1 for _, timestamp in OCR_CACHE.values() if now - timestamp <= CACHE_TTL)

    return {
        "total_entries": len(OCR_CACHE),
        "active_entries": active_entries,
        "expired_entries": len(OCR_CACHE) - active_entries,
        "max_size": MAX_CACHE_SIZE,
        "ttl_seconds": CACHE_TTL,
        "memory_usage": (
            sum(len(str(data)) for data, _ in OCR_CACHE.values()) / 1024 if OCR_CACHE else 0
        ),  # Approximate KB
    }
