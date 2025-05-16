from typing import List, Dict, Any
import re
from .free_parser import detect_intent, apply_edit

def parse_multi_edit_command(text: str) -> List[Dict[str, Any]]:
    """
    Парсит мультистрочную команду редактирования, разделенную точкой с запятой.
    
    Args:
        text: Строка с командами, разделенными ";"
        
    Returns:
        List[Dict[str, Any]]: Список интентов для каждой команды
    """
    # Разбиваем текст на отдельные команды
    commands = [cmd.strip() for cmd in text.split(";") if cmd.strip()]
    
    # Парсим каждую команду отдельно
    all_intents = []
    for command in commands:
        intents = detect_intent(command)  # Теперь возвращает список интентов
        for intent in intents:
            if intent["action"] != "unknown":
                all_intents.append(intent)
            
    return all_intents

def apply_multi_edit(ctx: dict, intents: List[Dict[str, Any]]) -> tuple[dict, list]:
    """
    Применяет список изменений к инвойсу последовательно.
    
    Args:
        ctx: Текущий контекст (invoice)
        intents: Список интентов для применения
        
    Returns:
        tuple[dict, list]: Обновленный контекст и список примененных изменений
    """
    current_ctx = ctx
    applied_changes = []
    
    for intent in intents:
        try:
            # Применяем каждое изменение последовательно
            new_ctx = apply_edit(current_ctx, intent)
            if new_ctx != current_ctx:  # Если изменение было успешно применено
                current_ctx = new_ctx
                applied_changes.append(intent)
        except Exception as e:
            # Логируем ошибку, но продолжаем обработку остальных команд
            print(f"Error applying intent {intent}: {str(e)}")
            
    return current_ctx, applied_changes 