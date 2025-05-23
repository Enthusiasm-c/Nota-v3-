import logging
import time
from unittest.mock import patch

import pytest

from app.assistants.client import parse_assistant_output
from app.utils.monitor import latency_monitor, parse_action_monitor


@pytest.fixture(autouse=True)
def reset_monitor():
    # Очистить очередь ошибок перед каждым тестом
    parse_action_monitor.error_times.clear()
    yield
    parse_action_monitor.error_times.clear()


def test_monitor_triggers_alert(caplog):
    caplog.set_level(logging.ERROR)
    # Сгенерировать 5 ошибок подряд (без поля 'action')
    bad_json = '{"foo": "bar"}'
    for _ in range(5):
        result = parse_assistant_output(bad_json)
        assert result[0].action == "clarification_needed"
    # Проверить, что ALERT сработал
    alerts = [r for r in caplog.records if "[ALERT]" in r.getMessage()]
    assert alerts, "ALERT не сработал при 5 ошибках"
    assert "ошибок ValueError: Missing" in alerts[-1].getMessage()


def test_monitor_not_triggered_for_few_errors(caplog):
    caplog.set_level(logging.ERROR)
    bad_json = '{"foo": "bar"}'
    # Меньше порога
    for _ in range(3):
        result = parse_assistant_output(bad_json)
        assert result[0].action == "clarification_needed"
    alerts = [r for r in caplog.records if "[ALERT]" in r.getMessage()]
    assert not alerts, "ALERT не должен срабатывать при <5 ошибках"


def test_latency_monitor_triggers_alert_on_p95():
    # Очистить очередь латентности
    latency_monitor.latencies.clear()
    # Добавить 100 значений: 95 по 1000мс, 5 по 9001мс (p95 = 9001)
    now = time.time()
    latencies = [(now, 1000)] * 94 + [(now, 9001)] * 6
    latency_monitor.latencies.clear()
    latency_monitor.latencies.extend(latencies)
    with patch.object(latency_monitor, "trigger_alert") as mock_alert:
        latency_monitor.check_alert()
        mock_alert.assert_called_once()
        args, kwargs = mock_alert.call_args
        assert args[0] == 9001
    # Очистить очередь после теста
    latency_monitor.latencies.clear()
