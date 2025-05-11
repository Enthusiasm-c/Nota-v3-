"""
Валидатор для проверки бизнес-правил и здравого смысла в накладных.

Проверяет корректность с точки зрения бизнес-логики:
- Даты не в будущем
- Цены и количества положительные
- Количества в разумных пределах
- Имена поставщиков валидны
- Номера накладных форматно корректны
"""

import logging
from typing import Dict, List, Any, Optional
import datetime
import re

logger = logging.getLogger(__name__)

class SanityValidator:
    """
    Валидатор для проверки бизнес-правил и здравого смысла в накладных.
    """
    
    def __init__(self, max_qty: float = 1000, min_price: float = 0, auto_fix: bool = True):
        """
        Инициализирует валидатор с настройками бизнес-правил.
        
        Args:
            max_qty: Максимально допустимое количество для одной позиции
            min_price: Минимально допустимая цена
            auto_fix: Автоматически исправлять обнаруженные ошибки
        """
        self.max_qty = max_qty
        self.min_price = min_price
        self.auto_fix = auto_fix
    
    def validate(self, invoice_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Проверяет все накладную на соответствие бизнес-правилам.
        
        Args:
            invoice_data: Словарь с данными накладной
            
        Returns:
            Словарь с проверенными и исправленными данными
        """
        result = invoice_data.copy()
        lines = result.get('lines', [])
        issues = result.get('issues', [])
        
        # Проверка заголовка накладной
        if self._check_header(result, issues):
            # Проходим по всем строкам и проверяем
            for i, line in enumerate(lines):
                self._check_line(i, line, lines, issues)
            
            # Проверка на дублирование позиций
            self._check_duplicates(lines, issues)
        
        result['lines'] = lines
        result['issues'] = issues
        return result
    
    def _check_header(self, invoice: Dict[str, Any], issues: List[Dict[str, Any]]) -> bool:
        """
        Проверяет корректность заголовка накладной.
        
        Args:
            invoice: Данные накладной
            issues: Список проблем для пополнения
            
        Returns:
            True, если заголовок корректен или исправлен
        """
        # Проверка даты
        date_str = invoice.get('date')
        if date_str:
            try:
                # Преобразуем строку даты в объект datetime
                formats = [
                    "%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", 
                    "%Y/%m/%d", "%m/%d/%Y", "%d-%m-%Y"
                ]
                
                parsed_date = None
                for fmt in formats:
                    try:
                        parsed_date = datetime.datetime.strptime(date_str, fmt).date()
                        break
                    except ValueError:
                        continue
                
                if parsed_date:
                    # Проверка, что дата не в будущем
                    today = datetime.date.today()
                    if parsed_date > today:
                        if self.auto_fix:
                            invoice['date'] = today.strftime("%Y-%m-%d")
                            issues.append({
                                'type': 'DATE_FUTURE',
                                'message': f'Дата накладной ({date_str}) в будущем. Исправлено на сегодня ({today.strftime("%Y-%m-%d")})',
                                'severity': 'warning'
                            })
                        else:
                            issues.append({
                                'type': 'DATE_FUTURE',
                                'message': f'Дата накладной ({date_str}) в будущем',
                                'severity': 'warning'
                            })
                else:
                    issues.append({
                        'type': 'DATE_INVALID',
                        'message': f'Невозможно распознать формат даты: {date_str}',
                        'severity': 'warning'
                    })
            except Exception as e:
                issues.append({
                    'type': 'DATE_ERROR',
                    'message': f'Ошибка при проверке даты: {str(e)}',
                    'severity': 'error'
                })
        
        # Проверка поставщика
        supplier = invoice.get('supplier')
        if not supplier:
            issues.append({
                'type': 'SUPPLIER_MISSING',
                'message': 'Не указан поставщик',
                'severity': 'warning'
            })
        elif len(supplier) < 3:
            issues.append({
                'type': 'SUPPLIER_TOO_SHORT',
                'message': f'Имя поставщика слишком короткое: {supplier}',
                'severity': 'info'
            })
        
        # Проверка номера накладной
        invoice_number = invoice.get('invoice_number')
        if invoice_number and not self._is_valid_invoice_number(invoice_number):
            issues.append({
                'type': 'INVOICE_NUMBER_INVALID',
                'message': f'Номер накладной имеет нестандартный формат: {invoice_number}',
                'severity': 'info'
            })
        
        return True
    
    def _check_line(self, index: int, line: Dict[str, Any], all_lines: List[Dict[str, Any]], issues: List[Dict[str, Any]]) -> None:
        """
        Проверяет корректность одной строки накладной.
        
        Args:
            index: Индекс строки
            line: Данные строки
            all_lines: Все строки накладной
            issues: Список проблем для пополнения
        """
        # Проверка наличия наименования
        name = line.get('name')
        if not name:
            issues.append({
                'type': 'NAME_MISSING',
                'line': index,
                'message': 'Не указано наименование товара',
                'severity': 'warning'
            })
        elif len(name) < 2:
            issues.append({
                'type': 'NAME_TOO_SHORT',
                'line': index,
                'message': f'Наименование товара слишком короткое: {name}',
                'severity': 'info'
            })
        
        # Проверка количества
        try:
            qty = float(line.get('qty', 0))
            if qty < 0:
                if self.auto_fix:
                    line['qty'] = abs(qty)
                    issues.append({
                        'type': 'QTY_NEGATIVE',
                        'line': index,
                        'message': f'Отрицательное количество ({qty}) исправлено на положительное ({abs(qty)})',
                        'severity': 'warning'
                    })
                else:
                    issues.append({
                        'type': 'QTY_NEGATIVE',
                        'line': index,
                        'message': f'Отрицательное количество: {qty}',
                        'severity': 'warning'
                    })
            elif qty > self.max_qty:
                issues.append({
                    'type': 'QTY_TOO_LARGE',
                    'line': index,
                    'message': f'Подозрительно большое количество: {qty}',
                    'severity': 'warning'
                })
        except (ValueError, TypeError):
            pass
        
        # Проверка цены
        try:
            price = float(line.get('price', 0))
            if price < self.min_price:
                if self.auto_fix and price < 0:
                    line['price'] = abs(price)
                    issues.append({
                        'type': 'PRICE_NEGATIVE',
                        'line': index,
                        'message': f'Отрицательная цена ({price}) исправлена на положительную ({abs(price)})',
                        'severity': 'warning'
                    })
                else:
                    issues.append({
                        'type': 'PRICE_TOO_LOW',
                        'line': index,
                        'message': f'Подозрительно низкая цена: {price}',
                        'severity': 'info'
                    })
        except (ValueError, TypeError):
            pass
        
        # Проверка единиц измерения
        unit = line.get('unit')
        if unit and not self._is_valid_unit(unit):
            if self.auto_fix:
                fixed_unit = self._fix_unit(unit)
                if fixed_unit != unit:
                    line['unit'] = fixed_unit
                    issues.append({
                        'type': 'UNIT_FIXED',
                        'line': index,
                        'message': f'Единица измерения исправлена: {unit} -> {fixed_unit}',
                        'severity': 'info'
                    })
            else:
                issues.append({
                    'type': 'UNIT_INVALID',
                    'line': index,
                    'message': f'Нестандартная единица измерения: {unit}',
                    'severity': 'info'
                })
    
    def _check_duplicates(self, lines: List[Dict[str, Any]], issues: List[Dict[str, Any]]) -> None:
        """
        Проверяет наличие дублирующихся позиций в накладной.
        
        Args:
            lines: Список строк накладной
            issues: Список проблем для пополнения
        """
        # Создаем словарь для подсчета вхождений наименований
        name_counts = {}
        
        for i, line in enumerate(lines):
            name = line.get('name', '').strip().lower()
            if name:
                if name in name_counts:
                    name_counts[name].append(i)
                else:
                    name_counts[name] = [i]
        
        # Проверяем на дубликаты
        for name, indexes in name_counts.items():
            if len(indexes) > 1:
                dup_lines = ", ".join(str(idx+1) for idx in indexes)
                issues.append({
                    'type': 'DUPLICATE_POSITIONS',
                    'message': f'Дублирующиеся позиции "{name}" в строках {dup_lines}',
                    'severity': 'warning'
                })
    
    def _is_valid_invoice_number(self, number: str) -> bool:
        """
        Проверяет, является ли строка валидным номером накладной.
        
        Args:
            number: Номер накладной
            
        Returns:
            True, если номер валиден
        """
        # Большинство номеров накладных содержат цифры и возможно буквы
        if not number or len(number) < 2:
            return False
        
        # Регулярное выражение для проверки общего формата номера накладной
        invoice_pattern = r'^[A-Za-z0-9\-\/\.]{2,20}$'
        return bool(re.match(invoice_pattern, number))
    
    def _is_valid_unit(self, unit: str) -> bool:
        """
        Проверяет, является ли строка валидной единицей измерения.
        
        Args:
            unit: Единица измерения
            
        Returns:
            True, если единица измерения валидна
        """
        valid_units = [
            'шт', 'кг', 'г', 'л', 'мл', 'пак', 'уп', 'box', 'pcs', 'kg', 'g', 'l', 'ml', 'pack'
        ]
        
        unit_lower = unit.lower().strip()
        for valid_unit in valid_units:
            if unit_lower == valid_unit or unit_lower.startswith(valid_unit):
                return True
        
        return False
    
    def _fix_unit(self, unit: str) -> str:
        """
        Пытается исправить некорректную единицу измерения.
        
        Args:
            unit: Исходная единица измерения
            
        Returns:
            Исправленная единица измерения
        """
        unit_lower = unit.lower().strip()
        
        # Типичные замены
        replacements = {
            'штук': 'шт',
            'штука': 'шт',
            'штуки': 'шт',
            'piece': 'pcs',
            'pieces': 'pcs',
            'kilogram': 'kg',
            'kilo': 'kg',
            'gram': 'g',
            'litre': 'l',
            'liter': 'l',
            'mililiter': 'ml',
            'milliliter': 'ml',
            'package': 'pack',
            'packet': 'pack',
            'pc': 'pcs',
            'pce': 'pcs',
            'грамм': 'г',
            'килограмм': 'кг',
            'литр': 'л',
            'миллилитр': 'мл',
            'упаковка': 'уп',
            'пакет': 'пак'
        }
        
        for wrong, correct in replacements.items():
            if unit_lower == wrong or unit_lower.startswith(wrong):
                return correct
        
        return unit 