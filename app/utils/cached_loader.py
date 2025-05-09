"""
Utilities for caching frequently accessed data.
"""

import time
import os
import threading
import logging
import functools
from typing import Dict, Any, Callable, List, Optional, Tuple, Hashable

logger = logging.getLogger(__name__)

# Global cache for products data
_products_cache = {
    "data": None,
    "last_updated": 0,
    "file_mtime": 0
}
_cache_lock = threading.Lock()

# Глобальный кэш для хранения загруженных данных
_data_cache = {}
_cache_timestamps = {}
_cache_ttl = 300  # 5 минут время жизни кэша по умолчанию

# Кэш для результатов сравнения строк
_string_comparison_cache = {}
_string_cache_size = 10000  # Максимальный размер кэша
_string_cache_hits = 0
_string_cache_misses = 0

def cached_load_data(path: str, loader_func: Callable, ttl: int = 300) -> List[Dict[str, Any]]:
    """
    Загружает данные из файла с кэшированием результатов.
    
    Args:
        path: Путь к файлу с данными
        loader_func: Функция загрузки, которая принимает путь к файлу
        ttl: Время жизни кэша в секундах
        
    Returns:
        Загруженные данные (из кэша или напрямую)
    """
    global _data_cache, _cache_timestamps, _cache_ttl
    
    _cache_ttl = ttl
    current_time = time.time()
    
    # Проверяем, есть ли данные в кэше и не истек ли срок их действия
    if path in _data_cache and (current_time - _cache_timestamps.get(path, 0)) < _cache_ttl:
        logger.debug(f"Using cached {path}: {len(_data_cache[path])} items")
        return _data_cache[path]
    
    # Загружаем данные и сохраняем в кэш
    data = loader_func(path)
    _data_cache[path] = data
    _cache_timestamps[path] = current_time
    
    logger.info(f"Loaded fresh data from {path}: {len(data)} items")
    return data

def clear_cache(path: Optional[str] = None) -> None:
    """
    Очищает кэш загруженных данных.
    
    Args:
        path: Если указан, очищает только кэш для этого пути,
              иначе очищает весь кэш
    """
    global _data_cache, _cache_timestamps
    
    if path:
        if path in _data_cache:
            del _data_cache[path]
        if path in _cache_timestamps:
            del _cache_timestamps[path]
        logger.debug(f"Cleared cache for {path}")
    else:
        _data_cache.clear()
        _cache_timestamps.clear()
        logger.debug("Cleared all data cache")

def cached_compare_strings(func: Callable) -> Callable:
    """
    Декоратор для кэширования результатов сравнения строк.
    
    Существенно ускоряет работу функций сравнения строк за счет
    сохранения ранее вычисленных результатов. Особенно эффективен
    при многократном сравнении одних и тех же строк в процессе
    поиска соответствий.
    
    Args:
        func: Функция сравнения строк, принимающая две строки
        
    Returns:
        Обернутая функция с кэшированием результатов
    """
    @functools.wraps(func)
    def wrapper(s1: str, s2: str, *args, **kwargs) -> float:
        global _string_comparison_cache, _string_cache_hits, _string_cache_misses
        
        # Создаем ключ кэша из нормализованных строк
        # (нормализация выполняется самой функцией сравнения)
        cache_key = (s1, s2)
        reverse_key = (s2, s1)
        
        # Проверяем кэш
        if cache_key in _string_comparison_cache:
            _string_cache_hits += 1
            return _string_comparison_cache[cache_key]
        
        if reverse_key in _string_comparison_cache:
            _string_cache_hits += 1
            return _string_comparison_cache[reverse_key]
        
        # Кэш-промах, вычисляем результат
        _string_cache_misses += 1
        result = func(s1, s2, *args, **kwargs)
        
        # Сохраняем в кэш
        _string_comparison_cache[cache_key] = result
        
        # Проверяем размер кэша и очищаем при необходимости
        if len(_string_comparison_cache) > _string_cache_size:
            # Удаляем 20% наиболее старых записей
            items_to_remove = int(_string_cache_size * 0.2)
            for _ in range(items_to_remove):
                _string_comparison_cache.pop(next(iter(_string_comparison_cache)))
            
            # Сбрасываем счетчики для статистики
            if (_string_cache_hits + _string_cache_misses) > 50000:
                logger.info(f"String comparison cache stats: {_string_cache_hits} hits, {_string_cache_misses} misses, " +
                           f"hit rate: {_string_cache_hits/(_string_cache_hits+_string_cache_misses)*100:.1f}%")
                _string_cache_hits = 0
                _string_cache_misses = 0
                
        return result
    
    return wrapper

def get_string_cache_stats() -> Dict[str, Any]:
    """
    Возвращает статистику использования кэша сравнения строк.
    
    Returns:
        Словарь со статистикой кэша
    """
    global _string_comparison_cache, _string_cache_hits, _string_cache_misses
    
    total_queries = _string_cache_hits + _string_cache_misses
    hit_rate = (_string_cache_hits / total_queries * 100) if total_queries > 0 else 0
    
    return {
        "size": len(_string_comparison_cache),
        "max_size": _string_cache_size,
        "hits": _string_cache_hits,
        "misses": _string_cache_misses,
        "hit_rate": hit_rate,
        "memory_usage_approx": len(_string_comparison_cache) * 100  # Примерный размер в байтах
    }

def cached_load_products(csv_path: str, loader_func: Callable, max_age_seconds: int = 300):
    """
    Backward compatibility function for cached loading products.
    """
    return cached_load_data(csv_path, loader_func, max_age_seconds)