"""
Локальный парсер для команд редактирования строк без обращения к OpenAI API.
Поддерживает команды изменения цены, названия, количества и единиц измерения.
"""

import logging
import re
from typing import Any, Dict, Optional

from app.parsers.text_processor import create_error_response, normalize_text, parse_number

logger = logging.getLogger(__name__)

# Шаблоны распознавания для различных типов команд
LINE_PRICE_PATTERN = r"\b(?:line|строка)\s+(\d+)\s+(?:price|цена)\s+([\d.,]+)"
LINE_NAME_PATTERN = r"\b(?:line|строка)\s+(\d+)\s+(?:name|название|наименование)\s+([^;,.]+?)(?=\s+(?:price|цена|qty|количество|unit|единица|ед\.)|$)"
LINE_QTY_PATTERN = r"\b(?:line|строка)\s+(\d+)\s+(?:qty|quantity|количество|кол-во)\s+([\d.,]+)"
LINE_UNIT_PATTERN = r"\b(?:line|строка)\s+(\d+)\s+(?:unit|единица|ед\.|ед)\s+(\w+)"

# Формат ошибок для каждого типа команды
ERROR_MAPPINGS = {
    "price": "invalid_price_value",
    "name": "invalid_name_value",
    "qty": "invalid_qty_value",
    "unit": "invalid_unit_value",
    "line": "invalid_line_number",
}


def _convert_to_zero_based(line_num: int) -> int:
    """
    Конвертирует номер строки из 1-based в 0-based индекс.

    Args:
        line_num: Номер строки (1-based)

    Returns:
        int: Индекс строки (0-based)
    """
    return line_num - 1


def _parse_price_command(text: str, line_limit: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """
    Парсит команду изменения цены.

    Args:
        text: Текст команды
        line_limit: Максимальный номер строки (для проверки)

    Returns:
        Словарь с интентом или None
    """
    match = re.search(LINE_PRICE_PATTERN, text)
    if not match:
        return None

    try:
        # Извлекаем и проверяем номер строки
        line_num = int(match.group(1))
        if line_num < 1:
            return create_error_response("invalid_line_number")

        # Конвертируем в 0-based индекс
        line_idx = _convert_to_zero_based(line_num)

        # Проверяем границы строки, если указаны
        if line_limit is not None and line_idx >= line_limit:
            return create_error_response("line_out_of_range", line=line_idx)

        # Извлекаем цену
        price_str = match.group(2)
        price = parse_number(price_str)
        if price is None:
            return create_error_response("invalid_price_value")

        logger.debug(f"Распознана команда изменения цены: строка {line_num}, цена {price}")
        return {"action": "edit_price", "line": line_idx, "value": price, "source": "local_parser"}
    except Exception as e:
        logger.error(f"Ошибка при парсинге команды цены: {str(e)}")
        return create_error_response("invalid_price_command")


def _parse_name_command(text: str, line_limit: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """
    Парсит команду изменения названия.

    Args:
        text: Текст команды
        line_limit: Максимальный номер строки (для проверки)

    Returns:
        Словарь с интентом или None
    """
    match = re.search(LINE_NAME_PATTERN, text)
    if not match:
        return None

    try:
        # Извлекаем и проверяем номер строки
        line_num = int(match.group(1))
        if line_num < 1:
            return create_error_response("invalid_line_number")

        # Конвертируем в 0-based индекс
        line_idx = _convert_to_zero_based(line_num)

        # Проверяем границы строки, если указаны
        if line_limit is not None and line_idx >= line_limit:
            return create_error_response("line_out_of_range", line=line_idx)

        # Извлекаем название
        name = match.group(2).strip()
        if not name:
            return create_error_response("empty_name_value")

        logger.debug(f"Распознана команда изменения названия: строка {line_num}, название '{name}'")
        return {"action": "edit_name", "line": line_idx, "value": name, "source": "local_parser"}
    except Exception as e:
        logger.error(f"Ошибка при парсинге команды названия: {str(e)}")
        return create_error_response("invalid_name_command")


def _parse_qty_command(text: str, line_limit: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """
    Парсит команду изменения количества.

    Args:
        text: Текст команды
        line_limit: Максимальный номер строки (для проверки)

    Returns:
        Словарь с интентом или None
    """
    match = re.search(LINE_QTY_PATTERN, text)
    if not match:
        return None

    try:
        # Извлекаем и проверяем номер строки
        line_num = int(match.group(1))
        if line_num < 1:
            return create_error_response("invalid_line_number")

        # Конвертируем в 0-based индекс
        line_idx = _convert_to_zero_based(line_num)

        # Проверяем границы строки, если указаны
        if line_limit is not None and line_idx >= line_limit:
            return create_error_response("line_out_of_range", line=line_idx)

        # Извлекаем количество
        qty_str = match.group(2)
        qty = parse_number(qty_str)
        if qty is None:
            return create_error_response("invalid_qty_value")

        logger.debug(
            f"Распознана команда изменения количества: строка {line_num}, количество {qty}"
        )
        return {"action": "edit_quantity", "line": line_idx, "value": qty, "source": "local_parser"}
    except Exception as e:
        logger.error(f"Ошибка при парсинге команды количества: {str(e)}")
        return create_error_response("invalid_qty_command")


def _parse_unit_command(text: str, line_limit: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """
    Парсит команду изменения единицы измерения.

    Args:
        text: Текст команды
        line_limit: Максимальный номер строки (для проверки)

    Returns:
        Словарь с интентом или None
    """
    match = re.search(LINE_UNIT_PATTERN, text)
    if not match:
        return None

    try:
        # Извлекаем и проверяем номер строки
        line_num = int(match.group(1))
        if line_num < 1:
            return create_error_response("invalid_line_number")

        # Конвертируем в 0-based индекс
        line_idx = _convert_to_zero_based(line_num)

        # Проверяем границы строки, если указаны
        if line_limit is not None and line_idx >= line_limit:
            return create_error_response("line_out_of_range", line=line_idx)

        # Извлекаем единицу измерения
        unit = match.group(2).strip()
        if not unit:
            return create_error_response("empty_unit_value")

        logger.debug(
            f"Распознана команда изменения единицы измерения: строка {line_num}, единица '{unit}'"
        )
        return {"action": "edit_unit", "line": line_idx, "value": unit, "source": "local_parser"}
    except Exception as e:
        logger.error(f"Ошибка при парсинге команды единицы измерения: {str(e)}")
        return create_error_response("invalid_unit_command")


def parse_line_command(text: str, line_limit: Optional[int] = None) -> Dict[str, Any]:
    """
    Парсит команды редактирования строк и возвращает интент.

    Поддерживаемые форматы:
    - Line X price Y
    - Line X name Y
    - Line X qty Y
    - Line X unit Y

    Args:
        text: Текст команды пользователя
        line_limit: Максимальный номер строки (для проверки)

    Returns:
        Dict: Распознанный интент
    """
    # Приводим к нижнему регистру для упрощения сопоставления
    text_lower = normalize_text(text)

    logger.debug(f"Парсинг команды строки: '{text_lower}'")

    # Массив парсеров для проверки
    parsers = [_parse_price_command, _parse_name_command, _parse_qty_command, _parse_unit_command]

    # Последовательно пробуем каждый парсер
    for parser in parsers:
        result = parser(text_lower, line_limit)
        if result:
            return result

    # Если ни один парсер не сработал, возвращаем неизвестную команду
    logger.debug(f"Не удалось распознать команду строки: '{text_lower}'")
    return create_error_response(
        "unknown_command",
        user_message="I couldn't understand your command. Please try again with a simpler format.",
    )
