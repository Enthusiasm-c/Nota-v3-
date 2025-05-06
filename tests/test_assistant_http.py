import pytest
from unittest.mock import patch, MagicMock
from app.assistants.client import run_thread_safe
import json
from fakeredis import FakeRedis


@pytest.fixture
def fake_redis():
    with patch('app.utils.redis_cache.redis.Redis', return_value=FakeRedis()):
        yield


@pytest.fixture
def mock_client():
    with patch('app.assistants.client.client') as mock:
        yield mock


@pytest.fixture
def mock_latency_monitor():
    with patch('app.utils.monitor.latency_monitor.record_latency') as mock:
        yield mock


def test_run_thread_safe_caching(fake_redis):
    # Кэш не найден, будет set
    # Мокаем OpenAI ответ
    mock_client = MagicMock()
    mock_client.return_value = {'result': 'mocked_result'}
    result = run_thread_safe('set qty', timeout=2)
    assert 'result' in result
    assert fake_redis.return_value.exists('cache_key') == 1


def test_run_thread_safe_latency(fake_redis, mock_client, mock_latency_monitor):
    # Мокаем время
    t = [100.0]
    def fake_time():
        t[0] += 0.015
        return t[0]
    with patch('time.time') as mock_time:
        mock_time.side_effect = fake_time
        # Мокаем OpenAI ответ
        mock_client.return_value = {'result': 'mocked_result'}
        run_thread_safe('set qty', timeout=2)
        assert mock_latency_monitor.called, 'latency_monitor.record_latency не вызван'
        latency_arg = mock_latency_monitor.call_args[0][0]
        assert 10 < latency_arg < 30  # ms диапазон
        assert fake_redis.return_value.exists('cache_key') == 1
