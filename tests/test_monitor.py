import logging
import time
import pytest
from app.assistants.client import parse_assistant_output
from app.utils.monitor import parse_action_monitor

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
        with pytest.raises(Exception):
            parse_assistant_output(bad_json)
    # Проверить, что ALERT сработал
    alerts = [r for r in caplog.records if '[ALERT]' in r.getMessage()]
    assert alerts, 'ALERT не сработал при 5 ошибках'
    assert 'ошибок ValueError: Missing' in alerts[-1].getMessage()

def test_monitor_not_triggered_for_few_errors(caplog):
    caplog.set_level(logging.ERROR)
    bad_json = '{"foo": "bar"}'
    # Меньше порога
    for _ in range(3):
        with pytest.raises(Exception):
            parse_assistant_output(bad_json)
    alerts = [r for r in caplog.records if '[ALERT]' in r.getMessage()]
    assert not alerts, 'ALERT не должен срабатывать при <5 ошибках'
