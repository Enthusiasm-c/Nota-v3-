"""
Фасад для локальных парсеров команд. Обеспечивает быстрый парсинг команд без обращения к OpenAI API.
"""

import asyncio
import logging
import time
from typing import Any, Dict, Optional

from app.parsers.date_parser import parse_date_command
from app.parsers.line_parser import parse_line_command
from app.parsers.supplier_parser import parse_supplier_command

logger = logging.getLogger(__name__)


def parse_command(text: str) -> Optional[Dict[str, Any]]:
    """
    Основной метод парсинга, который выбирает подходящий парсер в зависимости от текста команды.

    Args:
        text: Текст команды пользователя

    Returns:
        Dict или None: Распознанный интент или None, если команда не распознана
    """
    from app.parsers.command_parser import parse_command as unified_parse_command
    return unified_parse_command(text)


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
