"""
Monitoring utilities using Prometheus metrics.
"""

import logging
import time
from collections import deque
from datetime import datetime
from threading import Lock
from typing import Any, Dict, Optional, TypeVar, Union

from typing_extensions import TypedDict

# Initialize logger
logger = logging.getLogger(__name__)

# Prometheus metric classes
try:
    from prometheus_client import Counter, Histogram  # type: ignore

    HAS_PROMETHEUS = True
    PROMETHEUS_AVAILABLE = True
except ImportError:
    HAS_PROMETHEUS = False
    PROMETHEUS_AVAILABLE = False

# Monitoring metrics
METRICS: Dict[str, Dict[str, Any]] = {
    "ocr": {
        "total_requests": 0,
        "successful_requests": 0,
        "failed_requests": 0,
        "total_processing_time": 0.0,
        "avg_processing_time": 0.0,
        "last_request_time": None,
    },
    "matching": {
        "total_matches": 0,
        "successful_matches": 0,
        "failed_matches": 0,
        "total_processing_time": 0.0,
        "avg_processing_time": 0.0,
        "last_match_time": None,
    },
}

# In-memory storage for metrics when Prometheus is not available
LOCAL_METRICS = {"counters": {}, "histograms": {}, "last_flush": time.time()}
LOCAL_METRICS_LOCK = Lock()
LOCAL_METRICS_FLUSH_INTERVAL = 120  # Seconds

# Type for metric labels
MetricLabels = TypedDict("MetricLabels", {"status": str, "error": str, "supplier": str})

# Generic type for metric values
T = TypeVar("T")


class MetricValue:
    def __init__(self, value: Union[int, float] = 0) -> None:
        self.value = value
        self.timestamp = datetime.now()


class MetricsManager:
    """Manager for Prometheus metrics."""

    def __init__(self) -> None:
        self.metrics: Dict[str, Union[Counter, Histogram]] = {}

    def register_counter(
        self, name: str, description: str, labelnames: Optional[list[str]] = None
    ) -> None:
        """
        Register a new counter metric.

        Args:
            name: Metric name
            description: Metric description
            labelnames: Optional list of label names
        """
        if not PROMETHEUS_AVAILABLE:
            return

        if name not in self.metrics:
            self.metrics[name] = Counter(name, description, labelnames or [])

    def register_histogram(
        self,
        name: str,
        description: str,
        labelnames: Optional[list[str]] = None,
        buckets: Optional[list[float]] = None,
    ) -> None:
        """
        Register a new histogram metric.

        Args:
            name: Metric name
            description: Metric description
            labelnames: Optional list of label names
            buckets: Optional list of bucket boundaries
        """
        if not PROMETHEUS_AVAILABLE:
            return

        if name not in self.metrics:
            self.metrics[name] = Histogram(name, description, labelnames or [], buckets=buckets)

    def increment_counter(
        self, name: str, labels: Optional[Dict[str, str]] = None, value: float = 1
    ) -> None:
        """
        Increment a counter metric.

        Args:
            name: Metric name
            labels: Optional metric labels
            value: Value to increment by
        """
        if not PROMETHEUS_AVAILABLE:
            return

        metric = self.metrics.get(name)
        if metric is None:
            logger.warning(f"Metric {name} not registered")
            return

        if not isinstance(metric, Counter):
            logger.error(f"Metric {name} is not a Counter")
            return

        if labels:
            metric.labels(**labels).inc(value)
        else:
            metric.inc(value)

    def observe_histogram(
        self, name: str, value: float, labels: Optional[Dict[str, str]] = None
    ) -> None:
        """
        Observe a value in a histogram metric.

        Args:
            name: Metric name
            value: Value to observe
            labels: Optional metric labels
        """
        if not PROMETHEUS_AVAILABLE:
            return

        metric = self.metrics.get(name)
        if metric is None:
            logger.warning(f"Metric {name} not registered")
            return

        if not isinstance(metric, Histogram):
            logger.error(f"Metric {name} is not a Histogram")
            return

        if labels:
            metric.labels(**labels).observe(value)
        else:
            metric.observe(value)


