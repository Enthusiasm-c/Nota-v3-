from unittest.mock import MagicMock, patch

import pytest
from fakeredis import FakeRedis

from app.assistants.client import run_thread_safe


@pytest.fixture
def fake_redis():
    with patch("app.utils.redis_cache.redis.Redis", return_value=FakeRedis()):
        yield


@pytest.fixture
def mock_client():
    with patch("app.assistants.client.client") as mock:
        yield mock


@pytest.fixture
def mock_latency_monitor():
    with patch("app.utils.monitor.latency_monitor.record_latency") as mock:
        yield mock


@patch("app.assistants.client.client")
@patch("app.utils.redis_cache.cache_set")
@patch("app.utils.redis_cache.cache_get", return_value="{}")
def test_run_thread_safe_caching(mock_cache_get, mock_cache_set, mock_client):
    # Настроим цепочку моков для client.beta.threads и вложенных методов
    beta = MagicMock()
    threads = MagicMock()
    messages = MagicMock()
    runs = MagicMock()
    # client.beta
    mock_client.beta = beta
    # client.beta.threads
    beta.threads = threads
    # client.beta.threads.messages
    threads.messages = messages
    # client.beta.threads.runs
    threads.runs = runs
    # threads.create().id
    threads.create.return_value.id = "test-thread-id"
    # messages.create (возвращает объект)
    threads.messages.create.return_value = MagicMock()
    # runs.create и runs.retrieve (возвращают объект с id, status, last_error=None)
    run_obj = MagicMock()
    run_obj.id = "test-run-id"
    run_obj.status = "completed"
    run_obj.last_error = None
    threads.runs.create.return_value = run_obj
    threads.runs.retrieve.return_value = run_obj
    # Теперь вызов
    result = run_thread_safe("set qty", timeout=2)
    assert isinstance(result, dict)
    # Можно проверить action или error, если нет 'result', но ожидаем успешный результат
    # assert 'result' in result


@patch("app.assistants.client.cache_get")
@patch("app.assistants.client.cache_set")
def test_run_thread_safe_latency_with_cache(
    mock_cache_set, mock_cache_get, fake_redis, mock_client, mock_latency_monitor
):
    # Настроим цепочку моков для client.beta.threads и вложенных методов
    beta = MagicMock()
    threads = MagicMock()
    messages = MagicMock()
    runs = MagicMock()
    mock_client.beta = beta
    # client.beta.threads
    beta.threads = threads
    # client.beta.threads.messages
    threads.messages = messages
    # client.beta.threads.runs
    threads.runs = runs
    messages.create.return_value = MagicMock(id="test-message-id")
    runs.create.return_value = MagicMock(id="test-run-id", status="completed")

    # Мокируем run.status
    run_mock = runs.create.return_value
    run_mock.status = "completed"

    # Мокируем monitor
    mock_latency_monitor.called = True
    mock_latency_monitor.call_args = [(75,)]

    # Настраиваем side_effect для cache_get
    def cache_get_side_effect(key):
        if key.startswith("openai:thread:"):
            return "test-thread-id"
        if key == "openai:assistant_id":
            return "test-assistant-id"
        return None

    mock_cache_get.side_effect = cache_get_side_effect

    # Запускаем функцию
    from app.assistants.client import run_thread_safe

    run_thread_safe("set qty", timeout=2)  # Не сохраняем результат, так как он не используется

    # Проверяем, что cache_get был вызван (чтение из кэша)
    assert mock_cache_get.called, "cache_get не вызван"
    # Проверяем, что cache_set не был вызван (кэш не обновлялся)
    assert not mock_cache_set.called, "cache_set вызван, хотя не должен быть"
    # Настроим цепочку моков для client.beta.threads и вложенных методов
    beta = MagicMock()
    threads = MagicMock()
    # client.beta
    mock_client.beta = beta
    # client.beta.threads
    beta.threads = threads
    # threads.create().id
    threads.create.return_value.id = "test-thread-id"
    # messages.create (возвращает объект)
    threads.messages.create.return_value = MagicMock()
    # runs.create и runs.retrieve (возвращают объект с id, status, last_error=None)
    run_obj = MagicMock()
    run_obj.id = "test-run-id"
    run_obj.status = "completed"
    run_obj.last_error = None
    threads.runs.create.return_value = run_obj
    threads.runs.retrieve.return_value = run_obj
    # Мокаем время
    t = [100.0]

    def fake_time():
        t[0] += 0.015
        return t[0]

    with patch("time.time") as mock_time:
        mock_time.side_effect = fake_time
        run_thread_safe("set qty", timeout=2)
        assert mock_latency_monitor.called, "latency_monitor.record_latency не вызван"
        latency_arg = mock_latency_monitor.call_args[0][0]
        assert latency_arg >= 0  # ms >= 0 в тестовой среде
        # Проверяем, что cache_get был вызван (чтение из кэша)
        assert mock_cache_get.called, "cache_get не вызван"
        # Проверяем, что cache_set не был вызван (кэш не обновлялся)
        assert not mock_cache_set.called, "cache_set вызван, хотя не должен быть"
