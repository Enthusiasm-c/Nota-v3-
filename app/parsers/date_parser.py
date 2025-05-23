"""
Локальный парсер для команд изменения даты без обращения к OpenAI API.
Распознает различные форматы дат и команды на естественном языке.
"""

import logging
import re
from datetime import datetime
from typing import Any, Dict, Optional

from app.parsers.text_processor import normalize_text

logger = logging.getLogger(__name__)

# Регулярные выражения для распознавания различных форматов даты
DATE_PATTERNS = [
    # Форматы вида DD.MM.YYYY или DD/MM/YYYY
    r"(\d{1,2})[\.\/](\d{1,2})[\.\/](\d{4})",
    # Формат вида YYYY-MM-DD (ISO)
    r"(\d{4})-(\d{1,2})-(\d{1,2})",
    # Формат вида DD месяц YYYY (русский)
    r"(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)(?:\s+|,\s*)(\d{4})",
    # Формат вида DD month YYYY (английский)
    r"(\d{1,2})\s+(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)(?:\s+|,\s*)(\d{4})",
]

# Ключевые слова для команд изменения даты
RU_CHANGE_PATTERNS = [
    r"(?:изменить|измени|поменять|поменяй|установить|установи|смени|сменить) "
    r"(?:дату|дата) (?:на|в|во)?",
    r"(?:дату|дата) (?:установить|поставь|ставь|поставить) (?:на|в|во)?",
]

EN_CHANGE_PATTERNS = [
    r"(?:change|set|update|modify) (?:date|the date) (?:to|at|as)?",
    r"(?:date) (?:set|change|update|modify) (?:to|at|as)?",
]

# Прямые команды даты
DIRECT_DATE_COMMANDS = [r"^(?:date|дата)\s+"]

# Словари для преобразования названий месяцев
RU_MONTH_MAP = {
    "января": 1,
    "февраля": 2,
    "марта": 3,
    "апреля": 4,
    "мая": 5,
    "июня": 6,
    "июля": 7,
    "августа": 8,
    "сентября": 9,
    "октября": 10,
    "ноября": 11,
    "декабря": 12,
}

EN_MONTH_MAP = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "sept": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


def _extract_numeric_date(match: re.Match) -> Optional[dict]:
    """
    Извлекает дату из числового формата (DD.MM.YYYY или YYYY-MM-DD).

    Args:
        match: Результат регулярного выражения

    Returns:
        Словарь с компонентами даты или None
    """
    try:
        groups = match.groups()

        if len(groups[0]) == 4:  # Формат YYYY-MM-DD
            year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
        else:  # Формат DD.MM.YYYY
            day, month, year = int(groups[0]), int(groups[1]), int(groups[2])

        # Проверка корректности даты
        if not (1 <= day <= 31 and 1 <= month <= 12 and 1000 <= year <= 3000):
            logger.debug(f"Некорректные значения даты: день={day}, месяц={month}, год={year}")
            return None

        # Форматируем дату в стандартный вид
        date_obj = datetime(year, month, day)
        formatted_date = date_obj.strftime("%Y-%m-%d")

        return {"day": day, "month": month, "year": year, "date": formatted_date}
    except (ValueError, TypeError) as e:
        logger.debug(f"Ошибка при извлечении числовой даты: {str(e)}")
        return None


def _extract_text_month_date(match: re.Match) -> Optional[dict]:
    """
    Извлекает дату из формата с текстовым месяцем (DD месяц YYYY).

    Args:
        match: Результат регулярного выражения

    Returns:
        Словарь с компонентами даты или None
    """
    try:
        day = int(match.group(1))
        month_name = match.group(2).lower()
        year = int(match.group(3))

        # Определяем месяц по названию
        if month_name in RU_MONTH_MAP:
            month = RU_MONTH_MAP[month_name]
        elif month_name in EN_MONTH_MAP:
            month = EN_MONTH_MAP[month_name]
        else:
            logger.debug(f"Неизвестное название месяца: {month_name}")
            return None

        # Проверка корректности даты
        if not (1 <= day <= 31 and 1 <= month <= 12 and 1000 <= year <= 3000):
            logger.debug(f"Некорректные значения даты: день={day}, месяц={month}, год={year}")
            return None

        # Форматируем дату в стандартный вид
        date_obj = datetime(year, month, day)
        formatted_date = date_obj.strftime("%Y-%m-%d")

        return {"day": day, "month": month, "year": year, "date": formatted_date}
    except (ValueError, TypeError) as e:
        logger.debug(f"Ошибка при извлечении даты с текстовым месяцем: {str(e)}")
        return None


