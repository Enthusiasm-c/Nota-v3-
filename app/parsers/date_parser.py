"""
Локальный парсер для команд изменения даты без обращения к OpenAI API.
Распознает различные форматы дат и команды на естественном языке.
"""

import re
from datetime import datetime
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

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
                       или None, если команда не распознана
    """
    text = text.strip().lower()
    logger.info(f"Парсинг команды даты: {text}")
    
    # 1. Проверяем, содержит ли команда ключевые слова для даты
    is_date_command = any(word in text for word in ['дата', 'date', 'дату'])
    if not is_date_command:
        return None
    
    # 2. Пытаемся извлечь дату из различных форматов
    date_formats = [
        # DD.MM.YYYY или DD/MM/YYYY или DD-MM-YYYY
        r'(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})',
        # DD месяц YYYY (русский)
        r'(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+(\d{4}|\d{2})',
        # DD месяц YYYY (английский)
        r'(\d{1,2})\s+(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\s+(\d{4}|\d{2})'
    ]
    
    # Словари для преобразования названий месяцев в номера
    ru_months = {
        'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4, 'мая': 5, 'июня': 6,
        'июля': 7, 'августа': 8, 'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12
    }
    
    en_months = {
        'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6, 
        'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12,
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'jun': 6, 'jul': 7, 
        'aug': 8, 'sep': 9, 'sept': 9, 'oct': 10, 'nov': 11, 'dec': 12
    }
    
    for pattern in date_formats:
        match = re.search(pattern, text)
        if match:
            try:
                groups = match.groups()
                if len(groups) == 3:
                    day, month, year = groups
                    
                    # Обработка текстовых названий месяцев
                    if isinstance(month, str) and month in ru_months:
                        month = ru_months[month]
                    elif isinstance(month, str) and month in en_months:
                        month = en_months[month]
                    
                    # Преобразуем в числа
                    day = int(day)
                    month = int(month)
                    
                    # Обработка двузначного года
                    if len(str(year)) == 2:
                        # Если год двузначный, предполагаем, что это 20xx
                        year = 2000 + int(year)
                    else:
                        year = int(year)
                    
                    # Проверяем валидность даты
                    if 1 <= day <= 31 and 1 <= month <= 12 and year >= 2000:
                        # Формируем ISO-формат (YYYY-MM-DD)
                        iso_date = f"{year:04d}-{month:02d}-{day:02d}"
                        
                        # Дополнительная проверка валидности через datetime
                        try:
                            # Пытаемся создать объект datetime для проверки
                            datetime.strptime(iso_date, "%Y-%m-%d")
                            
                            # Возвращаем интент в формате OpenAI Assistant
                            logger.info(f"Распознана дата: {iso_date}")
                            return {
                                "action": "set_date",
                                "value": iso_date
                            }
                        except ValueError:
                            logger.warning(f"Невалидная дата: {iso_date}")
                            continue
            except Exception as e:
                logger.error(f"Ошибка при парсинге даты: {e}")
                continue
    
    # Если дата не распознана, но команда похожа на дату
    logger.warning(f"Команда похожа на дату, но не удалось распознать формат: {text}")
    return None 