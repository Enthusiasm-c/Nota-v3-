from typing import Dict, List, Any, Tuple, Optional
import logging
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)

class ArithmeticValidator:
    """
    Валидатор для проверки арифметических соотношений в накладных.
    
    Выполняет проверку:
    1. qty * price = amount (с учетом погрешностей округления)
    2. Автокоррекция пропущенных нулей в ценах
    3. Коррекция дробных значений
    """
    
    def __init__(self, max_error_percent: float = 1.0):
        """
        Инициализирует валидатор.
        
        Args:
            max_error_percent: Максимальный допустимый процент ошибки между расчетной и 
                               указанной суммой (по умолчанию 1%)
        """
        self.max_error_percent = max_error_percent
    
    def validate_line(self, line: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], List[Dict[str, Any]]]:
        """
        Проверяет и исправляет арифметические ошибки в строке накладной.
        
        Args:
            line: Словарь с данными строки (qty, price, amount и т.д.)
            
        Returns:
            Tuple из:
            - флаг валидности (True если валидно или исправлено)
            - исправленная строка
            - список обнаруженных проблем и исправлений
        """
        issues = []
        fixed_line = line.copy()
        is_valid = True
        
        # Проверка наличия всех необходимых полей
        if not all(k in line for k in ['qty', 'price', 'amount']):
            logger.warning(f"Не все поля присутствуют в строке: {line}")
            is_valid = False
            return is_valid, fixed_line, issues
        
        # Преобразуем в Decimal для точных вычислений
        try:
            qty = Decimal(str(line['qty']))
            price = Decimal(str(line['price']))
            amount = Decimal(str(line['amount']))
        except (InvalidOperation, TypeError, ValueError) as e:
            logger.warning(f"Ошибка преобразования значений в Decimal: {e}")
            issues.append({
                'type': 'VALUE_ERROR',
                'field': 'price or qty or amount',
                'message': f"Ошибка в значениях: {e}"
            })
            is_valid = False
            return is_valid, fixed_line, issues
        
        # Расчет ожидаемой суммы
        expected_amount = qty * price
        
        # Проверка на соответствие с учетом погрешности
        if expected_amount == 0 and amount == 0:
            # Особый случай: оба значения равны нулю
            return True, fixed_line, issues
        
        # Вычисляем процентную погрешность
        if expected_amount != 0:
            error_percent = abs(100 * (amount - expected_amount) / expected_amount)
        else:
            error_percent = 100.0  # если ожидаемая сумма 0, но фактическая не 0
        
        # Если погрешность в пределах допустимой, считаем валидным
        if error_percent <= self.max_error_percent:
            return True, fixed_line, issues
        
        # Пытаемся исправить ошибки
        fixed_line, fix_issues = self._try_fix_arithmetic(qty, price, amount)
        issues.extend(fix_issues)
        
        # Проверяем, удалось ли исправить
        if fixed_line:
            is_valid = True
            for issue in fix_issues:
                logger.info(f"Исправлена ошибка: {issue['type']}, новое значение: {issue['fix']}")
        else:
            is_valid = False
            issues.append({
                'type': 'ARITHMETIC_ERROR',
                'message': f"qty * price != amount: {qty} * {price} != {amount}",
                'error_percent': round(error_percent, 2)
            })
        
        return is_valid, fixed_line, issues
    
    def _try_fix_arithmetic(self, qty: Decimal, price: Decimal, amount: Decimal) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Пытается исправить арифметические ошибки.
        
        Args:
            qty: Количество
            price: Цена
            amount: Сумма
            
        Returns:
            Кортеж из исправленной строки (или None если не удалось) и списка исправлений
        """
        issues = []
        
        # Проверка на потерянный ноль в цене
        if price < 100_000 and amount / qty > 100_000:
            new_price = price * 10
            if abs(new_price * qty - amount) / amount <= 0.01:  # 1% погрешность
                issues.append({
                    'type': 'PRICE_ZERO_LOST',
                    'old': str(price),
                    'fix': str(new_price)
                })
                return {'qty': qty, 'price': new_price, 'amount': amount}, issues
        
        # Проверка на обратную ситуацию - лишний ноль в цене
        if price > 1000 and amount / qty < price / 10:
            new_price = price / 10
            if abs(new_price * qty - amount) / amount <= 0.01:  # 1% погрешность
                issues.append({
                    'type': 'PRICE_EXTRA_ZERO',
                    'old': str(price),
                    'fix': str(new_price)
                })
                return {'qty': qty, 'price': new_price, 'amount': amount}, issues
        
        # Исправление дробных значений в количестве
        # Например, если количество выглядит как "1.5", но распознано как "15"
        if qty > 10 and amount / price < qty / 10:
            new_qty = qty / 10
            if abs(new_qty * price - amount) / amount <= 0.01:  # 1% погрешность
                issues.append({
                    'type': 'QTY_DECIMAL_MISSED',
                    'old': str(qty),
                    'fix': str(new_qty)
                })
                return {'qty': new_qty, 'price': price, 'amount': amount}, issues
        
        # Если не удалось исправить, возвращаем None
        return None, issues

    def validate_invoice(self, invoice_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Проверяет все строки накладной на арифметические ошибки.
        
        Args:
            invoice_data: Данные накладной со списком строк (lines)
            
        Returns:
            Обновленные данные накладной с исправлениями и отметками о проблемах
        """
        result = invoice_data.copy()
        lines = result.get('lines', [])
        all_issues = []
        total_fixed = 0
        
        # Обновляем строки
        updated_lines = []
        for i, line in enumerate(lines):
            is_valid, fixed_line, issues = self.validate_line(line)
            
            # Если были исправления, отмечаем это
            if issues:
                for issue in issues:
                    issue['line'] = i + 1
                all_issues.extend(issues)
                
                if is_valid:
                    total_fixed += 1
                    fixed_line['auto_fixed'] = True
            
            updated_lines.append(fixed_line)
        
        # Обновляем результат
        result['lines'] = updated_lines
        result['issues'] = all_issues
        result['auto_fixed_count'] = total_fixed
        
        return result 