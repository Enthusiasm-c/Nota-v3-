"""
Модуль для кеширования результатов OCR на основе хешей изображений.
Позволяет избежать повторной обработки одинаковых изображений.
"""

import hashlib
import logging
import time
from typing import Dict, Optional, Any, Tuple
from app.models import ParsedData

logger = logging.getLogger(__name__)

# Кеш для OCR результатов: {хеш_изображения: (data, timestamp)}
# Используем timestamp для определения возраста кеша
OCR_CACHE: Dict[str, Tuple[ParsedData, float]] = {}

# Максимальный размер кеша
MAX_CACHE_SIZE = 100

# Время жизни кеша в секундах (12 часов)
CACHE_TTL = 12 * 60 * 60


def get_image_hash(image_bytes: bytes) -> str:
    """
    Вычисляет MD5-хеш изображения для использования как ключ кеша.
    
    Args:
        image_bytes: Байты изображения
        
    Returns:
        str: MD5-хеш в виде hex-строки
    """
    return hashlib.md5(image_bytes).hexdigest()


def get_from_cache(image_bytes: bytes) -> Optional[ParsedData]:
    """
    Проверяет, есть ли результат OCR в кеше для данного изображения.
    
    Args:
        image_bytes: Байты изображения
        
    Returns:
        Optional[ParsedData]: Результат OCR из кеша или None, если не найден
    """
    img_hash = get_image_hash(image_bytes)
    
    # Проверяем наличие в кеше
    if img_hash in OCR_CACHE:
        data, timestamp = OCR_CACHE[img_hash]
        
        # Проверяем TTL
        if time.time() - timestamp <= CACHE_TTL:
            logger.info(f"OCR Cache hit for image hash {img_hash[:8]}")
            return data
        else:
            # Удаляем устаревшую запись
            logger.info(f"OCR Cache expired for image hash {img_hash[:8]}")
            OCR_CACHE.pop(img_hash)
    
    return None


def save_to_cache(image_bytes: bytes, data: ParsedData) -> None:
    """
    Сохраняет результат OCR в кеш.
    
    Args:
        image_bytes: Байты изображения
        data: Результат OCR
    """
    img_hash = get_image_hash(image_bytes)
    
    # Проверяем размер кеша
    if len(OCR_CACHE) >= MAX_CACHE_SIZE:
        # Находим самую старую запись
        oldest_key = min(OCR_CACHE.keys(), key=lambda k: OCR_CACHE[k][1])
        OCR_CACHE.pop(oldest_key)
        logger.info(f"OCR Cache pruned oldest entry {oldest_key[:8]}")
    
    # Сохраняем в кеш
    OCR_CACHE[img_hash] = (data, time.time())
    logger.info(f"OCR Cache saved for image hash {img_hash[:8]}")


def clear_cache() -> None:
    """
    Очищает кеш OCR.
    """
    OCR_CACHE.clear()
    logger.info("OCR Cache cleared")


def get_cache_stats() -> Dict[str, Any]:
    """
    Возвращает статистику кеша.
    
    Returns:
        Dict[str, Any]: Статистика кеша
    """
    now = time.time()
    active_entries = sum(1 for _, timestamp in OCR_CACHE.values() if now - timestamp <= CACHE_TTL)
    
    return {
        "total_entries": len(OCR_CACHE),
        "active_entries": active_entries,
        "expired_entries": len(OCR_CACHE) - active_entries,
        "max_size": MAX_CACHE_SIZE,
        "ttl_seconds": CACHE_TTL,
        "memory_usage": sum(len(str(data)) for data, _ in OCR_CACHE.values()) / 1024 if OCR_CACHE else 0  # Приблизительно в КБ
    }