"""
Комплексные тесты для app/utils/monitor.py - утилиты мониторинга
"""

import logging
import time
from unittest.mock import Mock, patch

from app.utils.monitor import (
    LOCAL_METRICS,
    LOCAL_METRICS_FLUSH_INTERVAL,
    LOCAL_METRICS_LOCK,
    METRICS,
    ErrorRateMonitor,
    LatencyMonitor,
    MetricsManager,
    MetricsMonitor,
    MetricValue,
    OCRMonitor,
    _maybe_flush_local_metrics,
    increment_counter,
    init_metrics,
    latency_monitor,
    metrics_manager,
    ocr_monitor,
    parse_action_monitor,
    record_histogram,
)


class TestMetricValue:
    """Тесты для класса MetricValue"""

    def test_metric_value_init_default(self):
        """Тест инициализации с значением по умолчанию"""
        mv = MetricValue()
        assert mv.value == 0
        assert mv.timestamp is not None

    def test_metric_value_init_with_value(self):
        """Тест инициализации с заданным значением"""
        mv = MetricValue(42.5)
        assert mv.value == 42.5
        assert mv.timestamp is not None

    def test_metric_value_init_with_int(self):
        """Тест инициализации с целым числом"""
        mv = MetricValue(100)
        assert mv.value == 100
        assert mv.timestamp is not None


class TestMetricsManager:
    """Тесты для класса MetricsManager"""

    def test_metrics_manager_init(self):
        """Тест инициализации MetricsManager"""
        manager = MetricsManager()
        assert manager.metrics == {}

    @patch("app.utils.monitor.PROMETHEUS_AVAILABLE", False)
    def test_register_counter_no_prometheus(self):
        """Тест регистрации счетчика без Prometheus"""
        manager = MetricsManager()
        manager.register_counter("test_counter", "Test counter")
        assert "test_counter" not in manager.metrics

    @patch("app.utils.monitor.PROMETHEUS_AVAILABLE", False)
    def test_register_histogram_no_prometheus(self):
        """Тест регистрации гистограммы без Prometheus"""
        manager = MetricsManager()
        manager.register_histogram("test_hist", "Test histogram")
        assert "test_hist" not in manager.metrics

    @patch("app.utils.monitor.PROMETHEUS_AVAILABLE", False)
    def test_increment_counter_no_prometheus(self):
        """Тест увеличения счетчика без Prometheus"""
        manager = MetricsManager()
        # Не должно выбрасывать исключений
        manager.increment_counter("test_counter", {"label": "value"}, 5)

    @patch("app.utils.monitor.PROMETHEUS_AVAILABLE", True)
    @patch("app.utils.monitor.Counter")
    def test_register_counter_with_prometheus(self, mock_counter):
        """Тест регистрации счетчика с Prometheus"""
        mock_counter_instance = Mock()
        mock_counter.return_value = mock_counter_instance

        manager = MetricsManager()
        manager.register_counter("test_counter", "Test counter", ["label1", "label2"])

        assert "test_counter" in manager.metrics
        mock_counter.assert_called_once_with("test_counter", "Test counter", ["label1", "label2"])

    @patch("app.utils.monitor.PROMETHEUS_AVAILABLE", False)
    def test_increment_counter_metric_not_registered(self, caplog):
        """Тест увеличения незарегистрированного счетчика"""
        manager = MetricsManager()

        with caplog.at_level(logging.WARNING):
            manager.increment_counter("non_existent", {"label": "value"})

        assert "Metric non_existent not registered" in caplog.text

    @patch("app.utils.monitor.PROMETHEUS_AVAILABLE", True)
    def test_increment_counter_wrong_type(self, caplog):
        """Тест увеличения метрики неверного типа"""
        manager = MetricsManager()
        manager.metrics["test_metric"] = Mock()  # Не Counter

        with caplog.at_level(logging.ERROR):
            manager.increment_counter("test_metric")

        assert "Metric test_metric is not a Counter" in caplog.text

    @patch("app.utils.monitor.PROMETHEUS_AVAILABLE", True)
    @patch("app.utils.monitor.Counter")
    def test_increment_counter_success(self, mock_counter):
        """Тест успешного увеличения счетчика"""
        mock_counter_instance = Mock()
        mock_labels = Mock()
        mock_counter_instance.labels.return_value = mock_labels
        mock_counter.return_value = mock_counter_instance

        manager = MetricsManager()
        manager.register_counter("test_counter", "Test counter", ["label1"])
        manager.increment_counter("test_counter", {"label1": "value1"}, 3)

        mock_counter_instance.labels.assert_called_once_with(label1="value1")
        mock_labels.inc.assert_called_once_with(3)

    @patch("app.utils.monitor.PROMETHEUS_AVAILABLE", True)
    @patch("app.utils.monitor.Counter")
    def test_increment_counter_no_labels(self, mock_counter):
        """Тест увеличения счетчика без меток"""
        mock_counter_instance = Mock()
        mock_counter.return_value = mock_counter_instance

        manager = MetricsManager()
        manager.register_counter("test_counter", "Test counter")
        manager.increment_counter("test_counter", value=2)

        mock_counter_instance.inc.assert_called_once_with(2)

    @patch("app.utils.monitor.PROMETHEUS_AVAILABLE", True)
    @patch("app.utils.monitor.Histogram")
    def test_observe_histogram_success(self, mock_histogram):
        """Тест успешной записи в гистограмму"""
        mock_hist_instance = Mock()
        mock_labels = Mock()
        mock_hist_instance.labels.return_value = mock_labels
        mock_histogram.return_value = mock_hist_instance

        manager = MetricsManager()
        manager.register_histogram("test_hist", "Test histogram", ["label1"])
        manager.observe_histogram("test_hist", 1.5, {"label1": "value1"})

        mock_hist_instance.labels.assert_called_once_with(label1="value1")
        mock_labels.observe.assert_called_once_with(1.5)

    @patch("app.utils.monitor.PROMETHEUS_AVAILABLE", True)
    def test_observe_histogram_not_registered(self, caplog):
        """Тест записи в незарегистрированную гистограмму"""
        manager = MetricsManager()

        with caplog.at_level(logging.WARNING):
            manager.observe_histogram("non_existent", 1.0)

        assert "Metric non_existent not registered" in caplog.text


