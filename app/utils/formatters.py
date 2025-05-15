"""
Унифицированные функции форматирования для всего приложения.
Этот модуль содержит общие функции для форматирования данных,
которые используются в разных частях приложения.
"""

import re
import logging
from typing import Optional, Union, Dict, Any, List

# Импортируем функцию clean_num из postprocessing
from app.postprocessing import clean_num

# Реэкспортируем для унификации импортов
__all__ = ["clean_num", "format_price", "format_quantity", "parse_date"]


def format_price(value: Optional[Union[str, float, int]], currency: str = "", decimal_places: int = 2) -> str:
    """
    Форматирует ценовое значение: разделитель тысяч — обычный пробел, без знаков после запятой, опционально валюта.
    Примеры: 240 000, 5 000, 13 200
    """
    cleaned = clean_num(value)
    if cleaned is None:
        return "—"
    
    # Форматируем число как целое, без десятичных знаков
    int_value = int(round(cleaned))
    formatted = str(int_value)
    
    # Форматируем с пробелами между тысячами
    if len(formatted) > 3:
        # Разделяем число на группы по 3 цифры справа налево и соединяем пробелами
        groups = []
        for i in range(len(formatted), 0, -3):
            start = max(0, i - 3)
            groups.insert(0, formatted[start:i])
        formatted = ' '.join(groups)
    
    if currency:
        return f"{formatted} {currency}"
    return formatted


def format_quantity(value: Optional[Union[str, float, int]], 
                    unit: Optional[str] = None) -> str:
    """
    Форматирует количественное значение с единицей измерения.
    """
    cleaned = clean_num(value)
    if cleaned is None:
        return "—"
    if cleaned == int(cleaned):
        formatted = str(int(cleaned))
    else:
        formatted = str(cleaned).rstrip('0').rstrip('.') if '.' in str(cleaned) else str(cleaned)
    if unit:
        return f"{formatted} {unit}"
    return formatted


def parse_date(date_str: Optional[str]) -> Optional[str]:
    """
    Парсит дату из форматов YYYY-MM-DD, DD/MM/YYYY, DD-MM-YYYY, DD.MM.YYYY.
    Если обе первые части <= 12, трактует как день-месяц-год (DD-MM-YYYY). Американский формат не поддерживается.
    """
    if not date_str or date_str.lower() in ("none", "null", "—", "-"):
        return None
    clean_date = re.sub(r'[^\d\.\-\/]', '', date_str.strip())
    # Сначала YYYY-MM-DD
    match = re.match(r'(\d{4})[\-\/\.](\d{1,2})[\-\/\.](\d{1,2})', clean_date)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    # Затем DD.MM.YYYY, DD/MM/YYYY, DD-MM-YYYY
    match = re.match(r'(\d{1,2})[\.\-\/](\d{1,2})[\.\-\/](\d{4})', clean_date)
    if match:
        d, m, y = int(match.group(1)), int(match.group(2)), int(match.group(3))
        # Всегда трактуем как день-месяц-год
        return f"{y}-{m:02d}-{d:02d}"
    logging.warning(f"Не удалось распарсить дату: {date_str}")
    return None

# Удаляю устаревшие функции форматирования валют
