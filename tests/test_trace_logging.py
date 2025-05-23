"""
Тесты для логирования с трассировкой.
"""

import logging

import pytest

from app.assistants.client import run_thread_safe
from app.trace_context import get_request_id, reset_request_id, set_request_id


@pytest.fixture(autouse=True)
def cleanup_trace():
    """
    Очищает контекст трассировки после каждого теста.
    """
    yield
    reset_request_id()


def test_trace_context():
    """
    Тест установки и получения ID запроса.
    """
    # Изначально ID не установлен
    assert get_request_id() is None

    # Устанавливаем ID
    test_id = "test-123"
    set_request_id(test_id)
    assert get_request_id() == test_id

    # Сбрасываем ID
    reset_request_id()
    assert get_request_id() is None


@pytest.fixture(autouse=True)
def set_test_trace_id():
    # Устанавливаем тестовый trace_id для каждого теста
    set_request_id("test-trace-id-12345")
    yield


def test_run_thread_safe_logs_error_traceid(caplog):
    # Перенаправляем логи в caplog
    logger = logging.getLogger("app.assistants.trace_openai")
    for h in logger.handlers[:]:
        logger.removeHandler(h)
    logger.addHandler(logging.StreamHandler(caplog.handler.stream))
    logger.setLevel(logging.INFO)
    caplog.set_level(logging.INFO)
    try:
        run_thread_safe("строка 1 цена 1000")
    except Exception:
        pass
    found = False
    for record in caplog.records:
        if getattr(record, "trace_id", None) == "test-trace-id-12345":
            found = True
            break
        if hasattr(record, "extra") and isinstance(record.extra, dict):
            if record.extra.get("trace_id") == "test-trace-id-12345":
                found = True
                break
        if "test-trace-id-12345" in str(record.__dict__):
            found = True
            break
    assert found, "trace_id должен быть в log record даже при ошибке"
