"""
Модуль локальных парсеров для быстрой обработки команд без обращения к OpenAI API.
Эффективно обрабатывает простые команды, такие как изменение даты и редактирование строк.
"""

from app.parsers.local_parser import parse_command, parse_command_async
from app.parsers.date_parser import parse_date_command, find_date_in_text 

__all__ = [
    'parse_command',
    'parse_command_async',
    'parse_date_command',
    'find_date_in_text'
] 