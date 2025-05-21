"""
Базовые утилиты для обработки текста в парсерах.
Централизует предварительную обработку текста и другие общие операции.
"""

import re
import logging
from typing import Dict, Any, Optional, List, Union, Tuple

logger = logging.getLogger(__name__)

def normalize_text(text: str) -> str:
    """
    Нормализует текст: приводит к нижнему регистру, удаляет лишние пробелы.
    
    Args:
        text: Исходный текст
        
    Returns:
        Нормализованный текст
    """
    if not text:
        return ""
    return text.lower().strip()

def parse_number(value: str) -> Optional[float]:
    """
    Преобразует строку в число с учетом запятых, точек и суффиксов k/к.
    
    Args:
        value: Строка с числом, возможно с суффиксом k/к (тысячи)
        
    Returns:
        float или None при ошибке
    """
    try:
        # Приводим к нижнему регистру для упрощения обработки суффиксов
        val = value.lower().strip()
        
        # Проверяем наличие суффикса k/к (тысячи)
        has_k = 'k' in val or 'к' in val
        val = val.replace('k', '').replace('к', '').strip()
        
        # Проверяем формат числа
        if val.count(',') > 1 or val.count('.') > 1:
            logger.debug(f"Некорректный формат числа: {value}")
            return None
        
        # Преобразуем в число
        number = float(val.replace(',', '.'))
        
        # Умножаем на 1000, если был суффикс k/к
        if has_k:
            number *= 1000
        
        return number
    except ValueError:
        logger.debug(f"Не удалось преобразовать в число: {value}")
        return None
    except Exception as e:
        logger.error(f"Ошибка при обработке числа {value}: {str(e)}")
        return None

def extract_line_number(match: re.Match) -> Tuple[Optional[int], Optional[str]]:
    """
    Извлекает и проверяет номер строки из регулярного выражения.
    
    Args:
        match: Результат выполнения регулярного выражения
        
    Returns:
        Кортеж (номер строки как 0-based индекс, код ошибки или None)
    """
    try:
        line_str = match.group(1)
        line_num = int(line_str)
        
        if line_num < 1:
            return None, "line_out_of_range"
        
        # Возвращаем 0-based индекс
        return line_num - 1, None
    except (ValueError, IndexError):
        logger.debug(f"Не удалось извлечь номер строки из {match.groups()}")
        return None, "invalid_line_number"

def create_error_response(error_code: str, **kwargs) -> Dict[str, Any]:
    """
    Создает стандартизированный ответ с ошибкой.
    
    Args:
        error_code: Код ошибки
        **kwargs: Дополнительные поля для включения в ответ
        
    Returns:
        Словарь с информацией об ошибке
    """
    result = {
        "action": "unknown",
        "error": error_code,
        "source": "line_parser",  # Specific source
        "user_message_key": f"error.{error_code}"
    }
    
    params_for_translation = {}
    # Populate user_message_params based on error_code and available kwargs
    # These keys in kwargs are expected to be provided by the calling parser (e.g., line_parser.py)
    if error_code == "invalid_price_value" or error_code == "invalid_qty_value":
        if "value" in kwargs:  # The problematic value string
            params_for_translation["value"] = str(kwargs["value"])[:50]
    elif error_code == "empty_name_value":
        if "line_number" in kwargs:  # 1-based line number for user display
            params_for_translation["line_number"] = kwargs["line_number"]
    elif error_code == "line_out_of_range":
        if "line_number" in kwargs:  # The line number user provided
            params_for_translation["line_number"] = kwargs["line_number"]
        if "max_lines" in kwargs:  # Max lines in the document
            params_for_translation["max_lines"] = kwargs["max_lines"]
    elif error_code == "invalid_line_number":  # e.g. user typed "строка X"
        if "value" in kwargs:  # The "X" part (problematic line string)
             params_for_translation["value"] = str(kwargs["value"])[:50]
    # Add other specific error codes and their expected kwargs for parameters here if needed

    result["user_message_params"] = params_for_translation
    
    # Optionally, add other kwargs to the root of the result if they are essential for other logic,
    # but not for translation parameters. For now, keeping it clean.
    return result

def split_command(text: str) -> List[str]:
    """
    Разбивает составные команды на отдельные части.
    
    Args:
        text: Исходный текст команды
        
    Returns:
        Список отдельных команд
    """
    # Заменяем переносы строк на точки с запятой для единообразия
    text = text.replace("\n", ";").strip()
    
    # Результаты разбиения
    parts = []
    
    # Сначала делим по точке с запятой
    if ";" in text:
        # Разбиваем на части по точкам с запятой
        raw_parts = text.split(";")
        for part in raw_parts:
            if part.strip():
                parts.append(part.strip())
    else:
        # Если нет точек с запятой, делим по запятым и точкам, но только если они предшествуют
        # ключевым командам для строк (чтобы не разбивать числа с плавающей точкой)
        subparts = re.split(r'(?:,|\.)(?=\s*(?:строка|line|row)\s+\d+)', text)
        for subpart in subparts:
            if subpart.strip():
                parts.append(subpart.strip())
    
    if not parts:
        parts = [text]
        
    return parts 