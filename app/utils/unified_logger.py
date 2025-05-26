"""
Унифицированный модуль логирования для всего приложения.
Объединяет функционал из enhanced_logger, debug_logger и timing_logger.
"""

import functools
import json
import logging
import os
import time
from contextlib import contextmanager
from datetime import date, datetime
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, TypeVar, Union

# Создаем директорию для логов
LOG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "logs"
)
os.makedirs(LOG_DIR, exist_ok=True)

# Типизация для декораторов
T = TypeVar("T")

# Глобальные логгеры для разных целей
app_logger = logging.getLogger("nota.app")
perf_logger = logging.getLogger("nota.performance")
debug_logger = logging.getLogger("nota.debug")


class UnifiedLogger:
    """Унифицированный логгер с поддержкой производительности и отладки."""
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self._initialized = True
            self.setup_logging()
    
    def setup_logging(self, log_level: str = "INFO") -> None:
        """
        Настраивает все логгеры приложения.
        
        Args:
            log_level: Уровень логирования
        """
        numeric_level = getattr(logging, log_level.upper(), logging.INFO)
        
        # Базовый формат
        base_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        date_format = "%Y-%m-%d %H:%M:%S"
        
        # Настройка основного логгера приложения
        app_handler = logging.StreamHandler()
        app_handler.setFormatter(logging.Formatter(base_format, date_format))
        app_logger.addHandler(app_handler)
        app_logger.setLevel(numeric_level)
        
        # Настройка логгера производительности
        perf_handler = logging.StreamHandler()
        perf_handler.setFormatter(
            logging.Formatter("%(asctime)s - [PERF] %(levelname)s - %(message)s", date_format)
        )
        perf_logger.addHandler(perf_handler)
        perf_logger.setLevel(logging.INFO)
        
        # Настройка отладочного логгера с записью в файл
        debug_file = os.path.join(LOG_DIR, f'debug_{datetime.now().strftime("%Y%m%d")}.log')
        debug_file_handler = logging.FileHandler(debug_file)
        debug_file_handler.setFormatter(logging.Formatter(base_format, date_format))
        debug_logger.addHandler(debug_file_handler)
        debug_logger.setLevel(logging.DEBUG)
        debug_logger.propagate = False
    
    @staticmethod
    def json_serialize(obj: Any) -> Any:
        """Сериализует объект для JSON."""
        if isinstance(obj, (date, datetime)):
            return obj.isoformat()
        elif hasattr(obj, "model_dump"):
            return obj.model_dump()
        elif hasattr(obj, "__dict__"):
            return obj.__dict__
        else:
            return str(obj)
    
    def log_operation(
        self, 
        operation: str, 
        data: Dict[str, Any], 
        level: str = "INFO",
        req_id: Optional[str] = None
    ) -> None:
        """
        Логирует операцию с данными.
        
        Args:
            operation: Название операции
            data: Данные для логирования
            level: Уровень логирования
            req_id: ID запроса
        """
        try:
            json_data = json.dumps(data, default=self.json_serialize, ensure_ascii=False)
            message = f"[{req_id or 'NO_ID'}] {operation}: {json_data}"
            getattr(app_logger, level.lower())(message)
        except Exception as e:
            app_logger.error(f"Error logging operation {operation}: {e}")
    
    def log_performance(
        self, 
        operation: str, 
        duration: float, 
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Логирует метрики производительности.
        
        Args:
            operation: Название операции
            duration: Длительность в секундах
            metadata: Дополнительные данные
        """
        message = f"{operation} took {duration:.3f}s"
        if metadata:
            message += f" | {json.dumps(metadata, default=self.json_serialize)}"
        perf_logger.info(message)
    
    def log_debug(
        self, 
        message: str, 
        data: Optional[Dict[str, Any]] = None,
        req_id: Optional[str] = None
    ) -> None:
        """
        Логирует отладочную информацию.
        
        Args:
            message: Сообщение
            data: Дополнительные данные
            req_id: ID запроса
        """
        full_message = f"[{req_id or 'NO_ID'}] {message}"
        if data:
            full_message += f" | {json.dumps(data, default=self.json_serialize)}"
        debug_logger.debug(full_message)


# Создаем единственный экземпляр
unified_logger = UnifiedLogger()


# Декораторы и контекстные менеджеры
@contextmanager
def log_timing(operation: str, req_id: Optional[str] = None, **metadata):
    """
    Контекстный менеджер для измерения времени выполнения.
    
    Usage:
        with log_timing("database_query", req_id="123"):
            # выполнить операцию
    """
    start_time = time.time()
    try:
        yield
    finally:
        duration = time.time() - start_time
        unified_logger.log_performance(
            f"[{req_id or 'NO_ID'}] {operation}", 
            duration, 
            metadata
        )


def timing_decorator(operation: Optional[str] = None):
    """
    Декоратор для измерения времени выполнения функции.
    
    Usage:
        @timing_decorator("process_image")
        def process_image(image):
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        op_name = operation or func.__name__
        
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time
                unified_logger.log_performance(op_name, duration)
        
        return wrapper
    
    return decorator


def log_exceptions(func: Callable[..., T]) -> Callable[..., T]:
    """
    Декоратор для логирования исключений.
    
    Usage:
        @log_exceptions
        def risky_operation():
            ...
    """
    @wraps(func)
    def wrapper(*args, **kwargs) -> T:
        try:
            return func(*args, **kwargs)
        except Exception as e:
            unified_logger.log_operation(
                f"Exception in {func.__name__}",
                {
                    "error": str(e),
                    "type": type(e).__name__,
                    "args": str(args),
                    "kwargs": str(kwargs)
                },
                level="ERROR"
            )
            raise
    
    return wrapper


# Специализированные функции для обратной совместимости
def log_indonesian_invoice(req_id: str, data: Dict[str, Any], phase: str = "processing") -> None:
    """Логирует информацию об индонезийских накладных."""
    unified_logger.log_operation(
        f"Indonesian invoice - {phase}",
        {
            "supplier": data.get("supplier", "Unknown"),
            "date": data.get("date", "Unknown"),
            "positions_count": len(data.get("positions", [])),
            "total_price": data.get("total_price")
        },
        req_id=req_id
    )


def log_format_issues(req_id: str, field: str, value: Any, expected: str) -> None:
    """Логирует проблемы с форматированием."""
    unified_logger.log_debug(
        f"Format issue in {field}",
        {
            "field": field,
            "value": value,
            "expected": expected
        },
        req_id=req_id
    )


def log_ocr_result(req_id: str, result: Any, metadata: Optional[Dict[str, Any]] = None) -> None:
    """Логирует результаты OCR."""
    data = {
        "success": result is not None,
        "type": type(result).__name__ if result else "None"
    }
    if metadata:
        data.update(metadata)
    
    unified_logger.log_operation(
        "OCR result",
        data,
        level="DEBUG" if result else "WARNING",
        req_id=req_id
    )


# Алиасы для обратной совместимости
setup_enhanced_logging = unified_logger.setup_logging
PerformanceTimer = log_timing  # Контекстный менеджер
time_it = timing_decorator  # Декоратор


# Экспорт основных компонентов
__all__ = [
    "unified_logger",
    "app_logger",
    "perf_logger", 
    "debug_logger",
    "log_timing",
    "timing_decorator",
    "log_exceptions",
    "log_indonesian_invoice",
    "log_format_issues",
    "log_ocr_result",
    "setup_enhanced_logging",
    "PerformanceTimer",
    "time_it"
]