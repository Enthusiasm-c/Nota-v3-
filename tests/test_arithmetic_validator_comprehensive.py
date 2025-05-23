"""
Комплексные тесты для модуля app/validators/arithmetic.py
"""

from decimal import Decimal
from unittest.mock import patch

import pytest

from app.validators.arithmetic import ArithmeticValidator


class TestArithmeticValidatorInit:
    """Тесты инициализации ArithmeticValidator"""

    def test_init_default_error_percent(self):
        """Тест инициализации с параметрами по умолчанию"""
        validator = ArithmeticValidator()
        assert validator.max_error_percent == 1.0

    def test_init_custom_error_percent(self):
        """Тест инициализации с пользовательским процентом ошибки"""
        validator = ArithmeticValidator(max_error_percent=2.5)
        assert validator.max_error_percent == 2.5


class TestValidateLine:
    """Тесты для метода validate_line"""

    def test_validate_line_valid_calculation(self):
        """Тест валидной строки с правильной арифметикой"""
        validator = ArithmeticValidator()
        line = {"qty": 5, "price": 100, "amount": 500}

        is_valid, fixed_line, issues = validator.validate_line(line)

        assert is_valid is True
        assert fixed_line == line
        assert issues == []

    def test_validate_line_missing_fields(self):
        """Тест строки с отсутствующими обязательными полями"""
        validator = ArithmeticValidator()
        line = {"qty": 5, "price": 100}  # отсутствует amount

        is_valid, fixed_line, issues = validator.validate_line(line)

        assert is_valid is False
        assert fixed_line == line
        assert issues == []

    def test_validate_line_invalid_values(self):
        """Тест строки с невалидными значениями"""
        validator = ArithmeticValidator()
        line = {"qty": "invalid", "price": 100, "amount": 500}

        is_valid, fixed_line, issues = validator.validate_line(line)

        assert is_valid is False
        assert len(issues) == 1
        assert issues[0]["type"] == "VALUE_ERROR"

    def test_validate_line_zero_values(self):
        """Тест строки с нулевыми значениями"""
        validator = ArithmeticValidator()
        line = {"qty": 0, "price": 0, "amount": 0}

        is_valid, fixed_line, issues = validator.validate_line(line)

        assert is_valid is True
        assert fixed_line == line
        assert issues == []

    def test_validate_line_within_error_tolerance(self):
        """Тест строки с ошибкой в пределах допустимой погрешности"""
        validator = ArithmeticValidator(max_error_percent=2.0)
        line = {"qty": 3, "price": 33.33, "amount": 100}  # 99.99 vs 100, погрешность ~0.01%

        is_valid, fixed_line, issues = validator.validate_line(line)

        assert is_valid is True
        assert issues == []

    def test_validate_line_exceeds_error_tolerance(self):
        """Тест строки с ошибкой превышающей допустимую погрешность"""
        validator = ArithmeticValidator(max_error_percent=1.0)
        line = {"qty": 5, "price": 100, "amount": 600}  # 500 vs 600, погрешность 20%

        with patch.object(validator, "_try_fix_arithmetic", return_value=(None, [])):
            is_valid, fixed_line, issues = validator.validate_line(line)

        assert is_valid is False
        assert len(issues) == 1
        assert issues[0]["type"] == "ARITHMETIC_ERROR"
        assert "error_percent" in issues[0]

    def test_validate_line_decimal_values(self):
        """Тест строки с дробными значениями"""
        validator = ArithmeticValidator()
        line = {"qty": "2.5", "price": "12.40", "amount": "31.00"}

        is_valid, fixed_line, issues = validator.validate_line(line)

        assert is_valid is True
        assert issues == []

    def test_validate_line_with_successful_fix(self):
        """Тест строки с успешным исправлением"""
        validator = ArithmeticValidator()
        line = {"qty": 5, "price": 100, "amount": 600}

        fixed_data = {"qty": Decimal("5"), "price": Decimal("120"), "amount": Decimal("600")}
        fix_issues = [{"type": "PRICE_CORRECTED", "old": "100", "fix": "120"}]

        with patch.object(validator, "_try_fix_arithmetic", return_value=(fixed_data, fix_issues)):
            is_valid, fixed_line, issues = validator.validate_line(line)

        assert is_valid is True
        assert issues == fix_issues

    def test_validate_line_type_error_handling(self):
        """Тест обработки TypeError при работе с Decimal"""
        validator = ArithmeticValidator()
        line = {"qty": None, "price": 100, "amount": 500}

        is_valid, fixed_line, issues = validator.validate_line(line)

        assert is_valid is False
        assert len(issues) == 1
        assert issues[0]["type"] == "VALUE_ERROR"

    def test_validate_line_zero_expected_amount_nonzero_actual(self):
        """Тест случая когда ожидаемая сумма 0, а фактическая нет"""
        validator = ArithmeticValidator()
        line = {"qty": 0, "price": 100, "amount": 500}

        with patch.object(validator, "_try_fix_arithmetic", return_value=(None, [])):
            is_valid, fixed_line, issues = validator.validate_line(line)

        assert is_valid is False


