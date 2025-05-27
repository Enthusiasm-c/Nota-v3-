"""
Интегрированный парсер для обработки пользовательских команд.
Объединяет все локальные парсеры в один интерфейс с подробным логгированием.
"""

import logging
import re
from typing import Any, Dict, List, Optional

from app.edit.free_parser import detect_intent
from app.parsers.date_parser import parse_date_command
from app.parsers.line_parser import parse_line_command
from app.parsers.supplier_parser import parse_supplier_command
from app.parsers.text_processor import split_command
from app.utils.data_utils import normalize_text

logger = logging.getLogger(__name__)

# Шаблоны для составных команд
COMPOUND_LINE_PATTERN = r"(?:строка|line|row)\s*(\d+)\s*:(.*?)(?=(?:строка|line|row)\s*\d+\s*:|$)"
FIELD_SEPARATOR = r"(?:;|,|\s+(?:и|and)\s+)"


def _parse_compound_line_command(
    text: str, invoice_lines: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Парсит составные команды для одной строки.

    Примеры:
    - "строка 1: название Товар; цена 100; количество 5; единица шт"
    - "line 2: name Product, price 200, qty 10, unit pcs"

    Args:
        text: Текст команды
        invoice_lines: Количество строк в инвойсе

    Returns:
        List[Dict]: Список интентов
    """
    results = []

    # Ищем все составные команды
    for match in re.finditer(COMPOUND_LINE_PATTERN, text, re.IGNORECASE):
        line_num = int(match.group(1))
        if line_num < 1:
            results.append({"action": "unknown", "error": "invalid_line_number"})
            continue

        line_idx = line_num - 1
        if invoice_lines is not None and line_idx >= invoice_lines:
            results.append({"action": "unknown", "error": "line_out_of_range", "line": line_idx})
            continue

        # Разбиваем поля по разделителям
        fields_text = match.group(2).strip()
        fields = re.split(FIELD_SEPARATOR, fields_text)

        for field in fields:
            field = field.strip()
            if not field:
                continue

            # Пробуем распознать каждое поле
            field_result = parse_line_command(f"строка {line_num} {field}", invoice_lines)
            if field_result and field_result.get("action") != "unknown":
                results.append(field_result)
            else:
                logger.warning(f"Не удалось распознать поле в составной команде: '{field}'")

    return results


def parse_command(text: str, invoice_lines: Optional[int] = None) -> Dict[str, Any]:
    """
    Универсальный парсер команд, объединяющий все специализированные парсеры.

    Последовательность проверки:
    1. Парсер дат - проверяет команды изменения даты
    2. Парсер строк - проверяет команды редактирования строк
    3. Свободный парсер - обрабатывает другие команды

    Args:
        text: Текст команды пользователя
        invoice_lines: Количество строк в инвойсе для проверки границ

    Returns:
        Dict: Распознанный интент
    """
    if not text or not text.strip():
        logger.warning("Получена пустая команда")
        return {"action": "unknown", "error": "empty_command", "source": "integrated_parser"}

    normalized_text = normalize_text(text)
    logger.info(f"Парсинг команды: '{normalized_text}'")

    # 1. Проверяем через парсер дат
    date_result = parse_date_command(text)
    if date_result:
        logger.info(f"Распознана команда даты: {date_result}")
        # Добавляем source, если его нет
        if "source" not in date_result:
            date_result["source"] = "date_parser"
        return date_result

    # 2. Проверяем через парсер поставщиков
    supplier_result = parse_supplier_command(text)
    if supplier_result:
        logger.info(f"Распознана команда поставщика: {supplier_result}")
        return supplier_result

    # 3. Проверяем через парсер строк
    line_result = parse_line_command(text, invoice_lines)
    if line_result and line_result.get("action") != "unknown":
        logger.info(f"Распознана команда строки: {line_result}")
        return line_result

    # 4. Проверяем через парсер составных команд
    compound_results = _parse_compound_line_command(text, invoice_lines)
    if compound_results:
        logger.info(f"Распознаны составные команды: {compound_results}")
        # Возвращаем первый результат, остальные будут обработаны в parse_compound_command
        return compound_results[0]

    # 5. Проверяем через свободный парсер
    free_result = detect_intent(text)
    if free_result and free_result.get("action") != "unknown":
        logger.info(f"Распознана свободная команда: {free_result}")
        # Добавляем source, если его нет
        if "source" not in free_result:
            free_result["source"] = "free_parser"
        return free_result

    # Если ни один парсер не распознал команду, возвращаем ошибку
    logger.warning(f"Не удалось распознать команду: '{text}'")

    # Расширенная информация об ошибке
    if "error" in line_result:
        error_details = {
            "action": "unknown",
            "error": line_result.get("error", "unknown_command"),
            "user_message": "I didn't understand your command. Could you please try rephrasing it?",
            "source": "integrated_parser",
            "original_text": text,
        }
    else:
        error_details = {
            "action": "unknown",
            "error": "unknown_command",
            "user_message": "I didn't understand your command. Could you please try rephrasing it?",
            "source": "integrated_parser",
            "original_text": text,
        }

    return error_details


def parse_compound_command(text: str, invoice_lines: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Парсит составные команды, разбивая их на части и обрабатывая каждую часть.

    Args:
        text: Текст команды пользователя
        invoice_lines: Количество строк в инвойсе для проверки границ

    Returns:
        List[Dict]: Список распознанных интентов
    """
    # Сначала пробуем распарсить как составную команду для одной строки
    compound_results = _parse_compound_line_command(text, invoice_lines)
    if compound_results:
        logger.info(f"Распознаны составные команды для одной строки: {compound_results}")
        return compound_results

    # Если не получилось, разбиваем на части
    parts = split_command(text)
    logger.info(f"Команда разбита на {len(parts)} частей")

    results = []
    for i, part in enumerate(parts):
        logger.debug(f"Обработка части {i+1}/{len(parts)}: '{part}'")
        result = parse_command(part, invoice_lines)
        results.append(result)

    return results
