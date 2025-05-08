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


def format_price(value: Optional[Union[str, float, int]], 
                 currency: str = "IDR", decimal_places: int = 0) -> str:
    """
    Форматирует ценовое значение для Индонезии: разделитель тысяч — неразрывный пробел, валюта — IDR.
    """
    cleaned = clean_num(value)
    if cleaned is None:
        return "—"
    formatted = f"{cleaned:,.0f}".replace(",", "\u202f")
    return f"{formatted} {currency}" if currency else formatted


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
    Парсит дату из индонезийских форматов в стандартный формат YYYY-MM-DD.
    Поддерживаются только YYYY-MM-DD, DD/MM/YYYY, DD-MM-YYYY.
    """
    if not date_str or date_str.lower() in ("none", "null", "—", "-"):
        return None
    clean_date = re.sub(r'[^\d\.\-\/]', '', date_str.strip())
    patterns = [
        # YYYY-MM-DD или YYYY/MM/DD
        (r'(\d{4})[\-\/\.](\d{1,2})[\-\/\.](\d{1,2})', lambda m: f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"),
        # DD.MM.YYYY или DD/MM/YYYY или DD-MM-YYYY
        (r'(\d{1,2})[\.\-\/](\d{1,2})[\.\-\/](\d{4})', lambda m: f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"),
    ]
    for pattern, formatter in patterns:
        match = re.match(pattern, clean_date)
        if match:
            try:
                return formatter(match)
            except (ValueError, IndexError):
                continue
    logging.warning(f"Не удалось распарсить дату: {date_str}")
    return None

# Удаляю устаревшие функции форматирования валют