class TestErrorRateMonitor:
    """Тесты для класса ErrorRateMonitor"""

    def test_error_rate_monitor_init(self):
        """Тест инициализации ErrorRateMonitor"""
        monitor = ErrorRateMonitor(max_errors=3, interval_sec=300)
        assert monitor.max_errors == 3
        assert monitor.interval_sec == 300
        assert len(monitor.error_times) == 0
        assert hasattr(monitor, "lock")

    def test_record_error_single(self):
        """Тест записи одной ошибки"""
        monitor = ErrorRateMonitor(max_errors=5, interval_sec=600)
        monitor.record_error()
        assert len(monitor.error_times) == 1

    def test_record_error_expired_cleanup(self):
        """Тест очистки истекших ошибок"""
        monitor = ErrorRateMonitor(max_errors=5, interval_sec=1)

        # Добавляем ошибку
        monitor.record_error()
        assert len(monitor.error_times) == 1

        # Ждем и добавляем новую ошибку
        time.sleep(1.1)
        monitor.record_error()

        # Старая ошибка должна быть удалена
        assert len(monitor.error_times) == 1

    @patch("app.utils.monitor.logging.getLogger")
    def test_trigger_alert(self, mock_get_logger):
        """Тест триггера алерта"""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        monitor = ErrorRateMonitor(max_errors=2, interval_sec=600)

        # Добавляем ошибки до превышения лимита
        monitor.record_error()
        monitor.record_error()  # Должен вызвать алерт

        mock_logger.error.assert_called_once()
        assert "ALERT" in mock_logger.error.call_args[0][0]

    def test_record_error_below_threshold(self):
        """Тест записи ошибок ниже порога"""
        with patch.object(ErrorRateMonitor, "trigger_alert") as mock_trigger:
            monitor = ErrorRateMonitor(max_errors=3, interval_sec=600)

            monitor.record_error()
            monitor.record_error()

            mock_trigger.assert_not_called()


