"""
Унифицированная система статистики кеша для всех модулей приложения.
Этот модуль предоставляет общие интерфейсы для сбора и отображения
статистики кеша из разных источников.
"""

import time
from typing import Any, Dict, Protocol, List
from abc import ABC, abstractmethod


class CacheStatsProvider(Protocol):
    """Протокол для провайдеров статистики кеша."""
    
    def get_stats(self) -> Dict[str, Any]:
        """Возвращает статистику кеша."""
        ...
    
    def get_name(self) -> str:
        """Возвращает имя кеша."""
        ...


class BaseCacheStatsProvider(ABC):
    """Базовый класс для провайдеров статистики кеша."""
    
    def __init__(self, name: str):
        self.name = name
    
    def get_name(self) -> str:
        return self.name
    
    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        pass


class OCRCacheStatsProvider(BaseCacheStatsProvider):
    """Провайдер статистики для OCR кеша."""
    
    def __init__(self):
        super().__init__("ocr_cache")
    
    def get_stats(self) -> Dict[str, Any]:
        from app.utils.ocr_cache import OCR_CACHE, CACHE_TTL
        
        now = time.time()
        active_entries = sum(1 for _, timestamp in OCR_CACHE.values() if now - timestamp <= CACHE_TTL)
        
        return {
            "total_entries": len(OCR_CACHE),
            "active_entries": active_entries,
            "expired_entries": len(OCR_CACHE) - active_entries,
            "cache_ttl_hours": CACHE_TTL / 3600,
        }


class StringCacheStatsProvider(BaseCacheStatsProvider):
    """Провайдер статистики для строкового кеша."""
    
    def __init__(self):
        super().__init__("string_cache")
    
    def get_stats(self) -> Dict[str, Any]:
        from app.utils.string_cache import _string_compare_cache, MAX_CACHE_SIZE, _cache_lock
        
        with _cache_lock:
            return {
                "size": len(_string_compare_cache),
                "max_size": MAX_CACHE_SIZE,
                "usage_percent": (len(_string_compare_cache) / MAX_CACHE_SIZE) * 100 if MAX_CACHE_SIZE > 0 else 0,
            }


class DataCacheStatsProvider(BaseCacheStatsProvider):
    """Провайдер статистики для кеша данных."""
    
    def __init__(self):
        super().__init__("data_cache")
    
    def get_stats(self) -> Dict[str, Any]:
        from app.utils.cached_loader import (
            _DATA_CACHE, _MODIFIED_TIMES, _CACHE_LOCK,
            _STRING_CACHE, _STRING_CACHE_LOCK, _STRING_CACHE_MAX_SIZE,
            _STRING_CACHE_HITS, _STRING_CACHE_MISSES
        )
        
        stats = {}
        
        with _CACHE_LOCK:
            stats["data_cache"] = {
                "files_cached": len(_DATA_CACHE),
                "modified_times_tracked": len(_MODIFIED_TIMES),
            }
        
        with _STRING_CACHE_LOCK:
            total_requests = _STRING_CACHE_HITS + _STRING_CACHE_MISSES
            hit_rate = (_STRING_CACHE_HITS / total_requests * 100) if total_requests > 0 else 0
            
            stats["string_cache"] = {
                "size": len(_STRING_CACHE),
                "max_size": _STRING_CACHE_MAX_SIZE,
                "hits": _STRING_CACHE_HITS,
                "misses": _STRING_CACHE_MISSES,
                "hit_rate_percent": round(hit_rate, 2),
                "usage_percent": (len(_STRING_CACHE) / _STRING_CACHE_MAX_SIZE) * 100 if _STRING_CACHE_MAX_SIZE > 0 else 0,
            }
        
        return stats


# Глобальный реестр провайдеров
_providers: List[CacheStatsProvider] = []


def register_cache_provider(provider: CacheStatsProvider) -> None:
    """Регистрирует провайдера статистики кеша."""
    _providers.append(provider)


def get_all_cache_stats() -> Dict[str, Any]:
    """
    Возвращает статистику всех зарегистрированных кешей.
    
    Returns:
        Словарь со статистикой всех кешей
    """
    stats = {}
    
    for provider in _providers:
        try:
            stats[provider.get_name()] = provider.get_stats()
        except Exception as e:
            stats[provider.get_name()] = {"error": str(e)}
    
    return stats


def get_cache_stats_summary() -> Dict[str, Any]:
    """
    Возвращает сводную статистику всех кешей.
    
    Returns:
        Словарь со сводной статистикой
    """
    all_stats = get_all_cache_stats()
    
    summary = {
        "total_caches": len(all_stats),
        "caches_with_errors": sum(1 for stats in all_stats.values() if "error" in stats),
        "timestamp": time.time(),
    }
    
    # Подсчитываем общие метрики где возможно
    total_entries = 0
    total_max_size = 0
    
    for cache_name, stats in all_stats.items():
        if "error" in stats:
            continue
            
        # Для разных типов кешей используем разные поля
        if cache_name == "ocr_cache":
            total_entries += stats.get("total_entries", 0)
        elif cache_name in ["string_cache", "data_cache"]:
            if cache_name == "string_cache":
                total_entries += stats.get("size", 0)
                total_max_size += stats.get("max_size", 0)
            else:  # data_cache
                if "string_cache" in stats:
                    total_entries += stats["string_cache"].get("size", 0)
                    total_max_size += stats["string_cache"].get("max_size", 0)
    
    summary["total_entries"] = total_entries
    summary["total_max_size"] = total_max_size
    
    return summary


# Автоматически регистрируем стандартные провайдеры
def _auto_register_providers():
    """Автоматически регистрирует стандартные провайдеры."""
    try:
        register_cache_provider(OCRCacheStatsProvider())
    except ImportError:
        pass
    
    try:
        register_cache_provider(StringCacheStatsProvider())
    except ImportError:
        pass
    
    try:
        register_cache_provider(DataCacheStatsProvider())
    except ImportError:
        pass


# Регистрируем провайдеры при импорте модуля
_auto_register_providers()