class TestTryFixArithmetic:
    """Тесты для метода _try_fix_arithmetic"""

    def test_fix_price_zero_lost(self):
        """Тест исправления потерянного нуля в цене"""
        validator = ArithmeticValidator()
        qty = Decimal("5")
        price = Decimal("10")  # должно быть 100
        amount = Decimal("500")

        fixed_line, issues = validator._try_fix_arithmetic(qty, price, amount)

        assert fixed_line is not None
        assert fixed_line["price"] == Decimal("100")
        assert len(issues) == 1
        assert issues[0]["type"] == "PRICE_ZERO_LOST"

    def test_fix_price_extra_zero(self):
        """Тест исправления лишнего нуля в цене"""
        validator = ArithmeticValidator()
        qty = Decimal("5")
        price = Decimal("1000")  # должно быть 100
        amount = Decimal("500")

        fixed_line, issues = validator._try_fix_arithmetic(qty, price, amount)

        assert fixed_line is not None
        assert fixed_line["price"] == Decimal("100")
        assert len(issues) == 1
        assert issues[0]["type"] == "PRICE_EXTRA_ZERO"

    def test_fix_qty_decimal_missed(self):
        """Тест исправления пропущенной десятичной точки в количестве"""
        validator = ArithmeticValidator()
        qty = Decimal("25")  # должно быть 2.5
        price = Decimal("100")
        amount = Decimal("250")

        fixed_line, issues = validator._try_fix_arithmetic(qty, price, amount)

        assert fixed_line is not None
        assert fixed_line["qty"] == Decimal("2.5")
        assert len(issues) == 1
        assert issues[0]["type"] == "QTY_DECIMAL_MISSED"

    def test_fix_no_fix_possible(self):
        """Тест случая когда исправление невозможно"""
        validator = ArithmeticValidator()
        qty = Decimal("5")
        price = Decimal("100")
        amount = Decimal("1000")  # слишком большое расхождение

        fixed_line, issues = validator._try_fix_arithmetic(qty, price, amount)

        assert fixed_line is None
        assert issues == []

    def test_fix_price_zero_lost_edge_case(self):
        """Тест граничного случая для исправления цены (price >= 100000)"""
        validator = ArithmeticValidator()
        qty = Decimal("1")
        price = Decimal("100000")  # не должно исправляться
        amount = Decimal("1000000")

        fixed_line, issues = validator._try_fix_arithmetic(qty, price, amount)

        assert fixed_line is None
        assert issues == []

    def test_fix_price_extra_zero_edge_case(self):
        """Тест граничного случая для лишнего нуля (price <= 1000)"""
        validator = ArithmeticValidator()
        qty = Decimal("5")
        price = Decimal("1000")  # граничное значение
        amount = Decimal("500")

        fixed_line, issues = validator._try_fix_arithmetic(qty, price, amount)

        assert fixed_line is not None
        assert fixed_line["price"] == Decimal("100")

    def test_fix_qty_decimal_edge_case(self):
        """Тест граничного случая для количества (qty <= 10)"""
        validator = ArithmeticValidator()
        qty = Decimal("10")  # граничное значение
        price = Decimal("100")
        amount = Decimal("100")

        fixed_line, issues = validator._try_fix_arithmetic(qty, price, amount)

        assert fixed_line is not None
        assert fixed_line["qty"] == Decimal("1")

    def test_fix_price_zero_lost_high_tolerance(self):
        """Тест исправления цены с высокой погрешностью"""
        validator = ArithmeticValidator()
        qty = Decimal("5")
        price = Decimal("10")
        amount = Decimal("520")  # погрешность > 1%, но в пределах алгоритма

        fixed_line, issues = validator._try_fix_arithmetic(qty, price, amount)

        assert fixed_line is None  # погрешность слишком высокая


