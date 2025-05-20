"""
Модуль для применения интентов GPT-3.5 к данным инвойса.
"""

import logging
from typing import Dict, Any, Union
from datetime import datetime
from copy import deepcopy
import re
from app.models import ParsedData
from app.converters import parsed_to_dict

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
    source = intent.get("source", "openai")
    logger.info(f"Применяем интент: action={action}, source={source}")
    
    # Тестовый блок для проверки обработки интента edit_quantity
    if action == "edit_quantity":
        line_value = intent.get("line", 0)
        logger.info(f"Тест: intent.get('line', 0) = {line_value}, intent.get('line', 0) - 1 = {line_value - 1}")
    
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
    
    elif action == "set_qty":
        line = intent.get("line", 0) - 1
        qty = str(intent.get("qty", "0"))
        logger.info(f"set_qty: line={line}, qty={qty}")
        return set_quantity(
            invoice,
            line,
            qty
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
            intent.get("line", 0) - 1,
            intent.get("value", "")
        )
    elif action == "edit_line_field":
        line = intent.get("line", 0) - 1  # Преобразуем в 0-based индекс
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
        try:
            # Изменение даты
            value = intent.get("value", "")
            logger.info(f"Изменяем дату инвойса на: {value}")
            
            # Проверяем формат даты и преобразуем его
            # Поддерживаем различные форматы: DD.MM.YYYY, MM/DD/YYYY, YYYY-MM-DD и т.д.
            match = re.match(r"(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})", value)
            
            if match:
                day, month, year = match.groups()
                
                # Приводим год к YYYY формату, если он в формате YY
                if len(year) == 2:
                    current_year = datetime.now().year
                    century = current_year // 100
                    year_num = int(year)
                    if year_num > (current_year % 100):
                        # Если год больше текущего, считаем что это прошлый век
                        century -= 1
                    year = f"{century}{year}"
                
                # Форматируем дату
                formatted_date = f"{int(day):02d}.{int(month):02d}.{int(year)}"
                logger.info(f"Дата отформатирована в {formatted_date}")
                
                invoice["date"] = formatted_date
            else:
                logger.warning(f"Некорректный формат даты: {value}")
        except Exception as e:
            logger.error(f"Ошибка при обработке интента edit_date: {e}")
        
        # Возвращаем invoice с изменениями
        return invoice

    elif action == "edit_quantity":
        try:
            # Изменение количества
            position_idx = intent.get("line", 0) - 1
            value = intent.get("value", "0")
            
            # Проверяем, что в позициях есть элемент с таким индексом
            if 0 <= position_idx < len(invoice.get("positions", [])):
                # Конвертируем строку в число
                numeric_value = value
                if isinstance(value, str):
                    # Заменяем запятую на точку для корректного парсинга
                    value = value.replace(",", ".")
                    numeric_value = float(value)
                
                invoice["positions"][position_idx]["qty"] = numeric_value
            else:
                logger.warning(f"Невалидный индекс позиции для изменения: {position_idx}")
        except Exception as e:
            logger.error(f"Ошибка при изменении quantity: {e}")
        
        # Возвращаем invoice с изменениями
        return invoice
    
    elif action == "edit_unit":
        try:
            # Изменение единицы измерения
            position_idx = intent.get("line", 0) - 1
            value = intent.get("value", "").strip().lower()
            
            # Проверяем, что в позициях есть элемент с таким индексом
            if 0 <= position_idx < len(invoice.get("positions", [])):
                # Нормализуем единицу измерения
                normalized_unit = value
                if value in ["g", "г", "гр", "грамм", "гра", "грамма", "грамм"]:
                    normalized_unit = "g"
                elif value in ["kg", "кг", "кило", "килограмм", "килограмма"]:
                    normalized_unit = "kg"
                elif value in ["l", "л", "литр", "литра", "литров"]:
                    normalized_unit = "l"
                elif value in ["ml", "мл", "миллилитр", "миллилитра", "миллилитров"]:
                    normalized_unit = "ml"
                elif value in ["pc", "шт", "штука", "штуки", "штук"]:
                    normalized_unit = "pc"
                
                invoice["positions"][position_idx]["unit"] = normalized_unit
            else:
                logger.warning(f"Невалидный индекс позиции для изменения: {position_idx}")
        except Exception as e:
            logger.error(f"Ошибка при изменении unit: {e}")
        
        # Возвращаем invoice с изменениями
        return invoice
    
    elif action == "edit_price":
        try:
            # Изменение цены
            position_idx = intent.get("line", 0) - 1
            value = intent.get("value", "0")
            
            # Проверяем, что в позициях есть элемент с таким индексом
            if 0 <= position_idx < len(invoice.get("positions", [])):
                # Конвертируем строку в число
                numeric_value = value
                if isinstance(value, str):
                    # Заменяем запятую на точку для корректного парсинга
                    value = value.replace(",", ".")
                    numeric_value = float(value)
                
                invoice["positions"][position_idx]["price"] = numeric_value
            else:
                logger.warning(f"Невалидный индекс позиции для изменения: {position_idx}")
        except Exception as e:
            logger.error(f"Ошибка при изменении price: {e}")
        
        # Возвращаем invoice с изменениями
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