from dataclasses import is_dataclass, asdict
import os
import logging
import json
import sys
from logging.handlers import RotatingFileHandler
from datetime import datetime
from app.trace_context import get_trace_id

LOG_PATH = os.path.join(os.path.dirname(__file__), "logs", "assistant_trace.log")

class JsonTraceFormatter(logging.Formatter):
    def format(self, record):
        trace_id = get_trace_id() or getattr(record, "trace_id", None)
        log_entry = {
            "ts": datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
            "lvl": record.levelname,
            "trace": trace_id,
            "mod": record.name,
            "msg": record.getMessage(),
        }
        
        # Добавляем информацию об исключении, если оно есть
        if record.exc_info:
            log_entry["exc_type"] = record.exc_info[0].__name__
            log_entry["exc_msg"] = str(record.exc_info[1])
            
        # Добавляем информацию о коде
        if hasattr(record, "pathname") and record.pathname:
            log_entry["file"] = record.pathname
            log_entry["line"] = record.lineno
            log_entry["func"] = record.funcName
            
        if hasattr(record, "data"):
            log_entry["data"] = record.data
            
        # Сериализуем все нестандартные типы (например, dataclass) корректно
        return json.dumps(
            log_entry,
            ensure_ascii=False,
            default=lambda o: asdict(o) if is_dataclass(o) else str(o)
        )
        
class ConsoleFormatter(logging.Formatter):
    """Форматтер для вывода в консоль и journald."""
    
    FORMATS = {
        logging.DEBUG: "\033[37m[%(levelname)s] %(name)s: %(message)s\033[0m",
        logging.INFO: "\033[1;32m[%(levelname)s] %(name)s: %(message)s\033[0m",
        logging.WARNING: "\033[1;33m[%(levelname)s] %(name)s: %(message)s\033[0m",
        logging.ERROR: "\033[1;31m[%(levelname)s] %(name)s: %(message)s\033[0m",
        logging.CRITICAL: "\033[1;37;41m[%(levelname)s] %(name)s: %(message)s\033[0m",
    }
    
    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        
        # Если есть трейс ID, добавим его в сообщение
        if hasattr(record, "trace_id") and record.trace_id:
            record.name = f"{record.name}[{record.trace_id}]"
        elif get_trace_id():
            record.name = f"{record.name}[{get_trace_id()}]"
            
        return formatter.format(record)

def setup_json_trace_logger():
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    
    # Создаем директорию для логов, если её нет
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    
    # Настраиваем ротацию файлов логов
    file_handler = RotatingFileHandler(
        LOG_PATH, 
        maxBytes=10 * 1024 * 1024,  # 10 МБ
        backupCount=10, 
        encoding="utf-8"
    )
    file_handler.setFormatter(JsonTraceFormatter())
    logger.addHandler(file_handler)
    
    # Добавляем вывод в консоль/journald
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(ConsoleFormatter())
    console_handler.setLevel(logging.INFO)  # В консоль только INFO и выше
    logger.addHandler(console_handler)
    
    return logger
