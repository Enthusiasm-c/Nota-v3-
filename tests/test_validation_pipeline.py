from decimal import Decimal
from app.validators.pipeline import ValidationPipeline

class TestValidationPipeline:
    """Тесты для полного пайплайна валидации."""
    
    def setup_method(self):
        """Настройка перед каждым тестом."""
        self.pipeline = ValidationPipeline(arithmetic_max_error=1.0, strict_mode=False)
        self.strict_pipeline = ValidationPipeline(arithmetic_max_error=1.0, strict_mode=True)
    
    def test_validate_empty_invoice(self):
        """Тест валидации пустой накладной."""
        invoice_data = {'lines': []}
        result = self.pipeline.validate(invoice_data)
        
        assert 'metadata' in result
        assert result['metadata']['total_lines'] == 0
        assert result['metadata']['total_issues'] == 0
        assert result['metadata']['accuracy'] == 0
    
    def test_validate_valid_invoice(self):
        """Тест валидации корректной накладной."""
        invoice_data = {
            'lines': [
                {'name': 'Daging sapi', 'qty': 2, 'unit': 'kg', 'price': 120000, 'amount': 240000},
                {'name': 'Beras putih', 'qty': 5, 'unit': 'kg', 'price': 12000, 'amount': 60000}
            ]
        }
        
        result = self.pipeline.validate(invoice_data)
        
        assert 'metadata' in result
        assert result['metadata']['total_lines'] == 2
        assert result['metadata']['total_issues'] == 0
        assert result['metadata']['accuracy'] == 1.0
    
    def test_validate_fixable_invoice(self):
        """Тест валидации накладной с исправимыми ошибками."""
        invoice_data = {
            'lines': [
                {'name': 'Daging sapi', 'qty': 2, 'unit': 'kg', 'price': 120000, 'amount': 240000},  # OK
                {'name': 'Kecap manis', 'qty': 2, 'unit': 'kg', 'price': 25000, 'amount': 500000},   # Потерянный ноль
                {'name': 'Telur ayam', 'qty': 30, 'unit': 'kg', 'price': 2000, 'amount': 60000}      # Неверная единица
            ]
        }
        
        result = self.pipeline.validate(invoice_data)
        
        assert 'metadata' in result
        assert result['metadata']['total_lines'] == 3
        assert result['metadata']['total_issues'] > 0
        assert result['metadata']['auto_fixed'] == 2  # Исправлены обе ошибки
        assert result['metadata']['accuracy'] == 1.0  # Все строки валидны после исправления
        
        # Проверяем исправления
        assert result['lines'][1]['price'] == Decimal('250000')  # Исправленная цена
        assert result['lines'][2]['unit'] == 'pcs'               # Исправленная единица
    
    def test_validate_with_unfixable_errors(self):
        """Тест валидации накладной с неисправимыми ошибками."""
        invoice_data = {
            'lines': [
                {'name': 'Daging sapi', 'qty': 2, 'unit': 'kg', 'price': 120000, 'amount': 240000},  # OK
                {'name': 'Item', 'qty': 3, 'unit': 'kg', 'price': 10000, 'amount': 50000}            # Неисправимая ошибка
            ]
        }
        
        result = self.pipeline.validate(invoice_data)
        
        assert 'metadata' in result
        assert result['metadata']['total_lines'] == 2
        assert result['metadata']['lines_with_issues'] == 1
        assert result['metadata']['accuracy'] == 0.5  # 1 из 2 строк корректная
        
        # Проверяем, что проблемы сгруппированы по строкам
        assert 'issues_by_line' in result
        assert 2 in result['issues_by_line']  # Проблема во второй строке
        issues = result['issues_by_line'][2]
        assert any(issue['type'] == 'ARITHMETIC_ERROR' for issue in issues)
    
    def test_strict_mode(self):
        """Тест валидации в строгом режиме."""
        invoice_data = {
            'lines': [
                {'name': 'Daging sapi', 'qty': 2, 'unit': 'kg', 'price': 50000, 'amount': 100000}  # Цена ниже ожидаемой
            ]
        }
        
        # В нестрогом режиме это только предупреждение
        result = self.pipeline.validate(invoice_data)
        assert result['metadata']['accuracy'] == 1.0
        
        # В строгом режиме это ошибка
        strict_result = self.strict_pipeline.validate(invoice_data)
        assert strict_result['metadata']['accuracy'] < 1.0 