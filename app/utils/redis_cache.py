import os
import redis
import json
from app.handlers.tracing_log_middleware import _default


REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

_redis = None


def get_redis():
    global _redis
    if _redis is None:
        _redis = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    return _redis


def cache_set(key: str, value, ex: int = 300):
    r = get_redis()
    r.set(key, json.dumps(value, default=_default, ensure_ascii=False), ex=ex)


def cache_get(key: str):
    r = get_redis()
    val = r.get(key)
    if val is not None:
        return json.loads(val)
    return None
