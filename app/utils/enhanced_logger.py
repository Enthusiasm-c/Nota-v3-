import logging
from typing import Dict, Any
import time

# Настройка логгера для индонезийских накладных
indonesia_logger = logging.getLogger("nota.indonesia")

def setup_enhanced_logging(log_level: str = "INFO") -> None:
    """
    Настраивает расширенное логирование с дополнительными форматами и обработчиками.
    
    Args:
        log_level: Уровень логирования (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    
    # Настройка основного логгера
    logging.basicConfig(
        level=numeric_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Настройка специального логгера для индонезийских накладных
    indonesia_handler = logging.StreamHandler()
    indonesia_handler.setFormatter(
        logging.Formatter('%(asctime)s - [INDONESIA] %(levelname)s - %(message)s')
    )
    indonesia_logger.addHandler(indonesia_handler)
    indonesia_logger.setLevel(numeric_level)

def log_indonesian_invoice(req_id: str, data: Dict[str, Any], phase: str = "processing") -> None:
    """
    Логирует информацию, специфичную для индонезийских накладных.
    """
    supplier = data.get("supplier", "Unknown")
    date = data.get("date", "Unknown")
    positions_count = len(data.get("positions", []))
    indonesia_logger.info(
        f"[{req_id}] Indonesian invoice: phase={phase}, supplier='{supplier}', date={date}, positions={positions_count}"
    )
    if phase == "validation" and positions_count > 0:
        positions = data.get("positions", [])
        for i, pos in enumerate(positions):
            name = pos.get("name", "Unknown")
            qty = pos.get("qty", 0)
            price = pos.get("price", 0)
            indonesia_logger.debug(
                f"[{req_id}] Position {i+1}: name='{name}', qty={qty}, price={price}"
            )

def log_format_issues(req_id: str, field: str, value: Any, expected_format: str) -> None:
    """
    Логирует проблемы с форматами данных в индонезийских накладных.
    """
    indonesia_logger.warning(
        f"[{req_id}] Format issue: field='{field}', value='{value}', expected format: {expected_format}"
    )

def log_performance(req_id: str, operation: str, duration_ms: float) -> None:
    """
    Логирует метрики производительности для разных операций.
    """
    indonesia_logger.info(
        f"[{req_id}] Performance: operation='{operation}', duration={duration_ms:.2f}ms"
    )

class PerformanceTimer:
    """Контекстный менеджер для замера производительности операций."""
    def __init__(self, req_id: str, operation: str):
        self.req_id = req_id
        self.operation = operation
        self.start_time = None
    def __enter__(self):
        self.start_time = time.time()
        return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time:
            duration_ms = (time.time() - self.start_time) * 1000
            log_performance(self.req_id, self.operation, duration_ms) 