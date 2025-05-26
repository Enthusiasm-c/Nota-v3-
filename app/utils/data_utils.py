"""
Общие утилиты для работы с данными: очистка, нормализация, валидация.
Единое место для избежания дублирования функционала.
"""

import logging
import re
from datetime import date, datetime
from typing import Optional, Union

logger = logging.getLogger(__name__)


def clean_number(
    val: Optional[Union[str, float, int]], 
    default: Optional[float] = None,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None
) -> Optional[float]:
    """
    Универсальная функция очистки и конвертации числовых значений.
    
    Args:
        val: Исходное значение
        default: Значение по умолчанию
        min_value: Минимально допустимое значение
        max_value: Максимально допустимое значение
    
    Returns:
        Очищенное числовое значение или None
    """
    if val is None:
        return default
    
    try:
        if isinstance(val, (int, float)):
            result = float(val)
        else:
            # Преобразуем в строку
            val_str = str(val).strip()
            
            # Обрабатываем отрицательные числа
            is_negative = val_str.startswith('-')
            if is_negative:
                val_str = val_str[1:]
            
            # Обработка сокращений (k, m, тыс, млн) до очистки
            multiplier = 1
            val_lower = val_str.lower()
            
            if val_lower.endswith('k') or val_lower.endswith('к'):
                multiplier = 1000
                val_str = val_str[:-1]
            elif val_lower.endswith('m') or val_lower.endswith('м'):
                multiplier = 1_000_000
                val_str = val_str[:-1]
            elif 'тыс' in val_lower:
                multiplier = 1000
                val_str = re.sub(r'\s*тыс.*', '', val_str, flags=re.IGNORECASE)
            elif 'млн' in val_lower:
                multiplier = 1_000_000
                val_str = re.sub(r'\s*млн.*', '', val_str, flags=re.IGNORECASE)
            elif 'млрд' in val_lower:
                multiplier = 1_000_000_000
                val_str = re.sub(r'\s*млрд.*', '', val_str, flags=re.IGNORECASE)
            
            # Теперь удаляем все нечисловые символы, кроме точки и запятой
            clean_str = re.sub(r"[^\d.,]", "", val_str)
            
            # Заменяем запятую на точку
            clean_str = clean_str.replace(",", ".")
            
            # Обработка разных форматов десятичных разделителей
            # Если есть и точка и запятая, определяем что является разделителем тысяч
            if '.' in clean_str and ',' in clean_str:
                # Если точка идет раньше запятой - точка разделитель тысяч (европейский формат)
                if clean_str.rfind('.') < clean_str.rfind(','):
                    clean_str = clean_str.replace('.', '').replace(',', '.')
                # Иначе запятая - разделитель тысяч (американский формат)
                else:
                    clean_str = clean_str.replace(',', '')
            # Если только точки (может быть индонезийский формат 10.000)
            elif clean_str.count('.') == 1 and len(clean_str.split('.')[1]) == 3:
                # Это скорее всего разделитель тысяч
                clean_str = clean_str.replace('.', '')
            
            # Удаляем множественные точки, оставляя только последнюю
            parts = clean_str.split('.')
            if len(parts) > 2:
                clean_str = ''.join(parts[:-1]) + '.' + parts[-1]
            
            # Если строка пустая, возвращаем значение по умолчанию
            if not clean_str or clean_str == '.':
                return default
            
            result = float(clean_str) * multiplier
            if is_negative:
                result = -result
    
    except (ValueError, TypeError):
        return default
    
    # Проверка границ
    if min_value is not None and result < min_value:
        logger.warning(f"Значение {result} меньше минимального {min_value}")
        return min_value
    
    if max_value is not None and result > max_value:
        logger.warning(f"Значение {result} больше максимального {max_value}")
        return max_value
    
    return result


