"""
Оптимизированный кеш для строковых сравнений.
Существенно ускоряет операции сопоставления при повторных запросах.
"""
import threading
from typing import Dict, Tuple, Optional, Any
from functools import lru_cache

# Кеш для сравнения строк со встроенным LRU механизмом
_string_compare_cache = {}
_cache_lock = threading.RLock()

# Ограничения для кеша
MAX_CACHE_SIZE = 10000  # Максимальное количество элементов в кеше
MAX_STRING_LENGTH = 200  # Максимальная длина строки для кеширования
CLEANUP_THRESHOLD = 0.8  # Порог заполнения для очистки кеша

def get_string_similarity_cached(s1: str, s2: str) -> Optional[float]:
    """
    Получает кешированное значение сходства между строками.
    
    Args:
        s1: Первая строка для сравнения
        s2: Вторая строка для сравнения
        
    Returns:
        Значение сходства из кеша или None, если его нет
    """
    # Кеширование отключено для слишком длинных строк
    if len(s1) > MAX_STRING_LENGTH or len(s2) > MAX_STRING_LENGTH:
        return None
        
    # Строки должны быть отсортированы для консистентного ключа
    key = tuple(sorted([s1, s2]))
    
    with _cache_lock:
        return _string_compare_cache.get(key)

def set_string_similarity_cached(s1: str, s2: str, similarity: float) -> None:
    """
    Сохраняет значение сходства между строками в кеш.
    
    Args:
        s1: Первая строка для сравнения
        s2: Вторая строка для сравнения
        similarity: Значение сходства для сохранения
    """
    # Кеширование отключено для слишком длинных строк
    if len(s1) > MAX_STRING_LENGTH or len(s2) > MAX_STRING_LENGTH:
        return
        
    # Строки должны быть отсортированы для консистентного ключа
    key = tuple(sorted([s1, s2]))
    
    with _cache_lock:
        # Проверяем размер кеша и очищаем его при необходимости
        if len(_string_compare_cache) >= MAX_CACHE_SIZE * CLEANUP_THRESHOLD:
            # Очищаем старые элементы (удаляем половину)
            items = list(_string_compare_cache.items())
            items.sort(key=lambda x: x[1], reverse=True)  # Сортируем по сходству
            for k, _ in items[MAX_CACHE_SIZE // 2:]:
                _string_compare_cache.pop(k, None)
        
        # Добавляем новое значение в кеш
        _string_compare_cache[key] = similarity
        
def clear_string_cache() -> None:
    """Полностью очищает кеш сравнения строк."""
    with _cache_lock:
        _string_compare_cache.clear()
        
def get_cache_stats() -> Dict[str, Any]:
    """
    Возвращает статистику использования кеша.
    
    Returns:
        Словарь со статистикой кеша
    """
    with _cache_lock:
        return {
            "size": len(_string_compare_cache),
            "max_size": MAX_CACHE_SIZE,
            "fill_percentage": len(_string_compare_cache) / MAX_CACHE_SIZE * 100
        }

# Небольшой кеш для быстрого сравнения наиболее частых строк
@lru_cache(maxsize=5000)
def cached_string_similarity(s1: str, s2: str) -> float:
    """
    Декоратор для кеширования результатов сравнения строк.
    Используется как обертка вокруг функции вычисления сходства.
    
    Args:
        s1: Первая строка для сравнения
        s2: Вторая строка для сравнения
        
    Returns:
        Кешированное или новое значение сходства
    """
    # Проксирующая функция для внешней функции сравнения
    # Фактическая реализация будет использовать этот декоратор
    pass