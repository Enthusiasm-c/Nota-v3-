from app.validators.sanity import SanityValidator

class TestSanityValidator:
    """Тесты для доменного валидатора sanity-правил."""
    
    def setup_method(self):
        """Настройка перед каждым тестом."""
        self.validator = SanityValidator(strict_mode=False)
        self.strict_validator = SanityValidator(strict_mode=True)
    
    def test_missing_fields(self):
        """Проверка строк с отсутствующими полями."""
        # Отсутствует name
        line = {'qty': 2, 'unit': 'kg', 'price': 15000, 'amount': 30000}
        is_valid, fixed_line, issues = self.validator.validate_line(line)
        
        assert is_valid is False
        assert len(issues) == 1
        assert issues[0]['type'] == 'MISSING_FIELDS'
        
        # Отсутствуют несколько полей
        line = {'name': 'Ayam', 'price': 15000}
        is_valid, fixed_line, issues = self.validator.validate_line(line)
        
        assert is_valid is False
        assert len(issues) == 1
        assert 'qty' in issues[0]['message']
        assert 'unit' in issues[0]['message']
        assert 'amount' in issues[0]['message']
    
    def test_unit_validation_non_strict(self):
        """Проверка валидации единиц измерения в нестрогом режиме."""
        # Правильная единица измерения
        line = {'name': 'Telur ayam', 'qty': 10, 'unit': 'pcs', 'price': 2000, 'amount': 20000}
        is_valid, fixed_line, issues = self.validator.validate_line(line)
        
        assert is_valid is True
        assert not issues
        
        # Неверная единица измерения (kg вместо pcs), но в нестрогом режиме это предупреждение
        line = {'name': 'Telur ayam', 'qty': 10, 'unit': 'kg', 'price': 2000, 'amount': 20000}
        is_valid, fixed_line, issues = self.validator.validate_line(line)
        
        assert is_valid is True  # В нестрогом режиме предупреждение не влияет на валидность
        assert len(issues) == 1
        assert issues[0]['type'] == 'UNIT_MISMATCH'
        assert issues[0]['severity'] == 'warning'
    
    def test_unit_validation_strict(self):
        """Проверка валидации единиц измерения в строгом режиме."""
        # Неверная единица измерения в строгом режиме
        line = {'name': 'Telur ayam', 'qty': 10, 'unit': 'kg', 'price': 2000, 'amount': 20000}
        is_valid, fixed_line, issues = self.strict_validator.validate_line(line)
        
        assert is_valid is False  # В строгом режиме предупреждение делает строку невалидной
        assert len(issues) == 1
        assert issues[0]['type'] == 'UNIT_MISMATCH'
    
    def test_unit_autocorrection(self):
        """Проверка автокоррекции единиц измерения."""
        # Определяем строку с неверной единицей
        line = {'name': 'Telur ayam', 'qty': 10, 'unit': 'kg', 'price': 2000, 'amount': 20000}
        is_valid, fixed_line, issues = self.validator.validate_line(line)
        
        assert is_valid is True
        assert fixed_line['unit'] == 'pcs'  # Должно быть исправлено
        assert fixed_line['auto_fixed'] is True
        assert issues[0]['fixed'] is True
    
    def test_price_range_validation(self):
        """Проверка валидации диапазонов цен."""
        # Цена в допустимом диапазоне
        line = {'name': 'Daging sapi', 'qty': 1, 'unit': 'kg', 'price': 120000, 'amount': 120000}
        is_valid, fixed_line, issues = self.validator.validate_line(line)
        
        assert is_valid is True
        assert not issues
        
        # Цена ниже диапазона
        line = {'name': 'Daging sapi', 'qty': 1, 'unit': 'kg', 'price': 50000, 'amount': 50000}
        is_valid, fixed_line, issues = self.validator.validate_line(line)
        
        assert is_valid is True  # В нестрогом режиме
        assert len(issues) == 1
        assert issues[0]['type'] == 'PRICE_TOO_LOW'
        
        # Цена выше диапазона
        line = {'name': 'Daging sapi', 'qty': 1, 'unit': 'kg', 'price': 350000, 'amount': 350000}
        is_valid, fixed_line, issues = self.validator.validate_line(line)
        
        assert is_valid is True  # В нестрогом режиме
        assert len(issues) == 1
        assert issues[0]['type'] == 'PRICE_TOO_HIGH'
    
    def test_weight_range_validation(self):
        """Проверка валидации диапазонов весов."""
        # Вес в допустимом диапазоне
        line = {'name': 'Daging sapi', 'qty': 5, 'unit': 'kg', 'price': 120000, 'amount': 600000}
        is_valid, fixed_line, issues = self.validator.validate_line(line)
        
        assert is_valid is True
        assert not issues
        
        # Вес выше диапазона
        line = {'name': 'Daging sapi', 'qty': 15, 'unit': 'kg', 'price': 120000, 'amount': 1800000}
        is_valid, fixed_line, issues = self.validator.validate_line(line)
        
        assert is_valid is True  # В нестрогом режиме
        assert len(issues) == 1
        assert issues[0]['type'] == 'WEIGHT_TOO_HIGH'
    
    def test_validate_invoice(self):
        """Проверка валидации всей накладной."""
        invoice_data = {
            'lines': [
                {'name': 'Ayam kampung', 'qty': 2, 'unit': 'kg', 'price': 120000, 'amount': 240000},  # OK
                {'name': 'Telur ayam', 'qty': 30, 'unit': 'kg', 'price': 2000, 'amount': 60000},  # Unit mismatch
                {'name': 'Gula pasir', 'qty': 100, 'unit': 'kg', 'price': 13000, 'amount': 1300000},  # Weight too high
            ]
        }
        
        result = self.validator.validate_invoice(invoice_data)
        
        # Проверка общего результата
        assert 'issues' in result
        assert 'auto_fixed_count' in result
        assert result['auto_fixed_count'] == 1  # Только одна строка должна быть исправлена
        
        # Проверка исправленных строк (единица измерения для яиц)
        assert result['lines'][1]['unit'] == 'pcs'
        assert result['lines'][1]['auto_fixed'] is True
        
        # Проверка предупреждений (вес сахара)
        weight_issue = None
        for issue in result['issues']:
            if issue['type'] == 'WEIGHT_TOO_HIGH':
                weight_issue = issue
                break
        
        assert weight_issue is not None
        assert weight_issue['line'] == 3  # 3-я строка 