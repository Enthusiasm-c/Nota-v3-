"""
Комплексные тесты для модуля app/postprocessing.py
"""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from app.models import ParsedData, Position
from app.postprocessing import (
    PRODUCT_CATEGORIES,
    PRODUCT_DEFAULT_UNITS,
    UNIT_MAPPING,
    autocorrect_name,
    clean_num,
    normalize_units,
    postprocess_parsed_data,
)


class TestCleanNum:
    """Тесты для функции clean_num"""

    def test_clean_num_none_input(self):
        """Тест с None входом"""
        result = clean_num(None)
        assert result is None

    def test_clean_num_none_with_default(self):
        """Тест с None входом и значением по умолчанию"""
        result = clean_num(None, 10.0)
        assert result == 10.0

    def test_clean_num_integer(self):
        """Тест с целым числом"""
        result = clean_num(42)
        assert result == 42.0

    def test_clean_num_float(self):
        """Тест с дробным числом"""
        result = clean_num(3.14)
        assert result == 3.14

    def test_clean_num_string_number(self):
        """Тест со строковым числом"""
        result = clean_num("123.45")
        assert result == 123.45

    def test_clean_num_string_with_comma(self):
        """Тест со строкой с запятой как разделителем"""
        result = clean_num("123,45")
        assert result == 123.45

    def test_clean_num_string_with_currency(self):
        """Тест со строкой с символом валюты"""
        result = clean_num("$123.45")
        assert result == 123.45

    def test_clean_num_string_with_spaces(self):
        """Тест со строкой с пробелами"""
        result = clean_num("1 234.56")
        assert result == 1234.56

    def test_clean_num_empty_string(self):
        """Тест с пустой строкой"""
        result = clean_num("", 5.0)
        assert result == 5.0

    def test_clean_num_invalid_string(self):
        """Тест с невалидной строкой"""
        result = clean_num("abc")
        assert result is None

    def test_clean_num_invalid_with_default(self):
        """Тест с невалидной строкой и значением по умолчанию"""
        result = clean_num("abc", 7.5)
        assert result == 7.5

    def test_clean_num_complex_string(self):
        """Тест со сложной строкой с различными символами"""
        result = clean_num("€1.234,56 EUR")
        assert result == 1234.56


class TestAutocorrectName:
    """Тесты для функции autocorrect_name"""

    def test_autocorrect_name_exact_match(self):
        """Тест точного совпадения"""
        allowed_names = ["apple", "banana", "orange"]
        result = autocorrect_name("apple", allowed_names)
        assert result == "apple"

    def test_autocorrect_name_case_insensitive(self):
        """Тест с учетом регистра"""
        allowed_names = ["Apple", "Banana", "Orange"]
        result = autocorrect_name("apple", allowed_names)
        assert result == "Apple"

    def test_autocorrect_name_small_distance(self):
        """Тест с малым расстоянием Левенштейна"""
        allowed_names = ["apple", "banana", "orange"]
        result = autocorrect_name("aple", allowed_names)  # пропущена одна буква
        assert result == "apple"

    def test_autocorrect_name_distance_two(self):
        """Тест с расстоянием Левенштейна = 2"""
        allowed_names = ["apple", "banana", "orange"]
        result = autocorrect_name("aplle", allowed_names)  # две ошибки
        assert result == "apple"

    def test_autocorrect_name_no_correction(self):
        """Тест когда коррекция не нужна (расстояние > 2)"""
        allowed_names = ["apple", "banana", "orange"]
        result = autocorrect_name("xyz", allowed_names)
        assert result == "xyz"

    def test_autocorrect_name_none_input(self):
        """Тест с None входом"""
        allowed_names = ["apple", "banana", "orange"]
        result = autocorrect_name(None, allowed_names)
        assert result is None

    def test_autocorrect_name_empty_list(self):
        """Тест с пустым списком разрешенных названий"""
        result = autocorrect_name("apple", [])
        assert result == "apple"

    def test_autocorrect_name_whitespace(self):
        """Тест с пробелами в названии"""
        allowed_names = ["apple", "banana", "orange"]
        result = autocorrect_name("  apple  ", allowed_names)
        assert result == "apple"

    @patch("app.postprocessing.logging")
    def test_autocorrect_name_logging(self, mock_logging):
        """Тест логирования в функции автокоррекции"""
        allowed_names = ["apple", "banana", "orange"]
        autocorrect_name("aple", allowed_names)

        # Проверяем что логирование происходило
        assert mock_logging.debug.call_count >= 2


