"""
Локальный парсер для команд изменения даты без обращения к OpenAI API.
Распознает различные форматы дат и команды на естественном языке.
"""

import re
from datetime import datetime
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Регулярные выражения для распознавания различных форматов даты
DATE_PATTERNS = [
    # Форматы вида DD.MM.YYYY или DD/MM/YYYY
    r'(\d{1,2})[\.\/](\d{1,2})[\.\/](\d{4})',
    # Формат вида YYYY-MM-DD (ISO)
    r'(\d{4})-(\d{1,2})-(\d{1,2})',
]

# Ключевые слова для команд изменения даты
RU_CHANGE_PATTERNS = [
    r'(?:изменить|измени|поменять|поменяй|установить|установи|смени|смената) '
    r'(?:дату|дата) (?:на|в|во)?',
    r'(?:дату|дата) (?:установить|поставь|ставь|поставить) (?:на|в|во)?',
]

EN_CHANGE_PATTERNS = [
    r'(?:change|set|update|modify) (?:date|the date) (?:to|at|as)?',
    r'(?:date) (?:set|change|update|modify) (?:to|at|as)?',
]

# Прямые команды даты
DIRECT_DATE_COMMANDS = [
    r'^(?:date|дата)\s+'
]

def parse_date_str(date_str: str) -> Optional[dict]:
    """
    Парсит строку с датой в различных форматах.
    
    Args:
        date_str: Строка с датой в одном из поддерживаемых форматов
        
    Returns:
        dict: Словарь с компонентами даты или None, если парсинг не удался
    """
    for pattern in DATE_PATTERNS:
        match = re.search(pattern, date_str)
        if not match:
            continue
            
        groups = match.groups()
        
        try:
            if len(groups[0]) == 4:  # Формат YYYY-MM-DD
                year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
            else:  # Формат DD.MM.YYYY
                day, month, year = int(groups[0]), int(groups[1]), int(groups[2])
                
            # Проверка корректности даты
            if not (1 <= day <= 31 and 1 <= month <= 12 and 1000 <= year <= 3000):
                continue
                
            # Форматируем дату в стандартный вид
            date_obj = datetime(year, month, day)
            formatted_date = date_obj.strftime('%Y-%m-%d')
            
            return {
                'day': day,
                'month': month,
                'year': year,
                'date': formatted_date
            }
        except (ValueError, TypeError):
            continue
            
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
        return date_info['date']
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
    text_lower = text.lower().strip()
    
    # Поиск даты в тексте
    date_str = find_date_in_text(text_lower)
    if not date_str:
        logger.debug(f"Парсер даты: дата не найдена в тексте '{text_lower}'")
        return None
    
    # Проверка прямых команд изменения даты
    for pattern in DIRECT_DATE_COMMANDS:
        if re.match(pattern, text_lower):
            logger.debug(f"Парсер даты: распознана прямая команда '{text_lower}' -> {date_str}")
            return {
                "action": "set_date",
                "value": date_str
            }
    
    # Проверка русских команд изменения даты
    for pattern in RU_CHANGE_PATTERNS:
        if re.search(pattern, text_lower):
            logger.debug(f"Парсер даты: распознана русская команда '{text_lower}' -> {date_str}")
            return {
                "action": "set_date",
                "value": date_str
            }
    
    # Проверка английских команд изменения даты
    for pattern in EN_CHANGE_PATTERNS:
        if re.search(pattern, text_lower):
            logger.debug(f"Парсер даты: распознана английская команда '{text_lower}' -> {date_str}")
            return {
                "action": "set_date",
                "value": date_str
            }
    
    # Если текст содержит дату, но не соответствует форматам команд,
    # смотрим, есть ли в нём ключевые слова, указывающие на изменение даты
    keywords = ['дат', 'date', 'число', 'день', 'day']
    if any(keyword in text_lower for keyword in keywords):
        logger.debug(f"Парсер даты: текст содержит ключевые слова даты '{text_lower}' -> {date_str}")
        return {
            "action": "set_date",
            "value": date_str
        }
        
    logger.debug(f"Парсер даты: команда не распознана для текста '{text_lower}'")
    return None 