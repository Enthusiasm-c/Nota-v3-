"""
Модуль для применения интентов GPT-3.5 к данным инвойса.
"""

import logging
from typing import Dict, Any, Union, Optional
from datetime import datetime
from copy import deepcopy
import re
from app.models import ParsedData
from app.converters import parsed_to_dict
from app.models.invoice import Invoice
from app.edit.actions import (
    set_name,
    set_quantity,
    set_unit,
    set_price,
    set_date,
    set_supplier
)

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

def apply_intent(invoice: Union[dict, ParsedData, Invoice], intent: Dict[str, Any]) -> Dict[str, Any]:
    """
    Применяет интент к инвойсу.
    
    Args:
        invoice: Инвойс для редактирования
        intent: Интент для применения
        
    Returns:
        Dict: Результат применения интента
    """
    # Проверяем и конвертируем входные данные
    if not isinstance(invoice, dict):
        invoice = parsed_to_dict(invoice)
    
    # Создаем глубокую копию инвойса
    result = deepcopy(invoice)
    
    # Проверяем наличие позиций
    if "positions" not in result:
        result["positions"] = []
        logger.warning("В инвойсе отсутствует список позиций, создаем пустой список")
    
    action = intent.get("action")
    if not action:
        logger.error("Интент не содержит действия")
        return result
        
    logger.info(f"Применение интента: {action}")
    
    try:
        if action == "set_name":
            line = intent.get("line", 0) - 1  # Преобразуем в 0-based индекс
            value = intent.get("value", "")
            updated = set_name(result, line, value)
            if isinstance(updated, dict) and "positions" in updated:
                result = updated
            
        elif action == "set_qty":
            line = intent.get("line", 0) - 1
            qty = str(intent.get("qty", "0"))
            updated = set_quantity(result, line, qty)
            if isinstance(updated, dict) and "positions" in updated:
                result = updated
            
        elif action == "set_unit":
            line = intent.get("line", 0) - 1
            unit = intent.get("value", "")
            updated = set_unit(result, line, unit)
            if isinstance(updated, dict) and "positions" in updated:
                result = updated
            
        elif action == "set_price":
            line = intent.get("line", 0) - 1
            price = str(intent.get("value", "0"))
            updated = set_price(result, line, price)
            if isinstance(updated, dict) and "positions" in updated:
                result = updated
            
        elif action == "set_date":
            date_str = intent.get("value", "")
            try:
                # Преобразуем дату и сохраняем как строку в нужном формате
                date = datetime.strptime(date_str, "%Y-%m-%d")
                updated = set_date(result, date_str)
                if isinstance(updated, dict):
                    result = updated
            except ValueError:
                logger.error(f"Неверный формат даты: {date_str}")
                
        elif action == "edit_supplier":
            supplier_name = intent.get("value", "")
            supplier_id = intent.get("supplier_id")
            supplier_code = intent.get("supplier_code")
            updated = set_supplier(result, supplier_name, supplier_id, supplier_code)
            if isinstance(updated, dict) and not updated.get("error"):
                result = updated
            
        else:
            logger.warning(f"Неизвестное действие: {action}")
    
    except Exception as e:
        logger.error(f"Ошибка при применении интента {action}: {str(e)}")
        logger.exception(e)
    
    # Проверяем, что позиции не были потеряны
    if not result.get("positions"):
        logger.critical("Позиции были потеряны при применении интента, возвращаем исходный инвойс")
        return invoice
        
    return result