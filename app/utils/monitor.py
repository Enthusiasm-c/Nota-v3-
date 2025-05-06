import logging
import time
from collections import deque
from threading import Lock
from typing import Dict, Any, Optional

# Prometheus metric classes
try:
    import prometheus_client as prom
    HAS_PROMETHEUS = True
except ImportError:
    HAS_PROMETHEUS = False

# Monitoring metrics
METRICS = {}

# Initialize Prometheus metrics if available
if HAS_PROMETHEUS:
    # Counter metrics
    METRICS["nota_invoices_total"] = prom.Counter(
        "nota_invoices_total",
        "Total number of processed invoices",
        ["status"]  # ok/failed
    )
    
    # Histogram metrics
    METRICS["nota_ocr_latency_ms"] = prom.Histogram(
        "nota_ocr_latency_ms",
        "OCR processing latency in milliseconds",
        buckets=(500, 1000, 2000, 5000, 10000, 15000, 30000, 60000)
    )
    
    METRICS["assistant_latency_ms"] = prom.Histogram(
        "assistant_latency_ms",
        "OpenAI Assistant latency in milliseconds",
        ["phase"],  # ocr/edits/syrve
        buckets=(500, 1000, 2000, 5000, 10000, 15000, 30000, 60000)
    )
    
    METRICS["fuzzy_suggestions"] = prom.Histogram(
        "fuzzy_suggestions",
        "Number of fuzzy match suggestions per request",
        buckets=(0, 1, 2, 3, 5, 10)
    )

def increment_counter(name: str, labels: Optional[Dict[str, Any]] = None) -> None:
    """
    Increment a Prometheus counter.
    
    Args:
        name: The name of the counter metric
        labels: Dictionary of label values
    """
    if not HAS_PROMETHEUS or name not in METRICS:
        return
    
    # Default to empty dict if no labels provided
    labels = labels or {}
    
    try:
        if isinstance(METRICS[name], prom.Counter):
            # Get counter with labels
            METRICS[name].labels(**labels).inc()
    except Exception as e:
        logging.getLogger().warning(f"Failed to increment counter {name}: {str(e)}")

def record_histogram(name: str, value: float, labels: Optional[Dict[str, Any]] = None) -> None:
    """
    Record a value in a Prometheus histogram.
    
    Args:
        name: The name of the histogram metric
        value: The value to record
        labels: Dictionary of label values
    """
    if not HAS_PROMETHEUS or name not in METRICS:
        return
    
    # Default to empty dict if no labels provided
    labels = labels or {}
    
    try:
        if isinstance(METRICS[name], prom.Histogram):
            # Get histogram with labels
            METRICS[name].labels(**labels).observe(value)
    except Exception as e:
        logging.getLogger().warning(f"Failed to record histogram {name}: {str(e)}")

# Monitor ValueError by key (e.g., 'Missing action')

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
        logging.getLogger().error(
            f"[ALERT] За последние {self.interval_sec//60} мин возникло "
            f"{len(self.error_times)}+ ошибок ValueError: Missing 'action' field"
        )

class LatencyMonitor:
    def __init__(self, threshold_ms=8000, interval_sec=600):
        self.threshold_ms = threshold_ms
        self.interval_sec = interval_sec
        self.latencies = deque()
        self.lock = Lock()

    def record_latency(self, latency_ms):
        now = time.time()
        with self.lock:
            self.latencies.append((now, latency_ms))
            # Удаляем устаревшие значения
            while self.latencies and self.latencies[0][0] < now - self.interval_sec:
                self.latencies.popleft()
            self.check_alert()

    def check_alert(self):
        if not self.latencies:
            return
        latencies_only = [lat for _, lat in self.latencies]
        sorted_lat = sorted(latencies_only)
        p95_idx = max(0, int(len(sorted_lat) * 0.95) - 1)
        p95 = sorted_lat[p95_idx]
        if p95 > self.threshold_ms:
            self.trigger_alert(p95)

    def trigger_alert(self, p95):
        logging.getLogger().error(
            f"[ALERT] assistant_latency_ms p95={p95}ms > {self.threshold_ms}ms за {self.interval_sec//60} мин"
        )

# Глобальный монитор для parse_assistant_output
parse_action_monitor = ErrorRateMonitor(max_errors=5, interval_sec=600)
# Глобальный монитор для assistant_latency_ms
latency_monitor = LatencyMonitor(threshold_ms=8000, interval_sec=600)
