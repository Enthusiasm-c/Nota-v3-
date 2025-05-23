"""
Фасад для локальных парсеров команд. Обеспечивает быстрый парсинг команд без обращения к OpenAI API.
"""

import logging
from typing import Dict, Any, Optional
import time
import asyncio

from app.parsers.date_parser import parse_date_command
from app.parsers.line_parser import parse_line_command

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
    date_result = parse_date_command(text)
    if date_result:
        elapsed_ms = (time.time() - start_time) * 1000
        logger.info(f"Локальный парсер обработал команду даты за {elapsed_ms:.1f} мс: {date_result}")
        return date_result
        
    # Попытка парсинга команды редактирования строки
    line_result = parse_line_command(text)
    if line_result:
        elapsed_ms = (time.time() - start_time) * 1000
        logger.info(f"Локальный парсер обработал команду редактирования строки за {elapsed_ms:.1f} мс: {line_result}")
        return line_result
    
    # Если ни один парсер не сработал
    elapsed_ms = (time.time() - start_time) * 1000
    logger.info(f"Локальный парсер не смог распознать команду за {elapsed_ms:.1f} мс")
    return {
        "action": "unknown",
        "user_message": "I couldn't understand your command. Please try again with a simpler format.",
        "source": "local_parser"
    }

async def parse_command_async(text: str) -> Optional[Dict[str, Any]]:
    """
    Асинхронная версия метода парсинга для использования в асинхронных контекстах.
    
    Args:
        text: Текст команды пользователя
        
    Returns:
        Dict или None: Распознанный интент или None, если команда не распознана
    """
    # Запускаем синхронную функцию в отдельном потоке, чтобы не блокировать event loop
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, parse_command, text) 