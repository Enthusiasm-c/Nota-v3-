"""
Фасад для локальных парсеров команд. Обеспечивает быстрый парсинг команд без обращения к OpenAI API.
"""

import logging
from typing import Dict, Any, Optional
import time

from app.parsers.date_parser import parse_date_command

logger = logging.getLogger(__name__)

def parse_command(text: str) -> Optional[Dict[str, Any]]:
    """
    Основной метод парсинга, который выбирает подходящий парсер в зависимости от текста команды.
    
    Args:
        text: Текст команды пользователя
        
    Returns:
        Dict или None: Распознанный интент или None, если команда не распознана
    """
    start_time = time.time()
    logger.info(f"Запуск локального парсера для команды: '{text}'")
    
    # Попытка парсинга команды даты
    date_intent = parse_date_command(text)
    if date_intent:
        elapsed = (time.time() - start_time) * 1000
        logger.info(f"Локальный парсер распознал дату за {elapsed:.1f} мс: {date_intent}")
        return date_intent
    
    # Здесь можно добавить вызовы других парсеров по мере их реализации
    # Например:
    # line_intent = parse_line_command(text)
    # if line_intent:
    #     return line_intent
    
    # Команда не распознана ни одним из локальных парсеров
    elapsed = (time.time() - start_time) * 1000
    logger.info(f"Локальный парсер не смог распознать команду за {elapsed:.1f} мс: '{text}'")
    return None

async def parse_command_async(text: str) -> Optional[Dict[str, Any]]:
    """
    Асинхронная обертка для парсинга команд. 
    Имеет тот же интерфейс, что и OpenAI парсер для облегчения замены.
    
    Args:
        text: Текст команды пользователя
        
    Returns:
        Dict или None: Распознанный интент или None, если команда не распознана
    """
    return parse_command(text) 