"""
Модуль для валидации цен в накладных.
Проверяет соответствие между ценой за единицу, количеством и общей суммой.
"""
from typing import Optional, Tuple
import logging
from decimal import Decimal, ROUND_HALF_UP
from app.models import Position, ParsedData

logger = logging.getLogger(__name__)

# Константы для проверки точности
PRICE_TOLERANCE = Decimal('0.01')  # Допустимая погрешность в рублях
QTY_TOLERANCE = Decimal('0.001')   # Допустимая погрешность в количестве

def round_decimal(value: float, places: int = 2) -> Decimal:
    """Округляет float до Decimal с заданной точностью."""
    if value is None:
        return None
    return Decimal(str(value)).quantize(Decimal(f'0.{"0" * places}'), rounding=ROUND_HALF_UP)

def validate_position_price(position: Position) -> Position:
    """
    Проверяет корректность цен в позиции накладной.
    
    Args:
        position: Объект Position для проверки
        
    Returns:
        Position с обновленными полями валидации
    """
    # Если нет необходимых данных для проверки, пропускаем
    if position.qty is None or (position.price_per_unit is None and position.price is None) or position.total_price is None:
        return position
        
    # Определяем цену за единицу
    unit_price = position.price_per_unit if position.price_per_unit is not None else position.price
    
    # Рассчитываем ожидаемую общую сумму
    expected_total = float(round_decimal(unit_price * position.qty))
    actual_total = float(round_decimal(position.total_price))
    
    # Проверяем разницу с учетом допустимой погрешности
    difference = abs(Decimal(str(expected_total)) - Decimal(str(actual_total)))
    
    if difference > PRICE_TOLERANCE:
        position.price_mismatch = True
        position.mismatch_type = "total_mismatch"
        position.expected_total = expected_total
        position.status = "error"  # Обновляем статус
    else:
        position.price_mismatch = False
        position.mismatch_type = None
        position.expected_total = None  # Очищаем expected_total для корректных позиций
        
    return position

def validate_invoice_prices(parsed: ParsedData) -> ParsedData:
    """
    Проверяет корректность цен во всех позициях накладной.
    
    Args:
        parsed: Объект ParsedData для проверки
        
    Returns:
        ParsedData с обновленными полями валидации
    """
    mismatch_count = 0
    
    # Проверяем каждую позицию
    for i, position in enumerate(parsed.positions):
        validated_position = validate_position_price(position)
        if validated_position.price_mismatch:
            mismatch_count += 1
        parsed.positions[i] = validated_position
    
    # Обновляем общие флаги
    parsed.has_price_mismatches = mismatch_count > 0
    parsed.price_mismatch_count = mismatch_count
    
    return parsed

def validate_item_price(
    quantity: float,
    unit_price: float,
    total: float,
    tolerance: float = 0.01
) -> Tuple[bool, Optional[float], Optional[str]]:
    """
    Проверяет соответствие между ценой за единицу, количеством и общей суммой.

    Args:
        quantity: Количество товара
        unit_price: Цена за единицу
        total: Общая сумма
        tolerance: Допустимая погрешность в процентах (0.01 = 1%)

    Returns:
        Tuple[bool, Optional[float], Optional[str]]:
            - bool: True если цены соответствуют
            - float: Вычисленная цена (если есть несоответствие)
            - str: Тип несоответствия (если есть)
    """
    if not all(isinstance(x, (int, float)) for x in [quantity, unit_price, total]):
        return False, None, "invalid_type"

    if any(x <= 0 for x in [quantity, unit_price, total]):
        return False, None, "negative_values"

    # Округляем значения для точного сравнения
    quantity = round_decimal(quantity)
    unit_price = round_decimal(unit_price)
    total = round_decimal(total)

    # Вычисляем ожидаемую сумму
    expected_total = round_decimal(quantity * unit_price)
    
    # Проверяем соответствие с учетом погрешности
    if abs(expected_total - total) <= total * tolerance:
        return True, None, None

    # Если есть несоответствие, пробуем вычислить правильную цену
    calculated_price = round_decimal(total / quantity)
    
    logger.info(
        "Price mismatch detected",
        extra={
            "quantity": quantity,
            "unit_price": unit_price,
            "total": total,
            "expected_total": expected_total,
            "calculated_price": calculated_price
        }
    )

    return False, calculated_price, "total_mismatch"

def check_price_from_total(quantity: float, total: float) -> Optional[float]:
    """
    Вычисляет цену за единицу на основе количества и общей суммы.
    """
    if not all(isinstance(x, (int, float)) for x in [quantity, total]):
        return None
    
    if any(x <= 0 for x in [quantity, total]):
        return None

    return round_decimal(total / quantity)

def check_total_from_price(quantity: float, price: float) -> Optional[float]:
    """
    Вычисляет ожидаемую общую сумму на основе количества и цены за единицу.
    """
    if not all(isinstance(x, (int, float)) for x in [quantity, price]):
        return None
    
    if any(x <= 0 for x in [quantity, price]):
        return None

    return round_decimal(quantity * price) 