# Global metrics manager instance
metrics_manager = MetricsManager()


def init_metrics() -> None:
    """Initialize default metrics."""
    metrics_manager.register_counter(
        "invoice_processing_total",
        "Total number of processed invoices",
        ["status", "error", "supplier"],
    )

    metrics_manager.register_histogram(
        "invoice_processing_duration_seconds",
        "Time spent processing invoices",
        ["supplier"],
        buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
    )


def increment_counter(name: str, labels: Optional[Dict[str, Any]] = None) -> None:
    """
    Increment a Prometheus counter.

    Args:
        name: The name of the counter metric
        labels: Dictionary of label values
    """
    # Default to empty dict if no labels provided
    labels = labels or {}

    # Store in local metrics when Prometheus is not available
    if not HAS_PROMETHEUS:
        with LOCAL_METRICS_LOCK:
            label_key = (
                "_".join(f"{k}:{v}" for k, v in sorted(labels.items())) if labels else "default"
            )
            counter_key = f"{name}:{label_key}"

            if counter_key not in LOCAL_METRICS["counters"]:
                LOCAL_METRICS["counters"][counter_key] = 0

            LOCAL_METRICS["counters"][counter_key] += 1

            # Maybe flush metrics to log if interval has passed
            _maybe_flush_local_metrics()
        return

    if name not in METRICS:
        return

    try:
        if isinstance(METRICS[name], Counter):
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
    # Default to empty dict if no labels provided
    labels = labels or {}

    # Store in local metrics when Prometheus is not available
    if not HAS_PROMETHEUS:
        with LOCAL_METRICS_LOCK:
            label_key = (
                "_".join(f"{k}:{v}" for k, v in sorted(labels.items())) if labels else "default"
            )
            hist_key = f"{name}:{label_key}"

            if hist_key not in LOCAL_METRICS["histograms"]:
                LOCAL_METRICS["histograms"][hist_key] = []

            LOCAL_METRICS["histograms"][hist_key].append(value)

            # Limit the size of histogram values to prevent memory issues
            if len(LOCAL_METRICS["histograms"][hist_key]) > 1000:
                LOCAL_METRICS["histograms"][hist_key] = LOCAL_METRICS["histograms"][hist_key][
                    -1000:
                ]

            # Maybe flush metrics to log if interval has passed
            _maybe_flush_local_metrics()
        return

    if name not in METRICS:
        return

    try:
        if isinstance(METRICS[name], Histogram):
            # Get histogram with labels
            METRICS[name].labels(**labels).observe(value)
    except Exception as e:
        logging.getLogger().warning(f"Failed to record histogram {name}: {str(e)}")


def _maybe_flush_local_metrics():
    """
    Flush local metrics to log if flush interval has passed.
    Should be called with LOCAL_METRICS_LOCK held.
    """
    now = time.time()
    if now - LOCAL_METRICS["last_flush"] < LOCAL_METRICS_FLUSH_INTERVAL:
        return

    # Reset flush time
    LOCAL_METRICS["last_flush"] = now

    # Prepare log message with metrics summary
    log_parts = []

    # Process counters
    if LOCAL_METRICS["counters"]:
        counter_parts = []
        for key, value in sorted(LOCAL_METRICS["counters"].items()):
            counter_parts.append(f"{key}={value}")
        log_parts.append("COUNTERS: " + ", ".join(counter_parts))

    # Process histograms - calculate percentiles
    if LOCAL_METRICS["histograms"]:
        hist_parts = []
        for key, values in sorted(LOCAL_METRICS["histograms"].items()):
            if not values:
                continue

            # Calculate percentiles
            sorted_values = sorted(values)
            n = len(sorted_values)

            if n >= 20:  # Only calculate percentiles if we have enough data
                p50_idx = max(0, int(n * 0.5) - 1)
                p95_idx = max(0, int(n * 0.95) - 1)
                p99_idx = max(0, int(n * 0.99) - 1)

                p50 = sorted_values[p50_idx]
                p95 = sorted_values[p95_idx]
                p99 = sorted_values[p99_idx]

                hist_parts.append(f"{key}: count={n}, p50={p50:.1f}, p95={p95:.1f}, p99={p99:.1f}")
            else:
                # Just report basic stats for small samples
                avg = sum(values) / max(1, len(values))
                hist_parts.append(f"{key}: count={n}, avg={avg:.1f}")

        if hist_parts:
            log_parts.append("HISTOGRAMS: " + ", ".join(hist_parts))

    # Log the metrics summary if we have data
    if log_parts:
        log_msg = "LOCAL METRICS: " + " | ".join(log_parts)
        logging.getLogger().info(log_msg)


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
            # Remove expired errors
            while self.error_times and self.error_times[0] < now - self.interval_sec:
                self.error_times.popleft()
            if len(self.error_times) >= self.max_errors:
                self.trigger_alert()

    def trigger_alert(self):
        # Can integrate with email, Telegram, Sentry, etc.
        logging.getLogger().error(
            f"[ALERT] In the last {self.interval_sec//60} minutes there were "
            f"{len(self.error_times)}+ errors ValueError: Missing 'action' field"
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
            # Remove expired values
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
            f"[ALERT] assistant_latency_ms p95={p95}ms > {self.threshold_ms}ms in the last {self.interval_sec//60} minutes"
        )


