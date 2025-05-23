"""
Локальный парсер для команд изменения поставщика без обращения к OpenAI API.
Распознает команды изменения поставщика на русском и английском языках.
"""

import logging
import re
from typing import Any, Dict, Optional

from app.parsers.text_processor import normalize_text

logger = logging.getLogger(__name__)

# Шаблоны распознавания для команд поставщика
SUPPLIER_PATTERNS = [
    # Прямые команды
    r"^(?:supplier|поставщик)\s+(.+)$",
    # Команды с ключевыми словами
    r"(?:изменить|измени|поменять|поменяй|установить|установи|смени|сменить)\s+(?:поставщика|supplier)\s+(?:на|в|во)?\s*(.+)$",
    r"(?:поставщика|supplier)\s+(?:установить|поставь|ставь|поставить|изменить|измени)\s+(?:на|в|во)?\s*(.+)$",
    r"(?:change|set|update|modify)\s+(?:supplier|поставщика)\s+(?:to|as)?\s*(.+)$",
    r"(?:supplier|поставщика)\s+(?:set|change|update|modify)\s+(?:to|as)?\s*(.+)$",
]


def parse_supplier_command(text: str) -> Optional[Dict[str, Any]]:
    """
    Парсит команду изменения поставщика и возвращает интент.

    Поддерживаемые форматы:
    - supplier Название компании
    - поставщик Название компании
    - изменить поставщика на Название компании
    - change supplier to Название компании
    - set supplier Название компании

    Args:
        text: Текст команды пользователя

    Returns:
        Dict или None: Распознанный интент в формате {"action": "edit_supplier", "value": "название"}
    """
    # Приводим к нижнему регистру для упрощения сопоставления
    text_lower = normalize_text(text)

    logger.debug(f"Парсинг команды поставщика: '{text_lower}'")

    # Проверяем каждый шаблон
    for pattern in SUPPLIER_PATTERNS:
        match = re.search(pattern, text_lower, re.IGNORECASE)
        if match:
            supplier_name = match.group(1).strip()

            # Убираем кавычки если есть
            supplier_name = supplier_name.strip("\"'")

            if supplier_name:
                logger.debug(
                    f"Распознана команда изменения поставщика: '{text_lower}' -> '{supplier_name}'"
                )
                return {"action": "edit_supplier", "value": supplier_name, "source": "local_parser"}

    logger.debug(f"Команда поставщика не распознана для текста '{text_lower}'")
    return None
