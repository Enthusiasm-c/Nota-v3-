"""
Пакет парсеров команд для обработки пользовательских команд.
"""

from app.parsers.command_parser import parse_command, parse_compound_command

__all__ = ['parse_command', 'parse_compound_command'] 