class TestValidateInvoice:
    """Тесты для метода validate_invoice"""

    def test_validate_invoice_all_valid_lines(self):
        """Тест накладной со всеми валидными строками"""
        validator = ArithmeticValidator()
        invoice_data = {
            "lines": [
                {"qty": 5, "price": 100, "amount": 500},
                {"qty": 3, "price": 50, "amount": 150},
            ]
        }

        result = validator.validate_invoice(invoice_data)

        assert result["auto_fixed_count"] == 0
        assert result["issues"] == []
        assert len(result["lines"]) == 2

    def test_validate_invoice_with_fixes(self):
        """Тест накладной с исправляемыми ошибками"""
        validator = ArithmeticValidator()
        invoice_data = {
            "lines": [
                {"qty": 5, "price": 10, "amount": 500},  # потерян ноль в цене
                {"qty": 3, "price": 50, "amount": 150},  # валидная строка
            ]
        }

        result = validator.validate_invoice(invoice_data)

        assert result["auto_fixed_count"] == 1
        assert len(result["issues"]) == 1
        assert result["issues"][0]["line"] == 1
        assert result["issues"][0]["type"] == "PRICE_ZERO_LOST"
        assert result["lines"][0]["auto_fixed"] is True

    def test_validate_invoice_with_unfixable_errors(self):
        """Тест накладной с неисправимыми ошибками"""
        validator = ArithmeticValidator()
        invoice_data = {
            "lines": [
                {"qty": 5, "price": 100, "amount": 1000},  # слишком большое расхождение
                {"qty": 3, "price": 50, "amount": 150},  # валидная строка
            ]
        }

        result = validator.validate_invoice(invoice_data)

        assert result["auto_fixed_count"] == 0
        assert len(result["issues"]) == 1
        assert result["issues"][0]["line"] == 1
        assert result["issues"][0]["type"] == "ARITHMETIC_ERROR"

    def test_validate_invoice_empty_lines(self):
        """Тест накладной без строк"""
        validator = ArithmeticValidator()
        invoice_data = {"lines": []}

        result = validator.validate_invoice(invoice_data)

        assert result["auto_fixed_count"] == 0
        assert result["issues"] == []
        assert result["lines"] == []

    def test_validate_invoice_no_lines_field(self):
        """Тест накладной без поля lines"""
        validator = ArithmeticValidator()
        invoice_data = {"total": 1000}

        result = validator.validate_invoice(invoice_data)

        assert result["auto_fixed_count"] == 0
        assert result["issues"] == []
        assert result["lines"] == []

    def test_validate_invoice_mixed_scenarios(self):
        """Тест накладной со смешанными сценариями"""
        validator = ArithmeticValidator()
        invoice_data = {
            "lines": [
                {"qty": 5, "price": 100, "amount": 500},  # валидная
                {"qty": 3, "price": 10, "amount": 300},  # потерян ноль в цене
                {"qty": "invalid", "price": 50, "amount": 150},  # невалидные данные
                {"qty": 2, "price": 25, "amount": 50},  # валидная
            ]
        }

        result = validator.validate_invoice(invoice_data)

        assert result["auto_fixed_count"] == 1  # одна исправлена
        assert len(result["issues"]) >= 1  # минимум одна ошибка (невалидные данные)

        # Проверяем что исправленная строка отмечена
        fixed_lines = [line for line in result["lines"] if line.get("auto_fixed")]
        assert len(fixed_lines) == 1

    def test_validate_invoice_preserves_other_fields(self):
        """Тест что валидатор сохраняет другие поля накладной"""
        validator = ArithmeticValidator()
        invoice_data = {
            "supplier": "Test Supplier",
            "date": "2024-01-01",
            "total": 650,
            "lines": [
                {"qty": 5, "price": 100, "amount": 500, "name": "Product A"},
                {"qty": 3, "price": 50, "amount": 150, "name": "Product B"},
            ],
        }

        result = validator.validate_invoice(invoice_data)

        assert result["supplier"] == "Test Supplier"
        assert result["date"] == "2024-01-01"
        assert result["total"] == 650
        assert result["lines"][0]["name"] == "Product A"
        assert result["lines"][1]["name"] == "Product B"

    def test_validate_invoice_line_numbering(self):
        """Тест правильной нумерации строк в issues"""
        validator = ArithmeticValidator()
        invoice_data = {
            "lines": [
                {"qty": 5, "price": 100, "amount": 500},  # строка 1 - валидная
                {"qty": 3, "price": 10, "amount": 300},  # строка 2 - исправимая
                {"qty": 2, "price": 100, "amount": 300},  # строка 3 - неисправимая
            ]
        }

        result = validator.validate_invoice(invoice_data)

        # Проверяем номера строк в issues
        line_numbers = [issue["line"] for issue in result["issues"]]
        assert 2 in line_numbers  # исправимая ошибка в строке 2
        assert 3 in line_numbers  # неисправимая ошибка в строке 3


