"""
AI Action для мониторинга ошибок в логах бота.
Автоматически анализирует Traceback и Exception, предлагает исправления.
"""

import os
import re
import time
import logging
from typing import Optional, Dict, List, Tuple
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)

@dataclass
class ErrorContext:
    timestamp: datetime
    error_type: str
    error_message: str
    traceback: List[str]
    file_path: Optional[str]
    line_number: Optional[int]
    code_snippet: Optional[str]

class ErrorAnalyzer:
    def __init__(self, log_file: str = "bot.log"):
        self.log_file = log_file
        self.last_position = 0
        self.known_errors: Dict[str, datetime] = {}
        
    def parse_traceback(self, lines: List[str]) -> ErrorContext:
        """Парсит traceback из логов в структурированный формат."""
        error_type = ""
        error_message = ""
        traceback_lines = []
        file_path = None
        line_number = None
        code_snippet = None
        timestamp = datetime.now()
        
        for line in lines:
            # Поиск временной метки
            if match := re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})", line):
                timestamp = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S,%f")
            
            # Поиск типа ошибки и сообщения
            if "Exception" in line or "Error" in line:
                parts = line.split(": ", 1)
                if len(parts) == 2:
                    error_type = parts[0].strip()
                    error_message = parts[1].strip()
            
            # Поиск файла и номера строки
            if "File" in line and ", line" in line:
                match = re.search(r'File "([^"]+)", line (\d+)', line)
                if match:
                    file_path = match.group(1)
                    line_number = int(match.group(2))
            
            traceback_lines.append(line)
        
        return ErrorContext(
            timestamp=timestamp,
            error_type=error_type,
            error_message=error_message,
            traceback=traceback_lines,
            file_path=file_path,
            line_number=line_number,
            code_snippet=code_snippet
        )
    
    def analyze_error(self, error: ErrorContext) -> Optional[str]:
        """Анализирует ошибку и предлагает исправление."""
        if not error.error_type:
            return None
            
        # Создаем ключ для ошибки
        error_key = f"{error.file_path}:{error.line_number}:{error.error_type}"
        
        # Проверяем, не анализировали ли мы эту ошибку недавно
        if error_key in self.known_errors:
            last_time = self.known_errors[error_key]
            if (datetime.now() - last_time).total_seconds() < 300:  # 5 минут
                return None
        
        # Обновляем время последнего анализа
        self.known_errors[error_key] = datetime.now()
        
        # Анализ конкретных типов ошибок
        if "AttributeError" in error.error_type:
            if "object has no attribute" in error.error_message:
                missing_attr = re.search(r"no attribute '(\w+)'", error.error_message)
                if missing_attr:
                    return f"В файле {error.file_path} строка {error.line_number}: " \
                           f"Отсутствует атрибут '{missing_attr.group(1)}'. " \
                           f"Проверьте определение класса и инициализацию атрибута."
        
        elif "TypeError" in error.error_type:
            if "can't be used in 'await' expression" in error.error_message:
                return f"В файле {error.file_path} строка {error.line_number}: " \
                       f"Функция не является корутиной (async). " \
                       f"Уберите await или сделайте функцию асинхронной."
            
            if "object is not callable" in error.error_message:
                return f"В файле {error.file_path} строка {error.line_number}: " \
                       f"Объект не является функцией. " \
                       f"Проверьте, что вы не перезаписали функцию другим типом данных."
        
        elif "ImportError" in error.error_type or "ModuleNotFoundError" in error.error_type:
            module = re.search(r"No module named '(\w+)'", error.error_message)
            if module:
                return f"Отсутствует модуль '{module.group(1)}'. " \
                       f"Установите его через pip или проверьте путь импорта."
        
        return f"Обнаружена ошибка в {error.file_path} строка {error.line_number}: " \
               f"{error.error_type} - {error.error_message}"
    
    def monitor_log(self) -> Optional[str]:
        """Мониторит лог-файл на наличие новых ошибок."""
        try:
            if not os.path.exists(self.log_file):
                logger.warning(f"Лог-файл {self.log_file} не найден")
                return None
            
            with open(self.log_file, 'r') as f:
                # Переходим к последней известной позиции
                f.seek(self.last_position)
                
                # Читаем новые строки
                new_lines = f.readlines()
                
                # Запоминаем новую позицию
                self.last_position = f.tell()
                
                if not new_lines:
                    return None
                
                # Ищем traceback в новых строках
                traceback_lines = []
                in_traceback = False
                
                for line in new_lines:
                    if "Traceback (most recent call last)" in line:
                        in_traceback = True
                        traceback_lines = [line]
                    elif in_traceback:
                        traceback_lines.append(line)
                        if not line.startswith(" "):
                            # Конец traceback
                            error = self.parse_traceback(traceback_lines)
                            suggestion = self.analyze_error(error)
                            if suggestion:
                                return suggestion
                            in_traceback = False
                            traceback_lines = []
                
                return None
                
        except Exception as e:
            logger.error(f"Ошибка при мониторинге лога: {e}")
            return None

def start_error_monitor(log_file: str = "bot.log"):
    """Запускает мониторинг ошибок в отдельном потоке."""
    import threading
    
    def monitor_thread():
        analyzer = ErrorAnalyzer(log_file)
        logger.info(f"Запущен AI Action монитор ошибок для файла {log_file}")
        
        while True:
            try:
                suggestion = analyzer.monitor_log()
                if suggestion:
                    logger.info(f"AI Action предлагает исправление: {suggestion}")
                time.sleep(1)  # Проверяем лог каждую секунду
            except Exception as e:
                logger.error(f"Ошибка в мониторе: {e}")
                time.sleep(5)  # При ошибке делаем паузу подольше
    
    thread = threading.Thread(target=monitor_thread, daemon=True)
    thread.start()
    return thread 