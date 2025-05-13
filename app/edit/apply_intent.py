"""
Модуль для применения интентов GPT-3.5 к данным инвойса.
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime
from copy import deepcopy

logger = logging.getLogger(__name__)

def set_date(invoice: Dict[str, Any], value: str) -> Dict[str, Any]:
    """
    Устанавливает дату инвойса.
    
    Args:
        invoice: Словарь с данными инвойса
        value: Новое значение даты (строка)
    
    Returns:
        Dict: Обновленный инвойс
    """
    result = deepcopy(invoice)
    result["date"] = value
    return result

def set_price(invoice: Dict[str, Any], line_index: int, value: str) -> Dict[str, Any]:
    """
    Устанавливает цену для указанной позиции.
    
    Args:
        invoice: Словарь с данными инвойса
        line_index: Индекс позиции (начиная с 0)
        value: Новое значение цены
    
    Returns:
        Dict: Обновленный инвойс
    """
    result = deepcopy(invoice)
    
    if 0 <= line_index < len(result.get("positions", [])):
        result["positions"][line_index]["price"] = value
        # Обновляем статус позиции на "ok"
        result["positions"][line_index]["status"] = "ok"
    else:
        logger.warning(f"Попытка установить цену для несуществующей строки: {line_index + 1}")
    
    return result

def set_name(invoice: Dict[str, Any], line_index: int, value: str, manual_edit: bool = False) -> Dict[str, Any]:
    """
    Устанавливает название для указанной позиции.
    
    Args:
        invoice: Словарь с данными инвойса
        line_index: Индекс позиции (начиная с 0)
        value: Новое название
        manual_edit: Флаг для обозначения ручного редактирования пользователем
    
    Returns:
        Dict: Обновленный инвойс
    """
    from app.matcher import match_positions
    from app.data_loader import load_products
    result = deepcopy(invoice)
    
    if 0 <= line_index < len(result.get("positions", [])):
        result["positions"][line_index]["name"] = value
        
        if manual_edit:
            # Если это ручное редактирование пользователем, устанавливаем статус "manual"
            # что означает "принято пользователем, не считать ошибкой"
            result["positions"][line_index]["status"] = "manual"
            logger.info(f"Line {line_index+1} manually edited by user: name = '{value}'")
        else:
            # Пытаемся найти соответствие в базе продуктов
            products = load_products()
            match_results = match_positions([result["positions"][line_index]], products)
            if match_results and match_results[0].get("matched_name"):
                result["positions"][line_index]["matched_name"] = match_results[0]["matched_name"]
                result["positions"][line_index]["status"] = match_results[0]["status"]
        else:
            # В противном случае сбрасываем статус для повторного матчинга
            result["positions"][line_index]["status"] = "unknown"
    else:
        logger.warning(f"Попытка установить название для несуществующей строки: {line_index + 1}")
    
    return result

def set_quantity(invoice: Dict[str, Any], line_index: int, value: str) -> Dict[str, Any]:
    """
    Устанавливает количество для указанной позиции.
    
    Args:
        invoice: Словарь с данными инвойса
        line_index: Индекс позиции (начиная с 0)
        value: Новое значение количества
    
    Returns:
        Dict: Обновленный инвойс
    """
    result = deepcopy(invoice)
    
    if 0 <= line_index < len(result.get("positions", [])):
        result["positions"][line_index]["qty"] = value
        # Не меняем статус, так как количество не влияет на распознавание
    else:
        logger.warning(f"Попытка установить количество для несуществующей строки: {line_index + 1}")
    
    return result

def set_unit(invoice: Dict[str, Any], line_index: int, value: str) -> Dict[str, Any]:
    """
    Устанавливает единицу измерения для указанной позиции.
    
    Args:
        invoice: Словарь с данными инвойса
        line_index: Индекс позиции (начиная с 0)
        value: Новая единица измерения
    
    Returns:
        Dict: Обновленный инвойс
    """
    result = deepcopy(invoice)
    
    if 0 <= line_index < len(result.get("positions", [])):
        result["positions"][line_index]["unit"] = value
    else:
        logger.warning(f"Попытка установить единицу измерения для несуществующей строки: {line_index + 1}")
    
    return result

from typing import Union
from app.models import ParsedData
from app.converters import parsed_to_dict

def apply_intent(invoice: Union[dict, ParsedData], intent: dict) -> dict:
    """
    Применяет интент к инвойсу на основе действия.
    
    Args:
        invoice: Словарь с данными инвойса или ParsedData
        intent: Словарь с интентом от GPT-3.5
    
    Returns:
        Dict: Обновленный инвойс
    """
    invoice = parsed_to_dict(invoice)
    action = intent.get("action", "unknown")
    
    if action == "set_date":
        return set_date(invoice, intent.get("value", ""))
    
    elif action == "set_price":
        return set_price(
            invoice, 
            intent.get("line_index", 0), 
            intent.get("value", "")
        )
    
    elif action == "set_name":
        return set_name(
            invoice, 
            intent.get("line_index", 0), 
            intent.get("value", "")
        )
    
    elif action == "set_quantity":
        return set_quantity(
            invoice, 
            intent.get("line_index", 0), 
            intent.get("value", "")
        )
    
    elif action == "set_unit":
        return set_unit(
            invoice, 
            intent.get("line_index", 0), 
            intent.get("value", "")
        )
    
    elif action == "edit_name":
        return set_name(
            invoice,
            intent.get("line", 0),
            intent.get("value", "")
        )
    elif action == "edit_line_field":
        line = intent.get("line", 0) - 1
        field = intent.get("field")
        value = intent.get("value")
        
        if (
            isinstance(invoice.get("positions"), list)
            and 0 <= line < len(invoice["positions"])
        ):
            # Обрабатываем поле name специальным образом для ручного редактирования
            if field == "name":
                return set_name(invoice, line, value, manual_edit=True)
            # For other fields, just update the value. Do not touch 'status'.
            if field in invoice["positions"][line]:
                invoice["positions"][line][field] = value
                # Only set status to 'manual' for name edits
                if field == "name":
                    invoice["positions"][line]["status"] = "manual"
                logger.info(f"Line {line+1} field '{field}' manually edited by user: value = '{value}'")
                
        return invoice

    elif action == "edit_date":
        value = intent.get("value")
        invoice["date"] = value
        return invoice

    elif action == "add_line":
        value = intent.get("value")
        parts = value.split()
        if len(parts) >= 4:
            name = parts[0]
            qty = parts[1]
            unit = parts[2]
            price = parts[3]
            invoice.setdefault("positions", []).append(
                {"name": name, "qty": qty, "unit": unit, "price": price}
            )
        return invoice

    else:
        logger.warning(f"Неизвестное действие в интенте: {action}")
        return deepcopy(invoice)  # Возвращаем копию без изменений