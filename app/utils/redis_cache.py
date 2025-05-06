import os
import redis
import json
from app.handlers.tracing_log_middleware import _default
import logging
from functools import lru_cache

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
_redis = None
logger = logging.getLogger("redis_cache")

# Простой in-memory LRU fallback (до 1024 ключей)
@lru_cache(maxsize=1024)
def _fallback_cache_get(key):
    return None

_fallback_cache = {}

def get_redis():
    global _redis
    if _redis is None:
        _redis = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    return _redis


def cache_set(key: str, value, ex: int = 300):
    try:
        r = get_redis()
        r.set(key, json.dumps(value, default=_default, ensure_ascii=False), ex=ex)
        _fallback_cache[key] = value
    except redis.exceptions.ConnectionError:
        logger.warning("Redis недоступен, сохраняем только в локальный кэш")
        _fallback_cache[key] = value


def cache_get(key: str):
    try:
        r = get_redis()
        val = r.get(key)
        if val is not None:
            value = json.loads(val)
            _fallback_cache[key] = value
            return value
        return _fallback_cache.get(key)
    except redis.exceptions.ConnectionError:
        logger.warning("Redis недоступен, используем локальный кэш")
        return _fallback_cache.get(key)
