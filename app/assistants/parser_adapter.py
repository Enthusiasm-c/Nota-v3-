"""
Адаптер для интеграции новой системы парсеров с существующим кодом.
Обеспечивает обратную совместимость с функцией parse_edit_command.
"""

import logging
from typing import Dict, Any, Optional, List, Union

from app.parsers.command_parser import parse_compound_command
# Removed: from app.assistants.client import parse_edit_command as legacy_parse_edit_command

logger = logging.getLogger(__name__)

def adapt_intent(intent: Dict[str, Any]) -> Dict[str, Any]:
    """
    Адаптирует интент от новых парсеров к формату, ожидаемому старым кодом.
    
    Args:
        intent: Интент от новых парсеров
        
    Returns:
        Интент в формате, совместимом со старым кодом
    """
    action = intent.get("action", "unknown")
    result = {"action": action}
    
    # Адаптация действий для строк
    if action == "edit_name":
        result["action"] = "set_name"
        result["line"] = intent.get("line", 0) # Already 0-based from new parser
        result["name"] = intent.get("value")
    elif action == "edit_price":
        result["action"] = "set_price"
        result["line"] = intent.get("line", 0) # Already 0-based from new parser
        result["price"] = intent.get("value")
    elif action == "edit_quantity":
        result["action"] = "set_qty"
        result["line"] = intent.get("line", 0) # Already 0-based from new parser
        result["qty"] = intent.get("value")
    elif action == "edit_unit":
        result["action"] = "set_unit"
        result["line"] = intent.get("line", 0) # Already 0-based from new parser
        result["unit"] = intent.get("value")
    elif action == "set_date":
        # Прямое копирование даты
        result["date"] = intent.get("value")
    elif action == "unknown":
        # Копируем ошибку и сообщение пользователю
        result["error"] = intent.get("error", "unknown_command")
        result["user_message"] = intent.get("user_message", "I couldn't understand your command.")
    else:
        # Для других действий просто копируем все поля
        result.update(intent)
        
    return result

def parse_edit_command_enhanced(user_input: str, invoice_lines: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Улучшенная версия parse_edit_command с использованием новой системы парсеров.
    Обеспечивает обратную совместимость с существующим кодом.
    
    Args:
        user_input: Команда пользователя
        invoice_lines: Количество строк в инвойсе (для проверки границ)
        
    Returns:
        Список интентов в формате, совместимом со старым кодом
    """
    logger.info(f"Улучшенный парсинг команды: '{user_input}'")
    
    # Сначала используем новый парсер
    try:
        intents = parse_compound_command(user_input, invoice_lines)
        
        # Адаптируем результаты в формат, ожидаемый старым кодом
        adapted_intents = [adapt_intent(intent) for intent in intents]
        
        # Адаптируем результаты в формат, ожидаемый старым кодом
        adapted_intents = [adapt_intent(intent) for intent in intents]
        
        logger.info(f"Успешный парсинг через новую систему, результат: {adapted_intents}")
        return adapted_intents
            
    except Exception as e:
        logger.error(f"Ошибка в новых парсерах: {str(e)}")
        # В случае ошибки возвращаем стандартный ответ об ошибке, без fallback
        return [{"action": "unknown", "error": "parser_error", "user_message": "Error processing your command."}] 