def parse_date_str(date_str: str) -> Optional[dict]:
    """
    Парсит строку с датой в различных форматах.

    Args:
        date_str: Строка с датой в одном из поддерживаемых форматов

    Returns:
        dict: Словарь с компонентами даты или None, если парсинг не удался
    """
    # Проверяем каждый шаблон даты
    for pattern in DATE_PATTERNS:
        match = re.search(pattern, date_str)
        if not match:
            continue

        # Определяем формат и извлекаем компоненты даты
        if pattern.startswith(r"(\d{1,2})\s+"):
            # Формат с текстовым названием месяца
            return _extract_text_month_date(match)
        else:
            # Числовой формат даты
            return _extract_numeric_date(match)

    return None


def find_date_in_text(text: str) -> Optional[str]:
    """
    Ищет дату в тексте и возвращает ее как строку.

    Args:
        text: Текст для поиска даты

    Returns:
        str: Найденная дата в формате YYYY-MM-DD или None
    """
    date_info = parse_date_str(text)
    if date_info:
        return date_info["date"]
    return None


def _check_direct_date_command(text: str, date_str: str) -> Optional[Dict[str, Any]]:
    """
    Проверяет на прямую команду изменения даты (date DD.MM.YYYY).

    Args:
        text: Нормализованный текст команды
        date_str: Распознанная дата в формате YYYY-MM-DD

    Returns:
        Словарь с командой или None
    """
    for pattern in DIRECT_DATE_COMMANDS:
        if re.match(pattern, text):
            logger.debug(f"Распознана прямая команда даты: '{text}' -> {date_str}")
            return {"action": "set_date", "value": date_str, "source": "local_parser"}
    return None


def _check_ru_date_command(text: str, date_str: str) -> Optional[Dict[str, Any]]:
    """
    Проверяет на русскую команду изменения даты.

    Args:
        text: Нормализованный текст команды
        date_str: Распознанная дата в формате YYYY-MM-DD

    Returns:
        Словарь с командой или None
    """
    for pattern in RU_CHANGE_PATTERNS:
        if re.search(pattern, text):
            logger.debug(f"Распознана русская команда даты: '{text}' -> {date_str}")
            return {"action": "set_date", "value": date_str, "source": "local_parser"}
    return None


def _check_en_date_command(text: str, date_str: str) -> Optional[Dict[str, Any]]:
    """
    Проверяет на английскую команду изменения даты.

    Args:
        text: Нормализованный текст команды
        date_str: Распознанная дата в формате YYYY-MM-DD

    Returns:
        Словарь с командой или None
    """
    for pattern in EN_CHANGE_PATTERNS:
        if re.search(pattern, text):
            logger.debug(f"Распознана английская команда даты: '{text}' -> {date_str}")
            return {"action": "set_date", "value": date_str, "source": "local_parser"}
    return None


def _check_keywords(text: str, date_str: str) -> Optional[Dict[str, Any]]:
    """
    Проверяет наличие ключевых слов для даты в тексте.

    Args:
        text: Нормализованный текст команды
        date_str: Распознанная дата в формате YYYY-MM-DD

    Returns:
        Словарь с командой или None
    """
    keywords = ["дат", "date", "число", "день", "day"]
    if any(keyword in text for keyword in keywords):
        logger.debug(f"Текст содержит ключевые слова даты: '{text}' -> {date_str}")
        return {"action": "set_date", "value": date_str, "source": "local_parser"}
    return None


def parse_date_command(text: str) -> Optional[Dict[str, Any]]:
    """
    Парсит команду изменения даты и возвращает интент в формате, совместимом с OpenAI Assistant.

    Поддерживаемые форматы:
    - date DD.MM.YYYY
    - дата DD.MM.YYYY
    - дата DD месяц YYYY
    - изменить дату на DD.MM.YYYY
    - измени дату на DD.MM.YYYY
    - change date to DD.MM.YYYY
    - set date to DD.MM.YYYY

    Args:
        text: Текст команды пользователя

    Returns:
        Dict или None: Распознанный интент в формате {"action": "set_date", "value": "YYYY-MM-DD"}
    """
    # Приводим к нижнему регистру для упрощения сопоставления
    text_lower = normalize_text(text)

    # Поиск даты в тексте
    date_str = find_date_in_text(text_lower)
    if not date_str:
        logger.debug(f"Парсер даты: дата не найдена в тексте '{text_lower}'")
        return None

    # Массив проверок на различные форматы команд
    check_functions = [
        _check_direct_date_command,
        _check_ru_date_command,
        _check_en_date_command,
        _check_keywords,
    ]

    # Последовательно проверяем каждый формат
    for check_func in check_functions:
        result = check_func(text_lower, date_str)
        if result:
            return result

    logger.debug(f"Дата найдена, но команда не распознана для текста '{text_lower}'")

    # Если дата найдена, но нет чёткой команды, возвращаем None, чтобы
    # свободный парсер мог обработать команду по-своему
    return None
