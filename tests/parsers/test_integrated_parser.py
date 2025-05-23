"""
Тесты для интегрированного парсера команд.
"""

from app.parsers.command_parser import parse_command, parse_compound_command


class TestIntegratedParser:
    """Тесты для интегрированного парсера команд."""

    def test_line_price_command(self):
        """Тест парсинга команды изменения цены."""
        result = parse_command("строка 1 цена 500")
        assert result["action"] == "edit_price"
        assert result["line"] == 0
        assert result["value"] == 500.0
        assert result["source"] == "local_parser"

        # Альтернативный синтаксис
        result = parse_command("line 2 price 1500")
        assert result["action"] == "edit_price"
        assert result["line"] == 1
        assert result["value"] == 1500.0

        # Дробное число с точкой
        result = parse_command("строка 3 цена 123.45")
        assert result["action"] == "edit_price"
        assert result["line"] == 2
        assert result["value"] == 123.45

        # Дробное число с запятой
        result = parse_command("строка 4 цена 67,89")
        assert result["action"] == "edit_price"
        assert result["line"] == 3
        assert result["value"] == 67.89

        # Число с K (тысячи)
        result = parse_command("строка 5 цена 2k")
        assert result["action"] == "edit_price"
        assert result["line"] == 4
        assert result["value"] == 2000.0

    def test_line_name_command(self):
        """Тест парсинга команды изменения названия."""
        result = parse_command("строка 1 название Тестовый продукт")
        assert result["action"] == "edit_name"
        assert result["line"] == 0
        assert result["value"] == "Тестовый продукт"

        # Альтернативный синтаксис
        result = parse_command("line 2 name Test product")
        assert result["action"] == "edit_name"
        assert result["line"] == 1
        assert result["value"] == "Test product"

    def test_line_qty_command(self):
        """Тест парсинга команды изменения количества."""
        result = parse_command("строка 1 количество 10")
        assert result["action"] == "edit_quantity"
        assert result["line"] == 0
        assert result["value"] == 10.0

        # Дробное число
        result = parse_command("строка 2 количество 1.5")
        assert result["action"] == "edit_quantity"
        assert result["line"] == 1
        assert result["value"] == 1.5

        # Альтернативный синтаксис
        result = parse_command("line 3 qty 5")
        assert result["action"] == "edit_quantity"
        assert result["line"] == 2
        assert result["value"] == 5.0

    def test_line_unit_command(self):
        """Тест парсинга команды изменения единицы измерения."""
        result = parse_command("строка 1 единица кг")
        assert result["action"] == "edit_unit"
        assert result["line"] == 0
        assert result["value"] == "кг"

        # Альтернативный синтаксис
        result = parse_command("line 2 unit pcs")
        assert result["action"] == "edit_unit"
        assert result["line"] == 1
        assert result["value"] == "pcs"

    def test_date_command(self):
        """Тест парсинга команды изменения даты."""
        result = parse_command("дата 01.02.2023")
        assert result["action"] == "set_date"
        assert result["value"] == "2023-02-01"

        # ISO формат
        result = parse_command("date 2023-12-31")
        assert result["action"] == "set_date"
        assert result["value"] == "2023-12-31"

        # С текстовым месяцем
        result = parse_command("дата 15 января 2024")
        assert result["action"] == "set_date"
        assert result["value"] == "2024-01-15"

        # С английским месяцем
        result = parse_command("date 20 december 2023")
        assert result["action"] == "set_date"
        assert result["value"] == "2023-12-20"

        # Другой формат команды
        result = parse_command("изменить дату на 05.04.2023")
        assert result["action"] == "set_date"
        assert result["value"] == "2023-04-05"

    def test_compound_command(self):
        """Тест парсинга составных команд."""
        results = parse_compound_command("строка 1 цена 500; строка 2 количество 3")
        assert len(results) == 2

        assert results[0]["action"] == "edit_price"
        assert results[0]["line"] == 0
        assert results[0]["value"] == 500.0

        assert results[1]["action"] == "edit_quantity"
        assert results[1]["line"] == 1
        assert results[1]["value"] == 3.0

        # Смешанные команды
        results = parse_compound_command("дата 01.02.2023; строка 1 название Тестовый продукт")
        assert len(results) == 2

        assert results[0]["action"] == "set_date"
        assert results[0]["value"] == "2023-02-01"

        assert results[1]["action"] == "edit_name"
        assert results[1]["line"] == 0
        assert results[1]["value"] == "Тестовый продукт"

    def test_error_handling(self):
        """Тест обработки ошибок."""
        # Неверный номер строки
        result = parse_command("строка 0 цена 100")
        assert result["action"] == "unknown"
        assert result["error"] == "line_out_of_range"

        # Превышение границ инвойса
        result = parse_command("строка 5 цена 100", invoice_lines=3)
        assert result["action"] == "unknown"
        assert result["error"] == "line_out_of_range"

        # Неверный формат цены
        result = parse_command("строка 1 цена абв")
        assert result["action"] == "unknown"
        assert "error" in result

        # Пустая команда
        result = parse_command("")
        assert result["action"] == "unknown"
        assert result["error"] == "empty_command"

        # Нераспознанная команда
        result = parse_command("какой-то нераспознанный текст")
        assert result["action"] == "unknown"
        assert "error" in result