class TestNormalizeUnits:
    """Тесты для функции normalize_units"""

    def test_normalize_units_exact_match(self):
        """Тест точного совпадения единицы в словаре"""
        result = normalize_units("kg")
        assert result == "kg"

    def test_normalize_units_case_insensitive(self):
        """Тест с учетом регистра"""
        result = normalize_units("KG")
        assert result == "kg"

    def test_normalize_units_plural_to_singular(self):
        """Тест преобразования множественного числа в единственное"""
        result = normalize_units("kilograms")
        assert result == "kg"

    def test_normalize_units_empty_input(self):
        """Тест с пустой единицей"""
        result = normalize_units("")
        assert result == "pcs"

    def test_normalize_units_none_input(self):
        """Тест с None входом"""
        result = normalize_units(None)
        assert result == "pcs"

    def test_normalize_units_unknown_unit(self):
        """Тест с неизвестной единицей"""
        result = normalize_units("unknown_unit")
        assert result == "unknown_unit"

    def test_normalize_units_with_product_name_vegetable(self):
        """Тест с названием продукта категории овощи"""
        result = normalize_units("", "fresh tomato")
        assert result == "kg"

    def test_normalize_units_with_product_name_dairy(self):
        """Тест с названием продукта категории молочные"""
        result = normalize_units("", "milk carton")
        assert result == "pcs"

    def test_normalize_units_with_product_name_beverage(self):
        """Тест с названием продукта категории напитки"""
        result = normalize_units("", "orange juice")
        assert result == "pcs"

    def test_normalize_units_with_product_name_no_category(self):
        """Тест с названием продукта без определенной категории"""
        result = normalize_units("", "unknown product")
        assert result == "pcs"

    def test_normalize_units_override_with_explicit_unit(self):
        """Тест что явно указанная единица имеет приоритет"""
        result = normalize_units("bottles", "tomato")  # должно вернуть btl, не kg
        assert result == "btl"

    def test_normalize_units_whitespace_handling(self):
        """Тест обработки пробелов"""
        result = normalize_units("  kg  ")
        assert result == "kg"


class TestConstants:
    """Тесты для констант модуля"""

    def test_unit_mapping_completeness(self):
        """Тест полноты маппинга единиц"""
        assert "kg" in UNIT_MAPPING
        assert "gram" in UNIT_MAPPING
        assert "liter" in UNIT_MAPPING
        assert "piece" in UNIT_MAPPING

    def test_unit_mapping_consistency(self):
        """Тест консистентности маппинга"""
        assert UNIT_MAPPING["kg"] == "kg"
        assert UNIT_MAPPING["kilogram"] == "kg"
        assert UNIT_MAPPING["kilograms"] == "kg"

    def test_product_default_units_coverage(self):
        """Тест покрытия единиц по умолчанию для категорий"""
        for category in PRODUCT_CATEGORIES.keys():
            assert category in PRODUCT_DEFAULT_UNITS

    def test_product_categories_structure(self):
        """Тест структуры категорий продуктов"""
        assert "vegetable" in PRODUCT_CATEGORIES
        assert "fruit" in PRODUCT_CATEGORIES
        assert "meat" in PRODUCT_CATEGORIES
        assert isinstance(PRODUCT_CATEGORIES["vegetable"], list)


