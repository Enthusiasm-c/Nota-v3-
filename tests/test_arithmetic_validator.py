import pytest
from decimal import Decimal
from app.validators.arithmetic import ArithmeticValidator

class TestArithmeticValidator:
    """Тесты для арифметического валидатора."""
    
    def setup_method(self):
        """Настройка перед каждым тестом."""
        self.validator = ArithmeticValidator(max_error_percent=1.0)
    
    def test_valid_arithmetic(self):
        """Проверка валидных строк."""
        # Точное соответствие
        line = {'qty': 2, 'price': 15000, 'amount': 30000}
        is_valid, fixed_line, issues = self.validator.validate_line(line)
        assert is_valid is True
        assert not issues
        
        # В пределах погрешности (0.5%)
        line = {'qty': 2, 'price': 15000, 'amount': 30150}
        is_valid, fixed_line, issues = self.validator.validate_line(line)
        assert is_valid is True
        assert not issues
    
    def test_invalid_arithmetic(self):
        """Проверка невалидных строк без возможности исправления."""
        line = {'qty': 2, 'price': 15000, 'amount': 40000}  # Ошибка более 1%
        is_valid, fixed_line, issues = self.validator.validate_line(line)
        assert is_valid is False
        assert len(issues) == 1
        assert issues[0]['type'] == 'ARITHMETIC_ERROR'
    
    def test_missing_fields(self):
        """Проверка строк с отсутствующими полями."""
        line = {'qty': 2, 'price': 15000}  # Нет amount
        is_valid, fixed_line, issues = self.validator.validate_line(line)
        assert is_valid is False
        assert not issues  # Не помечается как ошибка, просто невалидно
        
        line = {'qty': 2, 'amount': 30000}  # Нет price
        is_valid, fixed_line, issues = self.validator.validate_line(line)
        assert is_valid is False
    
    def test_invalid_value_types(self):
        """Проверка строк с невалидными типами значений."""
        line = {'qty': '2x', 'price': 15000, 'amount': 30000}  # Нечисловое значение
        is_valid, fixed_line, issues = self.validator.validate_line(line)
        assert is_valid is False
        assert len(issues) == 1
        assert issues[0]['type'] == 'VALUE_ERROR'
    
    def test_zero_values(self):
        """Проверка строк с нулевыми значениями."""
        line = {'qty': 0, 'price': 15000, 'amount': 0}
        is_valid, fixed_line, issues = self.validator.validate_line(line)
        assert is_valid is True
        assert not issues
    
    def test_fix_price_zero_lost(self):
        """Проверка исправления потерянного нуля в цене."""
        line = {'qty': 2, 'price': 25000, 'amount': 500000}  # Должно быть 250000
        is_valid, fixed_line, issues = self.validator.validate_line(line)
        
        assert is_valid is True
        assert len(issues) == 1
        assert issues[0]['type'] == 'PRICE_ZERO_LOST'
        assert fixed_line['price'] == Decimal('250000')
    
    def test_fix_price_extra_zero(self):
        """Проверка исправления лишнего нуля в цене."""
        line = {'qty': 2, 'price': 250000, 'amount': 50000}  # Должно быть 25000
        is_valid, fixed_line, issues = self.validator.validate_line(line)
        
        assert is_valid is True
        assert len(issues) == 1
        assert issues[0]['type'] == 'PRICE_EXTRA_ZERO'
        assert fixed_line['price'] == Decimal('25000')
    
    def test_fix_qty_decimal(self):
        """Проверка исправления дробного количества."""
        line = {'qty': 15, 'price': 10000, 'amount': 15000}  # Должно быть qty=1.5
        is_valid, fixed_line, issues = self.validator.validate_line(line)
        
        assert is_valid is True
        assert len(issues) == 1
        assert issues[0]['type'] == 'QTY_DECIMAL_MISSED'
        assert fixed_line['qty'] == Decimal('1.5')
    
    def test_validate_invoice(self):
        """Проверка валидации всей накладной."""
        invoice_data = {
            'lines': [
                {'qty': 2, 'price': 15000, 'amount': 30000},  # Валидная строка
                {'qty': 2, 'price': 25000, 'amount': 500000},  # Исправимая ошибка (потерянный ноль)
                {'qty': 2, 'price': 15000, 'amount': 40000},  # Неисправимая ошибка
            ]
        }
        
        result = self.validator.validate_invoice(invoice_data)
        
        # Проверка общего результата
        assert 'issues' in result
        assert 'auto_fixed_count' in result
        assert result['auto_fixed_count'] == 1
        
        # Проверка исправленных строк
        assert len(result['issues']) == 2  # 1 исправленная + 1 неисправимая
        assert result['lines'][1]['auto_fixed'] is True
        assert result['lines'][1]['price'] == Decimal('250000')
        
        # Проверка неисправленных строк
        assert 'auto_fixed' not in result['lines'][0]  # Валидная строка
        assert 'auto_fixed' not in result['lines'][2]  # Неисправимая ошибка 