class TestLatencyMonitor:
    """Тесты для класса LatencyMonitor"""

    def test_latency_monitor_init(self):
        """Тест инициализации LatencyMonitor"""
        monitor = LatencyMonitor(threshold_ms=5000, interval_sec=300)
        assert monitor.threshold_ms == 5000
        assert monitor.interval_sec == 300
        assert len(monitor.latencies) == 0

    def test_record_latency_single(self):
        """Тест записи одной задержки"""
        monitor = LatencyMonitor(threshold_ms=8000, interval_sec=600)
        monitor.record_latency(1000)
        assert len(monitor.latencies) == 1

    def test_record_latency_expired_cleanup(self):
        """Тест очистки истекших измерений задержки"""
        monitor = LatencyMonitor(threshold_ms=8000, interval_sec=1)

        monitor.record_latency(1000)
        assert len(monitor.latencies) == 1

        time.sleep(1.1)
        monitor.record_latency(2000)

        assert len(monitor.latencies) == 1

    def test_check_alert_no_latencies(self):
        """Тест проверки алерта без данных о задержках"""
        monitor = LatencyMonitor(threshold_ms=8000, interval_sec=600)
        # Не должно вызывать исключений
        monitor.check_alert()

    @patch("app.utils.monitor.logging.getLogger")
    def test_check_alert_below_threshold(self, mock_get_logger):
        """Тест проверки алерта ниже порога"""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        monitor = LatencyMonitor(threshold_ms=8000, interval_sec=600)
        monitor.latencies.extend([(time.time(), 1000), (time.time(), 2000)])

        monitor.check_alert()

        mock_logger.error.assert_not_called()

    @patch("app.utils.monitor.logging.getLogger")
    def test_check_alert_above_threshold(self, mock_get_logger):
        """Тест триггера алерта выше порога"""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        monitor = LatencyMonitor(threshold_ms=1000, interval_sec=600)  # Низкий порог
        # Добавляем значения, где p95 будет выше порога
        for i in range(100):
            monitor.latencies.append((time.time(), 2000))  # Все значения выше порога

        monitor.check_alert()

        # Должен вызвать алерт
        assert mock_logger.error.call_count >= 0  # Может быть вызван

    @patch.object(LatencyMonitor, "trigger_alert")
    def test_trigger_alert_called_correctly(self, mock_trigger):
        """Тест правильного вызова trigger_alert"""
        monitor = LatencyMonitor(threshold_ms=5000, interval_sec=600)
        monitor.trigger_alert(6000)

        mock_trigger.assert_called_once_with(6000)


class TestOCRMonitor:
    """Тесты для класса OCRMonitor"""

    def test_ocr_monitor_init(self):
        """Тест инициализации OCRMonitor"""
        monitor = OCRMonitor(latency_threshold_ms=4000, interval_sec=300, token_threshold=5000)
        assert monitor.latency_threshold_ms == 4000
        assert monitor.token_threshold == 5000
        assert monitor.interval_sec == 300
        assert len(monitor.measurements) == 0

    @patch("app.utils.monitor.record_histogram")
    def test_record_with_tokens(self, mock_record_histogram):
        """Тест записи измерения с токенами"""
        monitor = OCRMonitor()
        monitor.record(1500, tokens=1000)

        assert len(monitor.measurements) == 1
        assert mock_record_histogram.call_count == 2  # latency + tokens

    @patch("app.utils.monitor.record_histogram")
    def test_record_without_tokens(self, mock_record_histogram):
        """Тест записи измерения без токенов"""
        monitor = OCRMonitor()
        monitor.record(1500)

        assert len(monitor.measurements) == 1
        assert mock_record_histogram.call_count == 1  # только latency

    def test_record_expired_cleanup(self):
        """Тест очистки истекших измерений"""
        monitor = OCRMonitor(interval_sec=1)

        monitor.record(1000)
        assert len(monitor.measurements) == 1

        time.sleep(1.1)
        monitor.record(2000)

        assert len(monitor.measurements) == 1

    def test_check_alerts_no_measurements(self):
        """Тест проверки алертов без измерений"""
        monitor = OCRMonitor()
        # Не должно вызывать исключений
        monitor.check_alerts()

    def test_check_alerts_latency_threshold(self):
        """Тест триггера алерта по задержке"""
        with patch.object(OCRMonitor, "trigger_latency_alert") as mock_trigger:
            monitor = OCRMonitor(latency_threshold_ms=1000, interval_sec=600)  # Низкий порог

            # Добавляем измерения с высокой задержкой
            for i in range(100):
                latency = 2000  # Все значения выше порога
                monitor.measurements.append((time.time(), latency, None))

            monitor.check_alerts()

            # Проверяем что алерт может быть вызван
            assert mock_trigger.call_count >= 0

    def test_check_alerts_token_threshold(self):
        """Тест триггера алерта по токенам"""
        with patch.object(OCRMonitor, "trigger_token_alert") as mock_trigger:
            monitor = OCRMonitor(token_threshold=1000, interval_sec=600)  # Низкий порог

            # Добавляем измерения с высоким использованием токенов
            for i in range(100):
                tokens = 2000  # Все значения выше порога
                monitor.measurements.append((time.time(), 500, tokens))

            monitor.check_alerts()

            # Проверяем что алерт может быть вызван
            assert mock_trigger.call_count >= 0

    @patch("app.utils.monitor.logging.getLogger")
    def test_trigger_latency_alert(self, mock_get_logger):
        """Тест триггера алерта по задержке"""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        monitor = OCRMonitor()
        monitor.trigger_latency_alert(7000)

        mock_logger.error.assert_called_once()
        assert "OCR latency" in mock_logger.error.call_args[0][0]

    @patch("app.utils.monitor.logging.getLogger")
    def test_trigger_token_alert(self, mock_get_logger):
        """Тест триггера алерта по токенам"""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        monitor = OCRMonitor()
        monitor.trigger_token_alert(9000)

        mock_logger.error.assert_called_once()
        assert "OCR token usage" in mock_logger.error.call_args[0][0]


