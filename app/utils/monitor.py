import logging
import time
from collections import deque
from threading import Lock

# Мониторинг ValueError по ключу (например, 'Missing action')
class ErrorRateMonitor:
    def __init__(self, max_errors=5, interval_sec=600):
        self.max_errors = max_errors
        self.interval_sec = interval_sec
        self.error_times = deque()
        self.lock = Lock()

    def record_error(self):
        now = time.time()
        with self.lock:
            self.error_times.append(now)
            # Удаляем устаревшие ошибки
            while self.error_times and self.error_times[0] < now - self.interval_sec:
                self.error_times.popleft()
            if len(self.error_times) >= self.max_errors:
                self.trigger_alert()

    def trigger_alert(self):
        # Здесь можно интегрировать отправку email, Telegram, Sentry и т.д.
        logging.error(
            f"[ALERT] За последние {self.interval_sec//60} мин возникло "+
            f"{len(self.error_times)}+ ошибок ValueError: Missing 'action' field"
        )

# Глобальный монитор для parse_assistant_output
parse_action_monitor = ErrorRateMonitor(max_errors=5, interval_sec=600)
