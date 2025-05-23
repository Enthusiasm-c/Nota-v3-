import json
import logging
import os
import threading
import time
from typing import Any, Dict, Optional, Tuple

import redis

from app.handlers.tracing_log_middleware import _default

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
_redis = None
logger = logging.getLogger("redis_cache")

# Увеличенный размер локального кэша для лучшей производительности
CACHE_SIZE = 2048
REDIS_RETRY_INTERVAL = 60  # секунды между попытками восстановления соединения


# Расширенный in-memory кэш для лучшей производительности
# при недоступности Redis
class EnhancedLocalCache:
    """
    Улучшенная версия локального кэша с поддержкой TTL и автоматической очисткой.
    Обеспечивает более эффективную работу в случае недоступности Redis.
    """

    def __init__(self, max_size: int = CACHE_SIZE):
        self._cache: Dict[str, Tuple[Any, float, Optional[float]]] = (
            {}
        )  # key -> (value, timestamp, expiry)
        self._max_size = max_size
        self._lock = threading.RLock()

        # Запуск фонового процесса очистки
        self._cleanup_thread = threading.Thread(target=self._cleanup_expired, daemon=True)
        self._cleanup_thread.start()

    def set(self, key: str, value: Any, ex: Optional[int] = None) -> None:
        """Добавляет элемент в кэш с опциональным временем жизни"""
        with self._lock:
            now = time.time()
            expiry = now + ex if ex is not None else None

            # Если достигнут лимит размера, удаляем самый старый элемент
            if len(self._cache) >= self._max_size and key not in self._cache:
                oldest_key = min(self._cache.items(), key=lambda x: x[1][1])[0]
                del self._cache[oldest_key]

            self._cache[key] = (value, now, expiry)

    def get(self, key: str) -> Optional[Any]:
        """Получает элемент из кэша, проверяя его актуальность"""
        with self._lock:
            if key not in self._cache:
                return None

            value, _, expiry = self._cache[key]

            # Проверяем TTL
            if expiry is not None and time.time() > expiry:
                del self._cache[key]
                return None

            return value

    def _cleanup_expired(self) -> None:
        """Периодически очищает истекшие элементы кэша"""
        # Use an event to allow graceful shutdown
        self._stop_event = threading.Event()

        while not self._stop_event.is_set():
            # Use smaller sleep intervals to respond to shutdown faster
            for _ in range(6):  # 6 x 5 seconds = 30 seconds total
                if self._stop_event.is_set():
                    break
                time.sleep(5)

            # Skip if already stopping
            if self._stop_event.is_set():
                break

            try:
                with self._lock:
                    now = time.time()
                    expired_keys = [
                        key
                        for key, (_, _, expiry) in self._cache.items()
                        if expiry is not None and now > expiry
                    ]
                    for key in expired_keys:
                        del self._cache[key]
            except Exception as e:
                logger.error(f"Ошибка при очистке локального кэша: {e}")

        logger.info("Thread pool cleanup thread stopped gracefully")

    def stop_cleanup(self) -> None:
        """Останавливает поток очистки кэша при завершении работы"""
        if hasattr(self, "_stop_event"):
            self._stop_event.set()
            if hasattr(self, "_cleanup_thread") and self._cleanup_thread.is_alive():
                self._cleanup_thread.join(
                    timeout=2.0
                )  # Wait up to 2 seconds for thread to terminate
                logger.info("Cache cleanup thread stopped")


# Инициализация улучшенного локального кэша
_local_cache = EnhancedLocalCache(CACHE_SIZE)

# Для обеспечения обратной совместимости
_fallback_cache = {}  # Старый словарь для совместимости

# Последняя попытка подключения к Redis
_last_redis_attempt = 0
_redis_available = True


def get_redis():
    """
    Получает соединение с Redis с механизмом повторных попыток.
    Использует периодическую проверку доступности Redis.
    """
    global _redis, _last_redis_attempt, _redis_available

    # Если Redis недоступен и последняя попытка была недавно, не проверяем снова
    now = time.time()
    if not _redis_available and now - _last_redis_attempt < REDIS_RETRY_INTERVAL:
        return None

    # Если соединение не установлено или Redis недоступен, пробуем соединиться
    if _redis is None or not _redis_available:
        try:
            _last_redis_attempt = now
            _redis = redis.Redis.from_url(REDIS_URL, decode_responses=True, socket_timeout=2.0)
            # Проверяем, что соединение работает
            _redis.ping()
            if not _redis_available:
                logger.info("Redis снова доступен, возобновляем использование")
            _redis_available = True
        except redis.exceptions.RedisError as e:
            _redis_available = False
            logger.warning(f"Redis недоступен ({str(e)}), используем локальный кэш")
            return None

    return _redis


def cache_set(key: str, value, ex: int = 300):
    """
    Сохраняет значение в кэше. Если Redis недоступен, использует локальный кэш.

    Args:
        key: Ключ для сохранения
        value: Значение для сохранения
        ex: Время жизни кэша в секундах (по умолчанию 300 секунд)
    """
    # Всегда сохраняем в локальный кэш для быстрого доступа
    _local_cache.set(key, value, ex)
    _fallback_cache[key] = value  # Для обратной совместимости

    # Пробуем сохранить в Redis
    r = get_redis()
    if r is not None:
        try:
            json_value = json.dumps(value, default=_default, ensure_ascii=False)
            r.set(key, json_value, ex=ex)
        except redis.exceptions.RedisError as e:
            global _redis_available
            _redis_available = False
            logger.warning(f"Ошибка сохранения в Redis: {str(e)}")


def cache_get(key: str):
    """
    Получает значение из кэша. Сначала проверяет локальный кэш, затем Redis.
    Если значение найдено в Redis, обновляет локальный кэш.

    Args:
        key: Ключ для получения

    Returns:
        Значение из кэша или None, если значение не найдено
    """
    # Сначала проверяем локальный кэш для быстрого доступа
    local_value = _local_cache.get(key)
    if local_value is not None:
        return local_value

    # Если в локальном кэше нет, проверяем в Redis
    r = get_redis()
    if r is not None:
        try:
            val = r.get(key)
            if val is not None:
                value = json.loads(val)
                # Обновляем локальный кэш
                _local_cache.set(key, value)
                _fallback_cache[key] = value  # Для обратной совместимости
                return value
        except redis.exceptions.RedisError as e:
            global _redis_available
            _redis_available = False
            logger.warning(f"Ошибка получения из Redis: {str(e)}")

    # Для обратной совместимости проверяем старый кэш
    return _fallback_cache.get(key)