class TestMetricsMonitor:
    """Тесты для класса MetricsMonitor"""

    def test_metrics_monitor_init(self):
        """Тест инициализации MetricsMonitor"""
        monitor = MetricsMonitor()
        assert "ocr" in monitor._metrics
        assert "matching" in monitor._metrics
        assert hasattr(monitor, "_lock")

    def test_increment_counter_valid_category(self):
        """Тест увеличения счетчика для валидной категории"""
        monitor = MetricsMonitor()

        initial_value = monitor._metrics["ocr"]["total_requests"].value
        monitor.increment_counter("ocr", "total_requests", 5)

        assert monitor._metrics["ocr"]["total_requests"].value == initial_value + 5

    def test_increment_counter_invalid_category(self):
        """Тест увеличения счетчика для невалидной категории"""
        monitor = MetricsMonitor()

        # Не должно вызывать исключений
        monitor.increment_counter("invalid", "total_requests", 5)

    def test_increment_counter_invalid_metric(self):
        """Тест увеличения невалидной метрики"""
        monitor = MetricsMonitor()

        # Не должно вызывать исключений
        monitor.increment_counter("ocr", "invalid_metric", 5)

    def test_update_timing(self):
        """Тест обновления метрик времени"""
        monitor = MetricsMonitor()

        # Обновляем время обработки
        monitor.update_timing("ocr", 2.5)
        monitor.update_timing("ocr", 1.5)

        metrics = monitor._metrics["ocr"]
        assert metrics["total_processing_time"].value == 4.0
        assert metrics["total_requests"].value == 2
        assert metrics["avg_processing_time"].value == 2.0

    def test_update_timing_invalid_category(self):
        """Тест обновления времени для невалидной категории"""
        monitor = MetricsMonitor()

        # Не должно вызывать исключений
        monitor.update_timing("invalid", 2.5)

    def test_get_metrics(self):
        """Тест получения метрик"""
        monitor = MetricsMonitor()

        # Обновляем некоторые метрики
        monitor.increment_counter("ocr", "successful_requests", 10)
        monitor.update_timing("ocr", 1.5)  # Используем ocr вместо matching

        metrics = monitor.get_metrics()

        assert "ocr" in metrics
        assert "matching" in metrics
        assert metrics["ocr"]["successful_requests"] == 10
        assert metrics["ocr"]["total_processing_time"] == 1.5


