"""
Модуль для управления сообщениями об ошибках парсеров команд.
Содержит словари ошибок и функции для формирования сообщений пользователю.
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Словарь сообщений об ошибках для пользователя
ERROR_MESSAGES = {
    # Общие ошибки
    "unknown_command": "I couldn't understand your command. Please try a different format.",
    "empty_command": "Please enter a command.",
    
    # Ошибки строк
    "line_out_of_range": "Line number is out of range. Please specify a valid line number.",
    "invalid_line_number": "Invalid line number. Please specify a line using a number (e.g., 'line 1').",
    "invalid_line_or_qty": "Invalid line number or quantity. Please specify a valid number.",
    
    # Ошибки цены
    "invalid_price_value": "Invalid price value. Please specify a valid number.",
    "invalid_price_command": "Invalid price command. Please use format 'line X price Y'.",
    
    # Ошибки количества
    "invalid_qty_value": "Invalid quantity value. Please specify a valid number.",
    "invalid_qty_command": "Invalid quantity command. Please use format 'line X qty Y'.",
    
    # Ошибки названия
    "empty_name_value": "Empty name value. Please specify a name.",
    "invalid_name_command": "Invalid name command. Please use format 'line X name Y'.",
    
    # Ошибки единицы измерения
    "empty_unit_value": "Empty unit value. Please specify a unit.",
    "invalid_unit_command": "Invalid unit command. Please use format 'line X unit Y'.",
    
    # Ошибки даты
    "invalid_date_format": "Invalid date format. Please use format 'DD.MM.YYYY' or 'YYYY-MM-DD'.",
    
    # Fallback
    "default": "There was an error processing your command. Please try again."
}

# Словарь локализованных сообщений об ошибках (русский)
RU_ERROR_MESSAGES = {
    # Общие ошибки
    "unknown_command": "Я не понял вашу команду. Пожалуйста, попробуйте другой формат.",
    "empty_command": "Пожалуйста, введите команду.",
    
    # Ошибки строк
    "line_out_of_range": "Номер строки вне диапазона. Пожалуйста, укажите правильный номер строки.",
    "invalid_line_number": "Неверный номер строки. Пожалуйста, укажите строку с помощью числа (например, 'строка 1').",
    "invalid_line_or_qty": "Неверный номер строки или количество. Пожалуйста, укажите допустимое число.",
    
    # Ошибки цены
    "invalid_price_value": "Неверное значение цены. Пожалуйста, укажите допустимое число.",
    "invalid_price_command": "Неверная команда цены. Используйте формат 'строка X цена Y'.",
    
    # Ошибки количества
    "invalid_qty_value": "Неверное значение количества. Пожалуйста, укажите допустимое число.",
    "invalid_qty_command": "Неверная команда количества. Используйте формат 'строка X количество Y'.",
    
    # Ошибки названия
    "empty_name_value": "Пустое значение названия. Пожалуйста, укажите название.",
    "invalid_name_command": "Неверная команда названия. Используйте формат 'строка X название Y'.",
    
    # Ошибки единицы измерения
    "empty_unit_value": "Пустое значение единицы измерения. Пожалуйста, укажите единицу измерения.",
    "invalid_unit_command": "Неверная команда единицы измерения. Используйте формат 'строка X единица Y'.",
    
    # Ошибки даты
    "invalid_date_format": "Неверный формат даты. Используйте формат 'ДД.ММ.ГГГГ' или 'ГГГГ-ММ-ДД'.",
    
    # Fallback
    "default": "Произошла ошибка при обработке вашей команды. Пожалуйста, попробуйте еще раз."
}

def get_error_message(error_code: str, lang: str = "en") -> str:
    """
    Возвращает сообщение об ошибке для указанного кода и языка.
    
    Args:
        error_code: Код ошибки
        lang: Код языка (en/ru)
        
    Returns:
        Сообщение об ошибке
    """
    if lang == "ru":
        message = RU_ERROR_MESSAGES.get(error_code, RU_ERROR_MESSAGES.get("default"))
    else:
        message = ERROR_MESSAGES.get(error_code, ERROR_MESSAGES.get("default"))
    
    return message

def create_error_response(error_code: str, lang: str = "en", **kwargs) -> Dict[str, Any]:
    """
    Создает стандартизированный ответ с ошибкой и локализованным сообщением.
    
    Args:
        error_code: Код ошибки
        lang: Код языка (en/ru)
        **kwargs: Дополнительные поля для включения в ответ
        
    Returns:
        Словарь с информацией об ошибке и сообщением для пользователя
    """
    message = get_error_message(error_code, lang)
    
    result = {
        "action": "unknown", 
        "error": error_code,
        "user_message": message,
        "source": "integrated_parser"
    }
    
    # Добавляем дополнительные поля
    result.update(kwargs)
    
    logger.debug(f"Сформировано сообщение об ошибке: {error_code} -> {message}")
    return result 