from unittest.mock import patch, MagicMock
from app.utils import redis_cache
import json

def setup_function(function):
    redis_cache._redis = None

def test_cache_set_and_get_mock():
    with patch('app.utils.redis_cache.redis.Redis.from_url') as mock_from_url:
        mock_instance = MagicMock()
        mock_from_url.return_value = mock_instance
        key = "test:key"
        value = {"a": 1, "b": [2, 3], "c": "str"}
        redis_cache.cache_set(key, value, ex=2)
        mock_instance.set.assert_called_once_with(key, json.dumps(value), ex=2)
        mock_instance.get.return_value = json.dumps(value).encode("utf-8")
        result = redis_cache.cache_get(key)
        assert json.loads(mock_instance.get.return_value.decode("utf-8")) == value
        mock_instance.get.return_value = None
        assert redis_cache.cache_get(key) is None

def test_cache_overwrite_mock():
    with patch('app.utils.redis_cache.redis.Redis.from_url') as mock_from_url:
        mock_instance = MagicMock()
        mock_from_url.return_value = mock_instance
        key = "test:key2"
        value1 = {"foo": 123}
        value2 = {"foo": 456}
        redis_cache.cache_set(key, value1, ex=5)
        mock_instance.set.assert_called_with(key, json.dumps(value1), ex=5)
        mock_instance.get.return_value = json.dumps(value1).encode("utf-8")
        assert json.loads(mock_instance.get.return_value.decode("utf-8")) == value1
        # сбросить синглтон для повторного мока
        redis_cache._redis = None
        with patch('app.utils.redis_cache.redis.Redis.from_url') as mock_from_url2:
            mock_instance2 = MagicMock()
            mock_from_url2.return_value = mock_instance2
            redis_cache.cache_set(key, value2, ex=5)
            mock_instance2.set.assert_called_with(key, json.dumps(value2), ex=5)
            mock_instance2.get.return_value = json.dumps(value2).encode("utf-8")
            assert json.loads(mock_instance2.get.return_value.decode("utf-8")) == value2
