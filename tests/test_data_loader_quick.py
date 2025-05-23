"""
Быстрые тесты для модуля app/data_loader.py
"""

from unittest.mock import mock_open, patch

import pytest

from app.data_loader import load_products, load_suppliers, load_units


class TestLoadProducts:
    """Тесты для функции load_products"""

    @patch("app.data_loader.read_aliases")
    @patch("builtins.open", new_callable=mock_open)
    def test_load_products_success(self, mock_file, mock_read_aliases):
        """Тест успешной загрузки продуктов"""
        # Мокируем содержимое CSV файла
        mock_file.return_value.read.return_value = (
            "id,name,alias,unit,price_hint\n1,Apple,apple,kg,2.5\n"
        )
        mock_read_aliases.return_value = {"red_apple": (1, "red_apple")}

        products = load_products()

        assert len(products) >= 1
        assert any(p.name == "Apple" for p in products)

    @patch("app.data_loader.read_aliases")
    @patch("builtins.open")
    def test_load_products_file_not_found(self, mock_open_func, mock_read_aliases):
        """Тест обработки отсутствующего файла"""
        mock_open_func.side_effect = FileNotFoundError("File not found")
        mock_read_aliases.return_value = {}

        with pytest.raises(FileNotFoundError):
            load_products()

    @patch("app.data_loader.read_aliases")
    @patch("builtins.open", new_callable=mock_open)
    def test_load_products_empty_file(self, mock_file, mock_read_aliases):
        """Тест с пустым файлом"""
        mock_file.return_value.read.return_value = "id,name,alias,unit,price_hint\n"
        mock_read_aliases.return_value = {}

        products = load_products()

        assert products == []


class TestLoadSuppliers:
    """Тесты для функции load_suppliers"""

    @patch("builtins.open", new_callable=mock_open)
    def test_load_suppliers_success(self, mock_file):
        """Тест успешной загрузки поставщиков"""
        mock_file.return_value.read.return_value = "id,name,code\n1,Test Supplier,TS001\n"

        suppliers = load_suppliers()

        assert len(suppliers) == 1
        assert suppliers[0]["name"] == "Test Supplier"

    @patch("builtins.open")
    def test_load_suppliers_file_not_found(self, mock_open_func):
        """Тест обработки отсутствующего файла поставщиков"""
        mock_open_func.side_effect = FileNotFoundError("File not found")

        with pytest.raises(FileNotFoundError):
            load_suppliers()


class TestLoadUnits:
    """Тесты для функции load_units"""

    def test_load_units_returns_list(self):
        """Тест что функция возвращает список единиц"""
        units = load_units()

        assert isinstance(units, list)
        assert len(units) > 0
        assert "kg" in units
        assert "pcs" in units

    def test_load_units_contains_expected_units(self):
        """Тест наличия ожидаемых единиц измерения"""
        units = load_units()

        expected_units = ["kg", "g", "l", "ml", "pcs", "pack"]
        for unit in expected_units:
            assert unit in units


if __name__ == "__main__":
    pytest.main([__file__])
