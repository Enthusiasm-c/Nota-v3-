"""
Локальный парсер для команд редактирования строк без обращения к OpenAI API.
Поддерживает команды изменения цены, названия, количества и единиц измерения.
"""

import re
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

def parse_line_command(text: str) -> Optional[Dict[str, Any]]:
    """
    Парсит команды редактирования строк и возвращает интент.
    
    Поддерживаемые форматы:
    - Line X price Y
    - Line X name Y
    - Line X qty Y
    - Line X unit Y
    
    Args:
        text: Текст команды пользователя
        
    Returns:
        Dict или None: Распознанный интент
    """
    # Приводим к нижнему регистру для упрощения сопоставления
    text_lower = text.lower().strip()
    
    # Парсинг команды изменения цены
    price_match = re.search(r"\b(?:line|строка)\s+(\d+)\s+(?:price|цена)\s+([\d.,]+)", text_lower)
    if price_match:
        try:
            line_num = int(price_match.group(1)) - 1  # Конвертируем в 0-based индекс
            price = float(price_match.group(2).replace(',', '.'))
            return {
                "action": "edit_price",
                "line": line_num,
                "value": price,
                "source": "local_parser"
            }
        except ValueError:
            return None
            
    # Парсинг команды изменения названия
    name_match = re.search(r"\b(?:line|строка)\s+(\d+)\s+(?:name|название|наименование)\s+([^;,.]+?)(?=\s+(?:price|цена|qty|количество|unit|единица|ед\.)|$)", text_lower)
    if name_match:
        try:
            line_num = int(name_match.group(1)) - 1
            name = name_match.group(2).strip()
            return {
                "action": "edit_name",
                "line": line_num,
                "value": name,
                "source": "local_parser"
            }
        except ValueError:
            return None
            
    # Парсинг команды изменения количества
    qty_match = re.search(r"\b(?:line|строка)\s+(\d+)\s+(?:qty|quantity|количество|кол-во)\s+([\d.,]+)", text_lower)
    if qty_match:
        try:
            line_num = int(qty_match.group(1)) - 1
            qty = float(qty_match.group(2).replace(',', '.'))
            return {
                "action": "edit_quantity",
                "line": line_num,
                "value": qty,
                "source": "local_parser"
            }
        except ValueError:
            return None
            
    # Парсинг команды изменения единицы измерения
    unit_match = re.search(r"\b(?:line|строка)\s+(\d+)\s+(?:unit|единица|ед\.|ед)\s+(\w+)", text_lower)
    if unit_match:
        try:
            line_num = int(unit_match.group(1)) - 1
            unit = unit_match.group(2).strip()
            return {
                "action": "edit_unit",
                "line": line_num,
                "value": unit,
                "source": "local_parser"
            }
        except ValueError:
            return None
            
    return {"action": "unknown", "user_message": "I couldn't understand your command. Please try again with a simpler format.", "source": "local_parser"} 