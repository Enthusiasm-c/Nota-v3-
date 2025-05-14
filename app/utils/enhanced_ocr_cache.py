"""
Улучшенный модуль кеширования OCR-результатов.
Обеспечивает быстрый доступ и резервирование через Redis/локальный кеш.
"""
import hashlib
import json
import logging
import pickle
import time
from typing import Any, Dict, Optional
import concurrent.futures
import asyncio

from app.models import ParsedData
from app.utils.redis_cache import cache_get, cache_set

logger = logging.getLogger(__name__)

# Константы для кеша
CACHE_PREFIX = "ocr:image:"
CACHE_TTL = 86400 * 7  # 7 дней
IN_MEMORY_CACHE_SIZE = 50  # Размер локального кеша

# Локальный in-memory кеш для ускорения частых запросов
_local_cache: Dict[str, Any] = {}


def _compute_image_hash(image_bytes: bytes) -> str:
    """
    Вычисляет хеш изображения для использования в качестве ключа кеша.
    Использует быстрый алгоритм SHA-256.
    
    Args:
        image_bytes: Байты изображения
        
    Returns:
        Хеш в виде строки
    """
    return hashlib.sha256(image_bytes).hexdigest()


def _serialize_parsed_data(data: ParsedData) -> str:
    """
    Сериализует ParsedData для хранения в кеше.
    
    Args:
        data: Данные для сериализации
        
    Returns:
        Сериализованные данные в формате JSON
    """
    try:
        if hasattr(data, "model_dump"):
            # Pydantic v2
            return json.dumps(data.model_dump())
        else:
            # Pydantic v1 fallback
            return json.dumps(data.dict())
    except Exception as e:
        logger.error(f"Ошибка сериализации данных: {e}")
        # Используем pickle как запасной вариант
        return pickle.dumps(data)


def _deserialize_parsed_data(data_str: str) -> Optional[ParsedData]:
    """
    Десериализует данные из кеша.
    
    Args:
        data_str: Сериализованные данные
        
    Returns:
        Объект ParsedData или None в случае ошибки
    """
    try:
        # Пробуем десериализовать как JSON
        data_dict = json.loads(data_str)
        return ParsedData.model_validate(data_dict)
    except json.JSONDecodeError:
        # Если не JSON, пробуем как pickle
        try:
            return pickle.loads(data_str)
        except Exception as e:
            logger.error(f"Ошибка десериализации данных: {e}")
            return None
    except Exception as e:
        logger.error(f"Ошибка десериализации данных: {e}")
        return None


def get_from_cache(image_bytes: bytes) -> Optional[ParsedData]:
    """
    Получает результаты OCR из кеша по изображению.
    Сначала проверяет локальный кеш, затем Redis.
    
    Args:
        image_bytes: Байты изображения
        
    Returns:
        Результаты OCR или None, если кеш отсутствует
    """
    image_hash = _compute_image_hash(image_bytes)
    cache_key = f"{CACHE_PREFIX}{image_hash}"
    
    # Проверяем локальный кеш (самый быстрый доступ)
    if image_hash in _local_cache:
        logger.debug(f"OCR кеш: найден в локальном кеше ({image_hash[:8]})")
        return _local_cache[image_hash]
    
    # Проверяем Redis
    cached_data = cache_get(cache_key)
    if cached_data:
        try:
            if isinstance(cached_data, (bytes, str)):
                parsed_data = _deserialize_parsed_data(cached_data)
            else:
                # Если данные уже десериализованы через Redis middleware
                parsed_data = ParsedData.model_validate(cached_data)
                
            if parsed_data:
                # Обновляем локальный кеш
                _update_local_cache(image_hash, parsed_data)
                logger.debug(f"OCR кеш: найден в Redis ({image_hash[:8]})")
                return parsed_data
        except Exception as e:
            logger.warning(f"Ошибка при десериализации данных из кеша: {e}")
    
    logger.debug(f"OCR кеш: не найден ({image_hash[:8]})")
    return None