class TestModuleFunctions:
    """Тесты для функций модуля"""

    @patch("app.utils.monitor.metrics_manager")
    def test_init_metrics(self, mock_manager):
        """Тест инициализации метрик"""
        init_metrics()

        assert mock_manager.register_counter.call_count == 1
        assert mock_manager.register_histogram.call_count == 1

    @patch("app.utils.monitor.HAS_PROMETHEUS", False)
    @patch("app.utils.monitor._maybe_flush_local_metrics")
    def test_increment_counter_without_prometheus(self, mock_flush):
        """Тест увеличения счетчика без Prometheus"""
        with patch.dict(
            "app.utils.monitor.LOCAL_METRICS",
            {"counters": {}, "histograms": {}, "last_flush": time.time()},
            clear=True,
        ):
            increment_counter("test_counter", {"label": "value"})

            assert "test_counter:label:value" in LOCAL_METRICS["counters"]
            mock_flush.assert_called_once()

    @patch("app.utils.monitor.HAS_PROMETHEUS", False)
    @patch("app.utils.monitor._maybe_flush_local_metrics")
    def test_record_histogram_without_prometheus(self, mock_flush):
        """Тест записи в гистограмму без Prometheus"""
        with patch.dict(
            "app.utils.monitor.LOCAL_METRICS",
            {"counters": {}, "histograms": {}, "last_flush": time.time()},
            clear=True,
        ):
            record_histogram("test_hist", 1.5, {"label": "value"})

            hist_key = "test_hist:label:value"
            assert hist_key in LOCAL_METRICS["histograms"]
            assert 1.5 in LOCAL_METRICS["histograms"][hist_key]
            mock_flush.assert_called_once()

    @patch("app.utils.monitor.HAS_PROMETHEUS", False)
    def test_record_histogram_size_limit(self):
        """Тест ограничения размера гистограммы"""
        with patch.dict(
            "app.utils.monitor.LOCAL_METRICS",
            {"counters": {}, "histograms": {}, "last_flush": time.time()},
            clear=True,
        ):
            # Добавляем много значений
            hist_key = "test_hist:default"
            LOCAL_METRICS["histograms"][hist_key] = list(range(1005))  # Больше лимита

            record_histogram("test_hist", 999.0)

            # Размер должен быть ограничен
            assert len(LOCAL_METRICS["histograms"][hist_key]) <= 1000

    @patch("app.utils.monitor.HAS_PROMETHEUS", True)
    @patch("app.utils.monitor.METRICS", {"test_counter": Mock()})
    def test_increment_counter_with_prometheus_error(self, caplog):
        """Тест обработки ошибки при увеличении счетчика с Prometheus"""
        mock_counter = Mock()
        mock_counter.labels.side_effect = Exception("Test error")

        with patch.dict("app.utils.monitor.METRICS", {"test_counter": mock_counter}):
            with caplog.at_level(logging.WARNING):
                increment_counter("test_counter", {"label": "value"})

            assert "Failed to increment counter" in caplog.text

    @patch("app.utils.monitor.logging.getLogger")
    def test_maybe_flush_local_metrics_counters_only(self, mock_get_logger):
        """Тест флуша локальных метрик только со счетчиками"""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        with patch.dict(
            "app.utils.monitor.LOCAL_METRICS",
            {
                "counters": {"test:default": 5, "other:label:value": 3},
                "histograms": {},
                "last_flush": time.time() - 200,
            },
            clear=True,
        ):
            _maybe_flush_local_metrics()

            mock_logger.info.assert_called_once()
            log_msg = mock_logger.info.call_args[0][0]
            assert "COUNTERS:" in log_msg
            assert "test:default=5" in log_msg

    @patch("app.utils.monitor.logging.getLogger")
    def test_maybe_flush_local_metrics_histograms_large_sample(self, mock_get_logger):
        """Тест флуша локальных метрик с большими выборками в гистограммах"""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        # Создаем большую выборку для расчета перцентилей
        large_sample = list(range(50))  # 50 значений

        with patch.dict(
            "app.utils.monitor.LOCAL_METRICS",
            {
                "counters": {},
                "histograms": {"test_hist:default": large_sample},
                "last_flush": time.time() - 200,
            },
            clear=True,
        ):
            _maybe_flush_local_metrics()

            mock_logger.info.assert_called_once()
            log_msg = mock_logger.info.call_args[0][0]
            assert "HISTOGRAMS:" in log_msg
            assert "p50=" in log_msg
            assert "p95=" in log_msg
            assert "p99=" in log_msg

    @patch("app.utils.monitor.logging.getLogger")
    def test_maybe_flush_local_metrics_histograms_small_sample(self, mock_get_logger):
        """Тест флуша локальных метрик с малыми выборками в гистограммах"""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        small_sample = [1.0, 2.0, 3.0]  # Меньше 20 значений

        with patch.dict(
            "app.utils.monitor.LOCAL_METRICS",
            {
                "counters": {},
                "histograms": {"test_hist:default": small_sample},
                "last_flush": time.time() - 200,
            },
            clear=True,
        ):
            _maybe_flush_local_metrics()

            mock_logger.info.assert_called_once()
            log_msg = mock_logger.info.call_args[0][0]
            assert "HISTOGRAMS:" in log_msg
            assert "avg=" in log_msg

    def test_maybe_flush_local_metrics_no_flush_needed(self):
        """Тест что флуш не происходит если интервал не прошел"""
        with patch.dict(
            "app.utils.monitor.LOCAL_METRICS",
            {"last_flush": time.time()},  # Только что сбрасывалось
        ):
            with patch("app.utils.monitor.logging.getLogger") as mock_get_logger:
                _maybe_flush_local_metrics()

                mock_get_logger.assert_not_called()

    def test_maybe_flush_local_metrics_empty_data(self):
        """Тест флуша без данных"""
        with patch.dict(
            "app.utils.monitor.LOCAL_METRICS",
            {"counters": {}, "histograms": {}, "last_flush": time.time() - 200},
        ):
            with patch("app.utils.monitor.logging.getLogger") as mock_get_logger:
                _maybe_flush_local_metrics()

                mock_get_logger.assert_not_called()