def parse_date(
    date_str: Optional[Union[str, date, datetime]], 
    formats: Optional[list[str]] = None
) -> Optional[date]:
    """
    Универсальная функция парсинга даты из различных форматов.
    
    Args:
        date_str: Строка с датой или объект даты
        formats: Список форматов для попытки парсинга
    
    Returns:
        Объект datetime.date или None
    """
    if date_str is None:
        return None
    
    # Если datetime объект (проверяем первым, так как datetime также является date)
    if isinstance(date_str, datetime):
        return date_str.date()
    
    # Если уже date объект
    if isinstance(date_str, date):
        return date_str
    
    # Преобразуем в строку
    date_str = str(date_str).strip()
    if not date_str:
        return None
    
    # Стандартные форматы
    if formats is None:
        formats = [
            "%Y-%m-%d",      # ISO формат
            "%d.%m.%Y",      # DD.MM.YYYY
            "%d/%m/%Y",      # DD/MM/YYYY
            "%d-%m-%Y",      # DD-MM-YYYY
            "%Y/%m/%d",      # YYYY/MM/DD
            "%d %B %Y",      # DD Month YYYY
            "%d %b %Y",      # DD Mon YYYY
            "%B %d, %Y",     # Month DD, YYYY
            "%b %d, %Y",     # Mon DD, YYYY
        ]
    
    # Пробуем различные форматы
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    
    # Пробуем регулярные выражения для нестандартных форматов
    # DD.MM.YYYY или DD/MM/YYYY или DD-MM-YYYY
    match = re.match(r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})", date_str)
    if match:
        try:
            day, month, year = map(int, match.groups())
            return date(year, month, day)
        except ValueError:
            pass
    
    # YYYY-MM-DD или YYYY/MM/DD
    match = re.match(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", date_str)
    if match:
        try:
            year, month, day = map(int, match.groups())
            return date(year, month, day)
        except ValueError:
            pass
    
    logger.warning(f"Не удалось распарсить дату: {date_str}")
    return None


def normalize_text(text: Optional[str], lower: bool = True) -> str:
    """
    Нормализует текст: удаляет лишние пробелы, опционально приводит к нижнему регистру.
    
    Args:
        text: Исходный текст
        lower: Приводить ли к нижнему регистру
    
    Returns:
        Нормализованный текст
    """
    if not text:
        return ""
    
    # Удаляем лишние пробелы
    text = " ".join(text.split())
    
    # Удаляем специальные символы в начале и конце
    text = text.strip("-.,;:!?")
    
    # Приводим к нижнему регистру если нужно
    if lower:
        text = text.lower()
    
    return text


def is_valid_price(price: Optional[float], max_price: float = 10_000_000) -> bool:
    """
    Проверяет, является ли цена валидной.
    
    Args:
        price: Цена для проверки
        max_price: Максимально допустимая цена
    
    Returns:
        True если цена валидна
    """
    if price is None:
        return False
    
    return 0 <= price <= max_price


def is_valid_quantity(qty: Optional[float], max_qty: float = 10000) -> bool:
    """
    Проверяет, является ли количество валидным.
    
    Args:
        qty: Количество для проверки
        max_qty: Максимально допустимое количество
    
    Returns:
        True если количество валидно
    """
    if qty is None:
        return False
    
    return 0 < qty <= max_qty


def sanitize_string(text: Optional[str], max_length: int = 255) -> str:
    """
    Очищает строку от небезопасных символов и ограничивает длину.
    
    Args:
        text: Исходный текст
        max_length: Максимальная длина
    
    Returns:
        Очищенная строка
    """
    if not text:
        return ""
    
    # Удаляем управляющие символы, но сохраняем переносы строк и табуляцию как пробелы
    text = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f-\x9f]', '', text)
    text = text.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')
    
    # Нормализуем пробелы
    text = normalize_text(text, lower=False)
    
    # Ограничиваем длину
    if len(text) > max_length:
        text = text[:max_length-3] + "..."
    
    return text




def calculate_total(qty: Optional[float], price: Optional[float]) -> Optional[float]:
    """
    Вычисляет общую стоимость с проверками.
    
    Args:
        qty: Количество
        price: Цена за единицу
    
    Returns:
        Общая стоимость или None
    """
    if qty is None or price is None:
        return None
    
    if qty <= 0 or price < 0:
        return None
    
    return round(qty * price, 2)


def convert_weight_to_kg(
    quantity: float,
    unit: str,
    price_per_unit: Optional[float] = None
) -> tuple[float, str, Optional[float]]:
    """
    Преобразует вес в килограммы из других единиц.
    
    Args:
        quantity: Количество
        unit: Единица измерения
        price_per_unit: Цена за единицу (опционально)
    
    Returns:
        Кортеж (новое_количество, новая_единица, новая_цена)
    """
    unit_lower = unit.lower() if unit else ""
    
    # Коэффициенты преобразования в килограммы
    conversions = {
        "g": 0.001,      # граммы
        "gr": 0.001,     # граммы (альтернативное обозначение)
        "gm": 0.001,     # граммы (альтернативное обозначение)
        "gram": 0.001,   # граммы (полное название)
        "grams": 0.001,  # граммы (множественное)
        "gramme": 0.001, # граммы (французское)
        "grammes": 0.001,# граммы (французское, мн.)
        "г": 0.001,      # граммы (русский)
        "гр": 0.001,     # граммы (русский)
        "mg": 0.000001,  # миллиграммы
        "мг": 0.000001,  # миллиграммы (русский)
        "t": 1000,       # тонны
        "ton": 1000,     # тонны
        "tonne": 1000,   # тонны
        "т": 1000,       # тонны (русский)
        "lb": 0.453592,  # фунты
        "lbs": 0.453592, # фунты
        "pound": 0.453592,# фунты
        "pounds": 0.453592,# фунты
        "oz": 0.0283495, # унции
        "ounce": 0.0283495,# унции
        "ounces": 0.0283495,# унции
    }
    
    # Если уже в килограммах, ничего не делаем
    if unit_lower in ["kg", "kgs", "kilogram", "kilograms", "kilo", "kilos", "кг"]:
        return quantity, unit, price_per_unit
    
    # Проверяем, есть ли коэффициент преобразования
    if unit_lower in conversions:
        factor = conversions[unit_lower]
        new_quantity = quantity * factor
        new_unit = "kg"
        
        # Корректируем цену за единицу
        new_price = price_per_unit / factor if price_per_unit else None
        
        logger.debug(f"Преобразование веса: {quantity}{unit} -> {new_quantity}kg")
        return new_quantity, new_unit, new_price
    
    # Если не можем преобразовать, возвращаем как есть
    return quantity, unit, price_per_unit


def should_convert_to_kg(quantity: float, unit: str) -> bool:
    """
    Определяет, нужно ли преобразовывать вес в килограммы.
    
    Args:
        quantity: Количество
        unit: Единица измерения
    
    Returns:
        True если нужно преобразовать
    """
    unit_lower = unit.lower() if unit else ""
    
    # Преобразуем граммы в килограммы если больше или равно 1000г
    if unit_lower in ["g", "gr", "gm", "gram", "grams", "gramme", "grammes", "г", "гр"]:
        return quantity >= 1000
    
    # Всегда преобразуем тонны, фунты и другие единицы
    if unit_lower in ["t", "ton", "tonne", "т", "lb", "lbs", "pound", "pounds", "oz", "ounce", "ounces"]:
        return True
    
    # Миллиграммы преобразуем если больше 1 000 000 мг (1 кг)
    if unit_lower in ["mg", "мг"]:
        return quantity >= 1_000_000
    
    return False