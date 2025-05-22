"""
Парсер для общих команд, таких как установка поставщика или общей суммы инвойса.
"""
import re
import logging
from typing import Dict, Any, Optional

# Вспомогательная функция для парсинга чисел, включая 'k'/'к' суффиксы.
# Эта функция должна быть в app.parsers.text_processor, но для изоляции этого модуля,
# и так как text_processor.py не должен изменяться в этом сабтаске,
# мы временно определим ее здесь или будем полагаться на будущую доступность.
# Для текущей задачи, если text_processor.parse_number доступен, он будет импортирован.
try:
    from app.parsers.text_processor import parse_number
except ImportError:
    # Этот логгер будет инициализирован, только если импорт не удался.
    _logger_general_parser_fallback = logging.getLogger(__name__ + ".fallback_parse_number")
    _logger_general_parser_fallback.warning(
        "parse_number from app.parsers.text_processor not found. "
        "Using a basic local implementation for parse_total_command. "
    )
    def parse_number(value: str) -> Optional[float]: 
        try:
            cleaned_value = value.strip().replace(',', '.')
            multiplier = 1.0
            if 'k' in cleaned_value.lower() or 'к' in cleaned_value.lower():
                multiplier = 1000.0
                cleaned_value = cleaned_value.lower().replace('k', '').replace('к', '').strip()
            
            # Проверка, что строка действительно представляет собой число после очистки
            if not re.fullmatch(r"-?\d+(\.\d+)?", cleaned_value):
                 _logger_general_parser_fallback.debug(f"Fallback parse_number: Non-numeric value after cleaning '{value}'.")
                 return None

            num = float(cleaned_value)
            return num * multiplier
        except ValueError:
            _logger_general_parser_fallback.debug(f"Fallback parse_number: ValueError for '{value}'.")
            return None

logger = logging.getLogger(__name__)

def parse_supplier_command(text: str) -> Optional[Dict[str, Any]]:
    """
    Парсит команду установки поставщика.
    Примеры: "поставщик ООО Ромашка", "supplier ACME Corp",
             "изменить поставщика на ЗАО Вектор", "change supplier to Bubba Gump"
    """
    patterns = [
        re.compile(r"^(?:поставщик|supplier)\s+(.+)", re.IGNORECASE),
        re.compile(r"^(?:изменить\s+поставщика\s+на|change\s+supplier\s+to)\s+(.+)", re.IGNORECASE)
    ]

    for pattern in patterns:
        match = pattern.match(text) # text уже нормализован в command_parser
        if match:
            supplier_name = match.group(1).strip()
            if supplier_name: 
                # Дополнительная проверка, чтобы избежать ситуации "поставщик поставщик"
                if supplier_name.lower() in ["поставщик", "supplier"] and text.strip().lower() == supplier_name.lower():
                     logger.debug(f"Command 'set_supplier' found, but value is the keyword itself: '{text}'")
                     return {"action": "unknown", "error": "empty_supplier_name", "original_text": text, "source": "general_parser"}

                logger.info(f"Parsed 'set_supplier' command. Supplier: '{supplier_name}'")
                return {"action": "set_supplier", "supplier": supplier_name, "source": "general_parser"}
            else:
                logger.debug(f"Command 'set_supplier' found, but supplier name is empty: '{text}'")
                return {"action": "unknown", "error": "empty_supplier_name", "original_text": text, "source": "general_parser"}
            
    return None

def parse_total_command(text: str) -> Optional[Dict[str, Any]]:
    """
    Парсит команду установки общей суммы инвойса.
    Примеры: "общая сумма 123.45", "total 5000", "итого 100к"
    """
    # text уже нормализован в command_parser
    match = re.search(r"(?:общая\s+сумма|итого|total(?:amount)?)\s*([\d.,]+\s*[kк]?)", text, re.IGNORECASE)
    
    if match:
        total_value_str = match.group(1).strip()
        if not total_value_str: 
            logger.debug(f"Команда общей суммы найдена, но значение отсутствует: '{text}'")
            return {"action": "unknown", "error": "empty_total_value", "original_text": text, "source": "general_parser"}

        total_amount = parse_number(total_value_str) 

        if total_amount is not None:
            logger.info(f"Parsed 'set_total' command. Amount: {total_amount}")
            return {"action": "set_total", "total": total_amount, "source": "general_parser"}
        else:
            logger.warning(f"Failed to convert '{total_value_str}' to number for total amount. Command: '{text}'")
            return {"action": "unknown", "error": "invalid_total_value", "original_value": total_value_str, "source": "general_parser"}
            
    return None