class TestEdgeCases:
    """Тесты граничных случаев"""

    def test_very_small_numbers(self):
        """Тест с очень малыми числами"""
        validator = ArithmeticValidator()
        line = {"qty": 0.001, "price": 0.001, "amount": 0.000001}

        is_valid, fixed_line, issues = validator.validate_line(line)

        assert is_valid is True

    def test_very_large_numbers(self):
        """Тест с очень большими числами"""
        validator = ArithmeticValidator()
        line = {"qty": 1000000, "price": 1000000, "amount": 1000000000000}

        is_valid, fixed_line, issues = validator.validate_line(line)

        assert is_valid is True

    def test_negative_values(self):
        """Тест с отрицательными значениями"""
        validator = ArithmeticValidator()
        line = {"qty": -5, "price": 100, "amount": -500}

        is_valid, fixed_line, issues = validator.validate_line(line)

        assert is_valid is True

    def test_string_numbers(self):
        """Тест со строковыми числами"""
        validator = ArithmeticValidator()
        line = {"qty": "5.0", "price": "100.00", "amount": "500.00"}

        is_valid, fixed_line, issues = validator.validate_line(line)

        assert is_valid is True

    def test_scientific_notation(self):
        """Тест с научной нотацией"""
        validator = ArithmeticValidator()
        line = {"qty": "1e2", "price": "1e1", "amount": "1e3"}  # 100 * 10 = 1000

        is_valid, fixed_line, issues = validator.validate_line(line)

        assert is_valid is True

    def test_empty_strings(self):
        """Тест с пустыми строками"""
        validator = ArithmeticValidator()
        line = {"qty": "", "price": 100, "amount": 500}

        is_valid, fixed_line, issues = validator.validate_line(line)

        assert is_valid is False
        assert len(issues) == 1
        assert issues[0]["type"] == "VALUE_ERROR"


class TestLogging:
    """Тесты логирования"""

    @patch("app.validators.arithmetic.logger")
    def test_logging_missing_fields(self, mock_logger):
        """Тест логирования при отсутствии полей"""
        validator = ArithmeticValidator()
        line = {"qty": 5}

        validator.validate_line(line)

        mock_logger.warning.assert_called_once()

    @patch("app.validators.arithmetic.logger")
    def test_logging_value_errors(self, mock_logger):
        """Тест логирования ошибок значений"""
        validator = ArithmeticValidator()
        line = {"qty": "invalid", "price": 100, "amount": 500}

        validator.validate_line(line)

        mock_logger.warning.assert_called_once()

    @patch("app.validators.arithmetic.logger")
    def test_logging_successful_fixes(self, mock_logger):
        """Тест логирования успешных исправлений"""
        validator = ArithmeticValidator()
        line = {"qty": 5, "price": 10, "amount": 500}  # потерян ноль в цене

        validator.validate_line(line)

        mock_logger.info.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__])
