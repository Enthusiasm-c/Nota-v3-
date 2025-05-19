"""
Модуль для измерения и логирования времени выполнения операций.
Поддерживает вложенные таймеры и уровни детализации.
"""

import logging
import time
import functools
import threading
from typing import Dict, List, Any, Optional, Callable, Union
from contextlib import contextmanager
from functools import wraps

logger = logging.getLogger(__name__)

# Глобальное хранилище таймеров по ID запроса
_timers: Dict[str, float] = {}
_timers_lock = threading.RLock()

class TimingContext:
    """
    Контекст для измерения времени выполнения операций.
    Поддерживает вложенные таймеры и детальное логирование.
    """
    def __init__(self, request_id: str, operation_name: str, parent_id: Optional[str] = None):
        """
        Инициализирует новый контекст таймера.
        
        Args:
            request_id: ID запроса для группировки таймеров
            operation_name: Название операции для логирования
            parent_id: ID родительского таймера для вложенности
        """
        self.request_id = request_id
        self.operation_name = operation_name
        self.parent_id = parent_id
        self.timer_id = f"{request_id}:{operation_name}:{id(self)}"
        self.start_time = 0.0
        self.end_time = 0.0
        self.duration = 0.0
        self.children = []
        self.metadata = {}
        
    def __enter__(self):
        """Начинает измерение времени при входе в контекст."""
        self.start()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Завершает измерение времени при выходе из контекста."""
        self.stop()
        
    def start(self, reset: bool = False):
        """
        Начинает или перезапускает таймер.
        
        Args:
            reset: Сбросить предыдущие измерения
        """
        self.start_time = time.time()
        if reset:
            self.end_time = 0.0
            self.duration = 0.0
            self.children = []
            
        # Сохраняем таймер в глобальном хранилище
        with _timers_lock:
            if self.request_id not in _timers:
                _timers[self.request_id] = {}
            _timers[self.request_id][self.timer_id] = self
            
        # Добавляем этот таймер как дочерний к родительскому
        if self.parent_id and self.parent_id in _timers.get(self.request_id, {}):
            parent = _timers[self.request_id][self.parent_id]
            parent.children.append(self)
            
        return self
        
    def stop(self):
        """Останавливает таймер и вычисляет длительность."""
        self.end_time = time.time()
        self.duration = self.end_time - self.start_time
        
        # Логируем результат
        if self.parent_id:
            logger.debug(f"[{self.request_id}] {self.operation_name} completed in {self.duration:.3f}s (child operation)")
        else:
            logger.info(f"[{self.request_id}] {self.operation_name} completed in {self.duration:.3f}s")
            
        return self.duration
        
    def checkpoint(self, checkpoint_name: str) -> float:
        """
        Отмечает промежуточную точку измерения и возвращает время от начала.
        
        Args:
            checkpoint_name: Название промежуточной точки
            
        Returns:
            Время от начала до этой точки
        """
        now = time.time()
        elapsed = now - self.start_time
        
        # Добавляем в метаданные
        if "checkpoints" not in self.metadata:
            self.metadata["checkpoints"] = {}
        self.metadata["checkpoints"][checkpoint_name] = elapsed
        
        logger.debug(f"[{self.request_id}] {self.operation_name} - {checkpoint_name}: {elapsed:.3f}s")
        return elapsed
        
    def add_metadata(self, key: str, value: Any):
        """
        Добавляет метаданные к таймеру.
        
        Args:
            key: Ключ метаданных
            value: Значение метаданных
        """
        self.metadata[key] = value
        return self
        
    def get_report(self, include_children: bool = True) -> Dict[str, Any]:
        """
        Формирует отчет о времени выполнения.
        
        Args:
            include_children: Включать ли дочерние таймеры
            
        Returns:
            Словарь с данными таймера
        """
        report = {
            "operation": self.operation_name,
            "duration": self.duration,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "metadata": self.metadata
        }
        
        if include_children and self.children:
            report["children"] = [child.get_report() for child in self.children]
            
        return report

# Глобальные функции для работы с таймерами

def start_timer(request_id: str, operation_name: str, parent_timer: Optional[TimingContext] = None) -> TimingContext:
    """
    Создает и запускает новый таймер.
    
    Args:
        request_id: ID запроса для группировки таймеров
        operation_name: Название операции для логирования
        parent_timer: Родительский таймер для вложенности
        
    Returns:
        Новый запущенный таймер
    """
    parent_id = parent_timer.timer_id if parent_timer else None
    timer = TimingContext(request_id, operation_name, parent_id)
    return timer.start()

def get_timer(request_id: str, timer_id: str) -> Optional[TimingContext]:
    """
    Получает существующий таймер по ID.
    
    Args:
        request_id: ID запроса
        timer_id: ID таймера
        
    Returns:
        Таймер или None, если не найден
    """
    with _timers_lock:
        return _timers.get(request_id, {}).get(timer_id)

def cleanup_timers(request_id: str):
    """
    Очищает все таймеры для данного запроса.
    
    Args:
        request_id: ID запроса для очистки
    """
    with _timers_lock:
        if request_id in _timers:
            del _timers[request_id]

def get_request_timers(request_id: str) -> List[TimingContext]:
    """
    Получает все таймеры для данного запроса.
    
    Args:
        request_id: ID запроса
        
    Returns:
        Список таймеров
    """
    with _timers_lock:
        return list(_timers.get(request_id, {}).values())

def get_request_timing_report(request_id: str) -> Dict[str, Any]:
    """
    Формирует полный отчет о времени выполнения запроса.
    
    Args:
        request_id: ID запроса
        
    Returns:
        Словарь с данными всех таймеров запроса
    """
    # Получаем только корневые таймеры (без родителей)
    timers = get_request_timers(request_id)
    root_timers = [t for t in timers if not t.parent_id]
    
    return {
        "request_id": request_id,
        "total_timers": len(timers),
        "root_timers": [t.get_report() for t in root_timers]
    }

# Декораторы для измерения времени

def timed(request_id_arg: Union[str, int, Callable] = None, operation_name: Optional[str] = None):
    """
    Декоратор для измерения времени выполнения функции.
    
    Args:
        request_id_arg: Аргумент функции, содержащий ID запроса, или функция получения ID
        operation_name: Название операции (по умолчанию - имя функции)
        
    Returns:
        Декорированная функция
    """
    def decorator(func):
        func_name = operation_name or func.__name__
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Определяем ID запроса
            if isinstance(request_id_arg, (str, int)):
                # Если передана строка/число - это имя аргумента
                req_id = kwargs.get(request_id_arg) if request_id_arg in kwargs else args[request_id_arg]
            elif callable(request_id_arg):
                # Если передана функция - вызываем ее для получения ID
                req_id = request_id_arg(*args, **kwargs)
            else:
                # По умолчанию используем имя функции и timestamp
                req_id = f"{func.__name__}_{int(time.time())}"
                
            # Запускаем таймер
            with TimingContext(req_id, func_name) as timer:
                result = func(*args, **kwargs)
                logger.debug(f"Function {func_name} completed in {timer.duration:.2f}s")
                return result
                
        return wrapper
        
    # Если декоратор вызван без аргументов
    if callable(request_id_arg) and operation_name is None:
        func = request_id_arg
        request_id_arg = None
        return decorator(func)
        
    return decorator

def async_timed(request_id_arg: Union[str, int, Callable] = None, operation_name: Optional[str] = None):
    """
    Декоратор для измерения времени выполнения асинхронной функции.
    
    Args:
        request_id_arg: Аргумент функции, содержащий ID запроса, или функция получения ID
        operation_name: Название операции (по умолчанию - имя функции)
        
    Returns:
        Декорированная асинхронная функция
    """
    def decorator(func):
        func_name = operation_name or func.__name__
        
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Определяем ID запроса
            if isinstance(request_id_arg, (str, int)):
                # Если передана строка/число - это имя аргумента
                req_id = kwargs.get(request_id_arg) if request_id_arg in kwargs else args[request_id_arg]
            elif callable(request_id_arg):
                # Если передана функция - вызываем ее для получения ID
                req_id = request_id_arg(*args, **kwargs)
            else:
                # По умолчанию используем имя функции и timestamp
                req_id = f"{func.__name__}_{int(time.time())}"
                
            # Запускаем таймер
            with TimingContext(req_id, func_name) as timer:
                result = await func(*args, **kwargs)
                logger.debug(f"Async function {func_name} completed in {timer.duration:.2f}s")
                return result
                
        return wrapper
        
    # Если декоратор вызван без аргументов
    if callable(request_id_arg) and operation_name is None:
        func = request_id_arg
        request_id_arg = None
        return decorator(func)
        
    return decorator

# Контекстный менеджер для таймера
@contextmanager
def operation_timer(request_id: str, operation_name: str, parent_timer: Optional[TimingContext] = None):
    """
    Контекстный менеджер для измерения времени операции.
    
    Args:
        request_id: ID запроса
        operation_name: Название операции
        parent_timer: Родительский таймер
        
    Yields:
        Таймер для использования внутри контекста
    """
    timer = start_timer(request_id, operation_name, parent_timer)
    try:
        yield timer
    finally:
        timer.stop()

def timing_decorator(
    name: str,
    request_id_arg: Optional[Union[str, int, Callable[..., Any]]] = None
) -> Callable:
    """
    Decorator for timing function execution.
    
    Args:
        name: Name for the timing log
        request_id_arg: Argument to use as request ID
        
    Returns:
        Decorated function
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Get request ID if specified
            req_id: Optional[Union[str, int]] = None
            if request_id_arg is not None:
                if isinstance(request_id_arg, (str, int)):
                    req_id = str(request_id_arg)
                elif callable(request_id_arg):
                    req_id = str(request_id_arg(*args, **kwargs))
                    
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time
                if req_id:
                    logger.info(f"{name} completed in {duration:.3f}s [req_id={req_id}]")
                else:
                    logger.info(f"{name} completed in {duration:.3f}s")
        return wrapper
    return decorator

def async_timing_decorator(
    name: str,
    request_id_arg: Optional[Union[str, int, Callable[..., Any]]] = None
) -> Callable:
    """
    Async version of timing decorator.
    
    Args:
        name: Name for the timing log
        request_id_arg: Argument to use as request ID
        
    Returns:
        Decorated async function
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Get request ID if specified
            req_id: Optional[Union[str, int]] = None
            if request_id_arg is not None:
                if isinstance(request_id_arg, (str, int)):
                    req_id = str(request_id_arg)
                elif callable(request_id_arg):
                    req_id = str(request_id_arg(*args, **kwargs))
                    
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time
                if req_id:
                    logger.info(f"{name} completed in {duration:.3f}s [req_id={req_id}]")
                else:
                    logger.info(f"{name} completed in {duration:.3f}s")
        return wrapper
    return decorator