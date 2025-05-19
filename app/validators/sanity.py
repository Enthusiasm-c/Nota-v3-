from typing import Dict, List, Any, Tuple
import logging
from decimal import Decimal

logger = logging.getLogger(__name__)

class SanityValidator:
    """
    Валидатор для проверки доменных бизнес-правил в накладных.
    
    Выполняет проверки:
    1. Соответствие единиц измерения товарам (штуки vs вес)
    2. Допустимые диапазоны цен для товаров
    3. Допустимые диапазоны весов для весовых товаров
    """
    
    # Список товаров, которые обычно измеряются в штуках
    UNIT_ITEMS = {
        'pcs': ['telur', 'tahu', 'tempe', 'botol', 'bungkus', 'sachet', 'kotak', 'karton'],
        'btl': ['kecap', 'susu', 'minyak', 'saus'],
        'krat': ['soda', 'coca', 'cola', 'sprite', 'fanta', 'aqua', 'air'],
    }
    
    # Диапазоны цен для категорий товаров (в IDR)
    PRICE_RANGES = {
        'meat': {'min': 80000, 'max': 300000, 'keywords': ['ayam', 'daging', 'sapi', 'ikan']},
        'rice': {'min': 8000, 'max': 25000, 'keywords': ['beras']},
        'oil': {'min': 10000, 'max': 30000, 'keywords': ['minyak']},
        'sugar': {'min': 10000, 'max': 20000, 'keywords': ['gula']},
        'egg': {'min': 1500, 'max': 3000, 'keywords': ['telur']},
        'drink': {'min': 5000, 'max': 50000, 'keywords': ['susu', 'soda', 'cola']},
    }
    
    # Диапазоны весов для весовых товаров (в кг)
    WEIGHT_RANGES = {
        'meat': {'min': 0.1, 'max': 10, 'keywords': ['ayam', 'daging', 'sapi', 'ikan']},
        'rice': {'min': 1, 'max': 50, 'keywords': ['beras']},
        'oil': {'min': 0.5, 'max': 10, 'keywords': ['minyak']},
        'sugar': {'min': 0.5, 'max': 10, 'keywords': ['gula']},
    }
    
    def __init__(self, strict_mode: bool = False):
        """
        Инициализирует валидатор.
        
        Args:
            strict_mode: Если True, помечает все несоответствия как ошибки;
                        если False, мягкий режим с предупреждениями
        """
        self.strict_mode = strict_mode
    
    def validate_line(self, line: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], List[Dict[str, Any]]]:
        """
        Проверяет строку накладной на соответствие доменным правилам.
        
        Args:
            line: Словарь с данными строки
            
        Returns:
            Tuple из:
            - флаг валидности (True если все ОК или только предупреждения)
            - исправленная строка
            - список обнаруженных проблем и предупреждений
        """
        issues = []
        fixed_line = line.copy()
        is_valid = True
        
        # Проверка наличия всех необходимых полей
        required_fields = ['name', 'qty', 'unit', 'price', 'amount']
        if not all(k in line for k in required_fields):
            logger.warning(f"Не все поля присутствуют в строке: {line}")
            missing = [f for f in required_fields if f not in line]
            issues.append({
                'type': 'MISSING_FIELDS',
                'message': f"Отсутствуют поля: {', '.join(missing)}",
                'severity': 'error'
            })
            is_valid = False
            return is_valid, fixed_line, issues
        
        name = str(line.get('name', '')).lower()
        unit = str(line.get('unit', '')).lower()
        
        # Проверка единиц измерения
        unit_issues = self._check_unit(name, unit)
        if unit_issues:
            for issue in unit_issues:
                if self.strict_mode or issue['severity'] == 'error':
                    is_valid = False
                issues.append(issue)
        
        # Проверка диапазонов цен
        try:
            price = Decimal(str(line.get('price', 0)))
            price_issues = self._check_price_range(name, price)
            if price_issues:
                for issue in price_issues:
                    if self.strict_mode or issue['severity'] == 'error':
                        is_valid = False
                    issues.append(issue)
        except (ValueError, TypeError) as e:
            logger.warning(f"Ошибка преобразования цены в Decimal: {e}")
            issues.append({
                'type': 'PRICE_TYPE_ERROR',
                'message': f"Некорректный формат цены: {line.get('price')}",
                'severity': 'error'
            })
            is_valid = False
        
        # Проверка диапазонов весов
        if unit.lower() == 'kg':
            try:
                qty = Decimal(str(line.get('qty', 0)))
                weight_issues = self._check_weight_range(name, qty)
                if weight_issues:
                    for issue in weight_issues:
                        if self.strict_mode or issue['severity'] == 'error':
                            is_valid = False
                        issues.append(issue)
            except (ValueError, TypeError) as e:
                logger.warning(f"Ошибка преобразования веса в Decimal: {e}")
                issues.append({
                    'type': 'WEIGHT_TYPE_ERROR',
                    'message': f"Некорректный формат веса: {line.get('qty')}",
                    'severity': 'error'
                })
                is_valid = False
                
        # Автоисправление единицы измерения для штучных товаров
        if issues and not is_valid:
            for issue in issues:
                if issue['type'] == 'UNIT_MISMATCH' and 'suggestion' in issue:
                    fixed_line['unit'] = issue['suggestion']
                    fixed_line['auto_fixed'] = True
                    issue['fixed'] = True
                    logger.info(f"Исправлена единица измерения с {unit} на {issue['suggestion']}")
                    is_valid = True  # Проблема исправлена
                    break
        
        return is_valid, fixed_line, issues
    
    def _check_unit(self, name: str, unit: str) -> List[Dict[str, Any]]:
        """
        Проверяет соответствие единицы измерения названию товара.
        """
        issues = []
        
        # Проверяем штучные товары
        for unit_type, keywords in self.UNIT_ITEMS.items():
            for keyword in keywords:
                if keyword in name:
                    if unit != unit_type and unit == 'kg':
                        issues.append({
                            'type': 'UNIT_MISMATCH',
                            'message': f"Товар '{name}' обычно измеряется в '{unit_type}', а не в '{unit}'",
                            'severity': 'warning',
                            'suggestion': unit_type
                        })
        
        return issues
    
    def _check_price_range(self, name: str, price: Decimal) -> List[Dict[str, Any]]:
        """
        Проверяет соответствие цены диапазону для категории товара.
        """
        issues = []
        
        for category, data in self.PRICE_RANGES.items():
            keywords = data.get('keywords', [])
            for keyword in keywords:
                if keyword in name:
                    min_price = Decimal(str(data.get('min', 0)))
                    max_price = Decimal(str(data.get('max', float('inf'))))
                    
                    if price < min_price:
                        issues.append({
                            'type': 'PRICE_TOO_LOW',
                            'message': f"Цена для '{name}' необычно низкая: {price} (мин. {min_price})",
                            'severity': 'warning',
                            'min_expected': float(min_price)
                        })
                    elif price > max_price:
                        issues.append({
                            'type': 'PRICE_TOO_HIGH',
                            'message': f"Цена для '{name}' необычно высокая: {price} (макс. {max_price})",
                            'severity': 'warning',
                            'max_expected': float(max_price)
                        })
        
        return issues
    
    def _check_weight_range(self, name: str, weight: Decimal) -> List[Dict[str, Any]]:
        """
        Проверяет соответствие веса диапазону для категории товара.
        """
        issues = []
        
        for category, data in self.WEIGHT_RANGES.items():
            keywords = data.get('keywords', [])
            for keyword in keywords:
                if keyword in name:
                    min_weight = Decimal(str(data.get('min', 0)))
                    max_weight = Decimal(str(data.get('max', float('inf'))))
                    
                    if weight < min_weight:
                        issues.append({
                            'type': 'WEIGHT_TOO_LOW',
                            'message': f"Вес для '{name}' необычно низкий: {weight} (мин. {min_weight})",
                            'severity': 'warning',
                            'min_expected': float(min_weight)
                        })
                    elif weight > max_weight:
                        issues.append({
                            'type': 'WEIGHT_TOO_HIGH',
                            'message': f"Вес для '{name}' необычно высокий: {weight} (макс. {max_weight})",
                            'severity': 'warning',
                            'max_expected': float(max_weight)
                        })
        
        return issues
    
    def validate_invoice(self, invoice_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Проверяет все строки накладной на соответствие доменным правилам.
        
        Args:
            invoice_data: Данные накладной со списком строк (lines)
            
        Returns:
            Обновленные данные накладной с исправлениями и отметками о проблемах
        """
        result = invoice_data.copy()
        lines = result.get('lines', [])
        all_issues = result.get('issues', [])  # Объединяем с существующими проблемами
        total_fixed = result.get('auto_fixed_count', 0)  # Объединяем с существующими исправлениями
        
        # Обновляем строки
        updated_lines = []
        for i, line in enumerate(lines):
            is_valid, fixed_line, issues = self.validate_line(line)
            
            # Если были проблемы, отмечаем это
            if issues:
                for issue in issues:
                    issue['line'] = i + 1
                all_issues.extend(issues)
                
                # Если был автоматический фикс
                if 'auto_fixed' in fixed_line and fixed_line['auto_fixed']:
                    total_fixed += 1
            
            updated_lines.append(fixed_line)
        
        # Обновляем результат
        result['lines'] = updated_lines
        result['issues'] = all_issues
        result['auto_fixed_count'] = total_fixed
        
        return result