class OCRMonitor:
    """Monitor for OCR performance metrics including latency and token usage."""

    def __init__(self, latency_threshold_ms=6000, interval_sec=600, token_threshold=8000):
        self.latency_threshold_ms = latency_threshold_ms
        self.token_threshold = token_threshold
        self.interval_sec = interval_sec
        self.measurements = deque()  # (timestamp, latency_ms, tokens)
        self.lock = Lock()

    def record(self, latency_ms, tokens=None):
        """Record an OCR measurement with latency and optional token usage."""
        # Also record in Prometheus/local metrics if available
        record_histogram("nota_ocr_latency_ms", latency_ms)
        if tokens is not None:
            record_histogram("nota_ocr_tokens", tokens)

        now = time.time()
        with self.lock:
            self.measurements.append((now, latency_ms, tokens))
            # Remove expired measurements
            while self.measurements and self.measurements[0][0] < now - self.interval_sec:
                self.measurements.popleft()
            self.check_alerts()

    def check_alerts(self):
        """Check if any alert thresholds have been breached."""
        if not self.measurements:
            return

        # Extract latencies and calculate percentiles
        latencies = [lat for _, lat, _ in self.measurements]
        sorted_lat = sorted(latencies)
        p95_idx = max(0, int(len(sorted_lat) * 0.95) - 1)
        p95 = sorted_lat[p95_idx]

        # Check latency threshold
        if p95 > self.latency_threshold_ms:
            self.trigger_latency_alert(p95)

        # Extract and check token usage if available
        tokens = [t for _, _, t in self.measurements if t is not None]
        if tokens:
            sorted_tokens = sorted(tokens)
            p95_idx = max(0, int(len(sorted_tokens) * 0.95) - 1)
            p95_tokens = sorted_tokens[p95_idx]

            if p95_tokens > self.token_threshold:
                self.trigger_token_alert(p95_tokens)

    def trigger_latency_alert(self, p95):
        logging.getLogger().error(
            f"[ALERT] OCR latency p95={p95}ms > {self.latency_threshold_ms}ms "
            f"in the last {self.interval_sec//60} minutes"
        )

    def trigger_token_alert(self, p95_tokens):
        logging.getLogger().error(
            f"[ALERT] OCR token usage p95={p95_tokens} > {self.token_threshold} "
            f"in the last {self.interval_sec//60} minutes"
        )


# Global monitor for parse_assistant_output
parse_action_monitor = ErrorRateMonitor(max_errors=5, interval_sec=600)
# Global monitor for assistant_latency_ms
latency_monitor = LatencyMonitor(threshold_ms=8000, interval_sec=600)
# Global monitor for OCR performance
ocr_monitor = OCRMonitor(latency_threshold_ms=6000, interval_sec=600, token_threshold=8000)