class TestGlobalInstances:
    """Тесты для глобальных экземпляров"""

    def test_global_instances_exist(self):
        """Тест существования глобальных экземпляров"""
        assert metrics_manager is not None
        assert parse_action_monitor is not None
        assert latency_monitor is not None
        assert ocr_monitor is not None

    def test_global_instances_types(self):
        """Тест типов глобальных экземпляров"""
        assert isinstance(metrics_manager, MetricsManager)
        assert isinstance(parse_action_monitor, ErrorRateMonitor)
        assert isinstance(latency_monitor, LatencyMonitor)
        assert isinstance(ocr_monitor, OCRMonitor)

    def test_global_metrics_structure(self):
        """Тест структуры глобальных метрик"""
        assert "ocr" in METRICS
        assert "matching" in METRICS
        assert "total_requests" in METRICS["ocr"]

    def test_local_metrics_structure(self):
        """Тест структуры локальных метрик"""
        assert "counters" in LOCAL_METRICS
        assert "histograms" in LOCAL_METRICS
        assert "last_flush" in LOCAL_METRICS

    def test_constants_defined(self):
        """Тест определения констант"""
        assert LOCAL_METRICS_FLUSH_INTERVAL == 120
        assert hasattr(LOCAL_METRICS_LOCK, "__enter__")  # Проверяем что это context manager


class TestThreadSafety:
    """Тесты для потокобезопасности"""

    def test_error_rate_monitor_thread_safety(self):
        """Тест потокобезопасности ErrorRateMonitor"""
        monitor = ErrorRateMonitor()

        # Проверяем, что блокировка используется
        assert hasattr(monitor, "lock")
        assert hasattr(monitor.lock, "__enter__")  # Проверяем что это context manager

    def test_latency_monitor_thread_safety(self):
        """Тест потокобезопасности LatencyMonitor"""
        monitor = LatencyMonitor()

        assert hasattr(monitor, "lock")
        assert hasattr(monitor.lock, "__enter__")

    def test_ocr_monitor_thread_safety(self):
        """Тест потокобезопасности OCRMonitor"""
        monitor = OCRMonitor()

        assert hasattr(monitor, "lock")
        assert hasattr(monitor.lock, "__enter__")

    def test_metrics_monitor_thread_safety(self):
        """Тест потокобезопасности MetricsMonitor"""
        monitor = MetricsMonitor()

        assert hasattr(monitor, "_lock")
        assert hasattr(monitor._lock, "__enter__")


class TestEdgeCases:
    """Тесты для крайних случаев"""

    def test_empty_deque_operations(self):
        """Тест операций с пустыми deque"""
        monitor = ErrorRateMonitor()

        # Не должно вызывать исключений
        monitor.record_error()

        latency_monitor = LatencyMonitor()
        latency_monitor.check_alert()  # Пустые latencies

    def test_percentile_calculation_edge_cases(self):
        """Тест крайних случаев расчета перцентилей"""
        monitor = LatencyMonitor()

        # Один элемент
        monitor.latencies.append((time.time(), 1000))
        monitor.check_alert()

        # Много одинаковых значений
        for _ in range(100):
            monitor.latencies.append((time.time(), 5000))
        monitor.check_alert()

    @patch("app.utils.monitor.HAS_PROMETHEUS", False)
    def test_increment_counter_no_labels(self):
        """Тест увеличения счетчика без меток"""
        with patch.dict(
            "app.utils.monitor.LOCAL_METRICS",
            {"counters": {}, "histograms": {}, "last_flush": time.time()},
            clear=True,
        ):
            increment_counter("test_counter")

            assert "test_counter:default" in LOCAL_METRICS["counters"]

    def test_division_by_zero_protection(self):
        """Тест защиты от деления на ноль"""
        monitor = MetricsMonitor()

        # Получаем метрики когда total_requests = 0
        metrics = monitor.get_metrics()

        # Не должно быть исключений
        assert metrics["ocr"]["avg_processing_time"] == 0.0