class TestPostprocessParsedData:
    """Тесты для функции postprocess_parsed_data"""

    def test_postprocess_basic_data(self):
        """Тест базовой постобработки"""
        positions = [Position(name="apple", qty=5, price=2.0, total_price=10.0)]
        parsed = ParsedData(supplier="Test", positions=positions, total_price=10.0)

        with patch("app.postprocessing.load_products", return_value=[]):
            result = postprocess_parsed_data(parsed)

        assert result.supplier == "Test"
        assert len(result.positions) == 1
        assert result.total_price == 10.0

    def test_postprocess_clean_numbers(self):
        """Тест очистки числовых значений"""
        positions = [Position(name="apple", qty="5", price="$2.50", total_price="12.50")]
        parsed = ParsedData(supplier="Test", positions=positions, total_price="$12.50")

        with patch("app.postprocessing.load_products", return_value=[]):
            result = postprocess_parsed_data(parsed)

        assert result.positions[0].qty == 5.0
        assert result.positions[0].price == 2.50
        assert result.positions[0].total_price == 12.50
        assert result.total_price == 12.50

    def test_postprocess_date_conversion(self):
        """Тест конвертации даты"""
        positions = [Position(name="apple", qty=1, price=1.0)]
        parsed = ParsedData(supplier="Test", positions=positions, date="15.03.2024")

        with patch("app.postprocessing.load_products", return_value=[]):
            result = postprocess_parsed_data(parsed)

        assert result.date == date(2024, 3, 15)

    def test_postprocess_invalid_date(self):
        """Тест обработки невалидной даты"""
        positions = [Position(name="apple", qty=1, price=1.0)]
        parsed = ParsedData(supplier="Test", positions=positions, date="invalid_date")

        with patch("app.postprocessing.load_products", return_value=[]):
            result = postprocess_parsed_data(parsed)

        assert result.date == "invalid_date"  # должна остаться без изменений

    def test_postprocess_filter_empty_positions(self):
        """Тест фильтрации пустых позиций"""
        positions = [
            Position(name="apple", qty=1, price=1.0),
            Position(name="", qty=2, price=2.0),  # пустое название
            Position(name="Итого", qty=3, price=3.0),  # итого
            Position(name="banana", qty=4, price=4.0),
        ]
        parsed = ParsedData(supplier="Test", positions=positions)

        with patch("app.postprocessing.load_products", return_value=[]):
            result = postprocess_parsed_data(parsed)

        assert len(result.positions) == 2
        assert result.positions[0].name == "apple"
        assert result.positions[1].name == "banana"

    def test_postprocess_calculate_missing_total_price(self):
        """Тест вычисления отсутствующей total_price"""
        positions = [Position(name="apple", qty=5, price=2.0, total_price=None)]
        parsed = ParsedData(supplier="Test", positions=positions)

        with patch("app.postprocessing.load_products", return_value=[]):
            result = postprocess_parsed_data(parsed)

        assert result.positions[0].total_price == 10.0

    def test_postprocess_calculate_missing_price(self):
        """Тест вычисления отсутствующей цены"""
        positions = [Position(name="apple", qty=5, price=None, total_price=10.0)]
        parsed = ParsedData(supplier="Test", positions=positions)

        with patch("app.postprocessing.load_products", return_value=[]):
            result = postprocess_parsed_data(parsed)

        assert result.positions[0].price == 2.0

    def test_postprocess_calculate_total_sum(self):
        """Тест вычисления общей суммы"""
        positions = [
            Position(name="apple", qty=1, price=5.0, total_price=5.0),
            Position(name="banana", qty=2, price=3.0, total_price=6.0),
        ]
        parsed = ParsedData(supplier="Test", positions=positions, total_price=None)

        with patch("app.postprocessing.load_products", return_value=[]):
            result = postprocess_parsed_data(parsed)

        assert result.total_price == 11.0

    def test_postprocess_anomaly_correction_price(self):
        """Тест коррекции аномальной цены"""
        positions = [Position(name="apple", qty=1, price=20000000, total_price=20000000)]
        parsed = ParsedData(supplier="Test", positions=positions)

        with patch("app.postprocessing.load_products", return_value=[]):
            result = postprocess_parsed_data(parsed)

        assert result.positions[0].price == 2000000  # исправлено /10

    def test_postprocess_anomaly_correction_qty(self):
        """Тест коррекции аномального количества"""
        positions = [Position(name="apple", qty=5000, price=1.0, total_price=5000)]
        parsed = ParsedData(supplier="Test", positions=positions)

        with patch("app.postprocessing.load_products", return_value=[]):
            result = postprocess_parsed_data(parsed)

        assert result.positions[0].qty == 500  # исправлено /10

    def test_postprocess_with_autocorrect(self):
        """Тест автокоррекции названий"""
        mock_product = MagicMock()
        mock_product.alias = "apple"

        positions = [Position(name="aple", qty=1, price=1.0)]  # опечатка
        parsed = ParsedData(supplier="Test", positions=positions)

        with patch("app.postprocessing.load_products", return_value=[mock_product]):
            result = postprocess_parsed_data(parsed)

        assert result.positions[0].name == "apple"

    @patch("app.postprocessing.log_format_issues")
    def test_postprocess_long_name_logging(self, mock_log):
        """Тест логирования слишком длинных названий"""
        long_name = "a" * 35  # больше 30 символов
        positions = [Position(name=long_name, qty=1, price=1.0)]
        parsed = ParsedData(supplier="Test", positions=positions)

        with patch("app.postprocessing.load_products", return_value=[]):
            postprocess_parsed_data(parsed, req_id="test_123")

        mock_log.assert_called_with("test_123", "position.name", long_name, "< 30 chars")

    def test_postprocess_unit_normalization(self):
        """Тест нормализации единиц измерения"""
        positions = [Position(name="apple", qty=1, price=1.0, unit="kilograms")]
        parsed = ParsedData(supplier="Test", positions=positions)

        with patch("app.postprocessing.load_products", return_value=[]):
            result = postprocess_parsed_data(parsed)

        assert result.positions[0].unit == "kg"

    @patch("app.postprocessing.log_indonesian_invoice")
    @patch("app.postprocessing.logging")
    def test_postprocess_logging(self, mock_logging, mock_log_indonesian):
        """Тест логирования процесса постобработки"""
        positions = [Position(name="apple", qty=1, price=1.0)]
        parsed = ParsedData(supplier="Test", positions=positions)

        with patch("app.postprocessing.load_products", return_value=[]):
            postprocess_parsed_data(parsed, req_id="test_123")

        # Проверяем что происходило логирование
        assert mock_logging.info.call_count >= 1
        mock_log_indonesian.assert_called_once()

    def test_postprocess_exception_handling(self):
        """Тест обработки исключений"""
        positions = [Position(name="apple", qty=1, price=1.0)]
        parsed = ParsedData(supplier="Test", positions=positions)

        with patch("app.postprocessing.load_products", side_effect=Exception("Test error")):
            result = postprocess_parsed_data(parsed)

        # Должны вернуться исходные данные при ошибке
        assert result == parsed

    def test_postprocess_zero_division_protection(self):
        """Тест защиты от деления на ноль"""
        positions = [Position(name="apple", qty=0, price=None, total_price=10.0)]
        parsed = ParsedData(supplier="Test", positions=positions)

        with patch("app.postprocessing.load_products", return_value=[]):
            result = postprocess_parsed_data(parsed)

        # Цена не должна быть вычислена при qty=0
        assert result.positions[0].price is None

    def test_postprocess_complex_scenario(self):
        """Тест комплексного сценария"""
        positions = [
            Position(name="aple", qty="5", price="$2.50", total_price=None, unit="pieces"),
            Position(name="", qty=1, price=1.0),  # будет отфильтрована
            Position(name="banana", qty=3, price=None, total_price="$9.00", unit="kg"),
        ]
        parsed = ParsedData(supplier="Test Co", positions=positions, date="15/12/2024")

        mock_product = MagicMock()
        mock_product.alias = "apple"

        with patch("app.postprocessing.load_products", return_value=[mock_product]):
            result = postprocess_parsed_data(parsed)

        # Проверяем результаты
        assert len(result.positions) == 2  # одна отфильтрована
        assert result.positions[0].name == "apple"  # автокоррекция
        assert result.positions[0].qty == 5.0  # очищено
        assert result.positions[0].price == 2.50  # очищено
        assert result.positions[0].total_price == 12.5  # вычислено
        assert result.positions[0].unit == "pcs"  # нормализовано

        assert result.positions[1].name == "banana"
        assert result.positions[1].price == 3.0  # вычислено из total/qty
        assert result.positions[1].unit == "kg"

        assert result.total_price == 21.5  # сумма всех позиций
        assert result.date == date(2024, 12, 15)  # конвертирована


if __name__ == "__main__":
    pytest.main([__file__])
