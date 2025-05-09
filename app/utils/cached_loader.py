"""
Utilities for caching frequently accessed data.
"""

import time
import os
import threading
import logging
import functools
from typing import Dict, Any, Callable, List, Optional

logger = logging.getLogger(__name__)

# Global cache for products data
_products_cache = {
    "data": None,
    "last_updated": 0,
    "file_mtime": 0
}
_cache_lock = threading.Lock()

def cached_load_products(csv_path: str, loader_func: Callable, max_age_seconds: int = 300):
    """
    Caching wrapper for product data loading.
    
    Args:
        csv_path: Path to the CSV file
        loader_func: Original function that loads the data
        max_age_seconds: Maximum cache age in seconds
        
    Returns:
        Cached product data or freshly loaded data if cache is invalid
    """
    global _products_cache
    
    current_time = time.time()
    
    with _cache_lock:
        # Check if file has changed or cache is too old
        try:
            file_mtime = os.path.getmtime(csv_path)
        except OSError:
            file_mtime = 0
            
        # Check if cache needs updating
        cache_expired = current_time - _products_cache["last_updated"] > max_age_seconds
        file_changed = file_mtime > _products_cache["file_mtime"]
        
        if _products_cache["data"] is None or cache_expired or file_changed:
            # Load data
            logger.info(f"Updating products cache from {csv_path}")
            start_time = time.time()
            _products_cache["data"] = loader_func(csv_path)
            _products_cache["last_updated"] = current_time
            _products_cache["file_mtime"] = file_mtime
            logger.info(f"Products cache updated: {len(_products_cache['data'])} items in {time.time() - start_time:.2f}s")
        else:
            logger.debug(f"Using cached products: {len(_products_cache['data'])} items")
            
        return _products_cache["data"]