def save_to_cache(image_bytes: bytes, data: ParsedData) -> bool:
    """
    Сохраняет результаты OCR в кеш.
    
    Args:
        image_bytes: Байты изображения
        data: Результаты OCR для сохранения
        
    Returns:
        True, если сохранение прошло успешно
    """
    image_hash = _compute_image_hash(image_bytes)
    cache_key = f"{CACHE_PREFIX}{image_hash}"
    
    # Обновляем локальный кеш
    _update_local_cache(image_hash, data)
    
    # Сохраняем в Redis асинхронно в фоновом потоке
    try:
        serialized_data = _serialize_parsed_data(data)
        cache_set(cache_key, serialized_data, ex=CACHE_TTL)
        logger.debug(f"OCR кеш: сохранено в Redis ({image_hash[:8]})")
        return True
    except Exception as e:
        logger.warning(f"Ошибка при сохранении в Redis кеш: {e}")
        return False


def _update_local_cache(key: str, data: Any) -> None:
    """
    Обновляет локальный кеш, соблюдая ограничения размера.
    
    Args:
        key: Ключ для сохранения
        data: Данные для сохранения
    """
    # Если локальный кеш переполнен, удаляем самые старые элементы
    if len(_local_cache) >= IN_MEMORY_CACHE_SIZE:
        # Удаляем половину элементов
        keys_to_remove = list(_local_cache.keys())[:IN_MEMORY_CACHE_SIZE // 2]
        for k in keys_to_remove:
            _local_cache.pop(k, None)
    
    # Добавляем новый элемент
    _local_cache[key] = data


async def async_get_from_cache(image_bytes: bytes) -> Optional[ParsedData]:
    """
    Асинхронная версия получения результатов OCR из кеша.
    
    Args:
        image_bytes: Байты изображения
        
    Returns:
        Результаты OCR или None, если кеш отсутствует
    """
    # Вычисляем хеш без блокировки основного потока
    loop = asyncio.get_event_loop()
    image_hash = await loop.run_in_executor(None, _compute_image_hash, image_bytes)
    
    # Проверяем локальный кеш
    if image_hash in _local_cache:
        logger.debug(f"OCR async кеш: найден в локальном кеше ({image_hash[:8]})")
        return _local_cache[image_hash]
    
    # Ключ для Redis
    cache_key = f"{CACHE_PREFIX}{image_hash}"
    
    # Проверяем Redis
    try:
        cached_data = cache_get(cache_key)
        if cached_data:
            # Десериализуем без блокировки основного потока
            if isinstance(cached_data, (bytes, str)):
                parsed_data = await loop.run_in_executor(None, _deserialize_parsed_data, cached_data)
            else:
                # Если данные уже десериализованы
                parsed_data = ParsedData.model_validate(cached_data)
                
            if parsed_data:
                # Обновляем локальный кеш
                _update_local_cache(image_hash, parsed_data)
                logger.debug(f"OCR async кеш: найден в Redis ({image_hash[:8]})")
                return parsed_data
    except Exception as e:
        logger.warning(f"Ошибка при асинхронном доступе к кешу: {e}")
    
    logger.debug(f"OCR async кеш: не найден ({image_hash[:8]})")
    return None


async def async_save_to_cache(image_bytes: bytes, data: ParsedData) -> bool:
    """
    Асинхронная версия сохранения результатов OCR в кеш.
    
    Args:
        image_bytes: Байты изображения
        data: Результаты OCR для сохранения
        
    Returns:
        True, если сохранение прошло успешно
    """
    loop = asyncio.get_event_loop()
    
    # Вычисляем хеш без блокировки
    image_hash = await loop.run_in_executor(None, _compute_image_hash, image_bytes)
    cache_key = f"{CACHE_PREFIX}{image_hash}"
    
    # Обновляем локальный кеш
    _update_local_cache(image_hash, data)
    
    # Сериализуем и сохраняем без блокировки
    try:
        serialized_data = await loop.run_in_executor(None, _serialize_parsed_data, data)
        cache_set(cache_key, serialized_data, ex=CACHE_TTL)
        logger.debug(f"OCR async кеш: сохранено в Redis ({image_hash[:8]})")
        return True
    except Exception as e:
        logger.warning(f"Ошибка при асинхронном сохранении в кеш: {e}")
        return False