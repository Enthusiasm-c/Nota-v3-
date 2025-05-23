"""
Комплексные тесты для модуля app/matcher.py
"""

from unittest.mock import patch

import pytest

from app.matcher import (
    PRODUCT_VARIANTS,
    UNIT_PATTERN,
    calculate_similarity,
    calculate_string_similarity,
    check_unit_compatibility,
    find_best_match,
    fuzzy_best,
    fuzzy_find,
    fuzzy_match_product,
    match_positions,
    match_supplier,
    normalize_name,
    normalize_product_name,
    normalize_unit,
)
from app.models import Product


class TestNormalizeProductName:
    """Тесты для функции normalize_product_name"""

    def test_normalize_none_input(self):
        """Тест с None входом"""
        result = normalize_product_name(None)
        assert result == ""

    def test_normalize_empty_string(self):
        """Тест с пустой строкой"""
        result = normalize_product_name("")
        assert result == ""

    def test_normalize_basic_string(self):
        """Тест базовой нормализации"""
        result = normalize_product_name("Apple")
        assert result == "apple"

    def test_normalize_with_spaces(self):
        """Тест с пробелами"""
        result = normalize_product_name("  Fresh Apple  ")
        assert result == "apple"

    def test_normalize_plural_to_singular(self):
        """Тест приведения к единственному числу"""
        result = normalize_product_name("apples")
        assert result == "apple"

    def test_normalize_ies_ending(self):
        """Тест слов заканчивающихся на -ies"""
        result = normalize_product_name("berries")
        assert result == "berry"

    def test_normalize_es_ending(self):
        """Тест слов заканчивающихся на -es"""
        result = normalize_product_name("boxes")
        assert result == "boxe"

    def test_normalize_with_unit(self):
        """Тест удаления единиц измерения"""
        result = normalize_product_name("apple 5 kg")
        assert result == "apple"

    def test_normalize_with_fillers(self):
        """Тест удаления слов-филлеров"""
        result = normalize_product_name("fresh organic apple")
        assert result == "apple"

    def test_normalize_variant_mapping(self):
        """Тест маппинга вариантов"""
        result = normalize_product_name("chickpeas")
        assert result == "chickpeas"

    def test_normalize_short_word(self):
        """Тест коротких слов (не убираем s)"""
        result = normalize_product_name("gas")
        assert result == "gas"


class TestCalculateStringSimilarity:
    """Тесты для функции calculate_string_similarity"""

    def test_similarity_none_inputs(self):
        """Тест с None входами"""
        assert calculate_string_similarity(None, None) == 0.0
        assert calculate_string_similarity("test", None) == 0.0
        assert calculate_string_similarity(None, "test") == 0.0

    def test_similarity_identical_strings(self):
        """Тест идентичных строк"""
        result = calculate_string_similarity("apple", "apple")
        assert result == 1.0

    def test_similarity_empty_strings(self):
        """Тест пустых строк"""
        result = calculate_string_similarity("", "")
        assert result == 0.0

    def test_similarity_normalized_match(self):
        """Тест совпадения после нормализации"""
        result = calculate_string_similarity("Apple", "apple")
        assert result == 1.0

    def test_similarity_partial_match(self):
        """Тест частичного совпадения"""
        result = calculate_string_similarity("apple", "aple")
        assert result > 0.8

    def test_similarity_different_strings(self):
        """Тест разных строк"""
        result = calculate_string_similarity("apple", "orange")
        assert result < 0.5

    def test_similarity_substring_match(self):
        """Тест вхождения подстроки"""
        result = calculate_string_similarity("apple", "green apple")
        assert result >= 0.85

    def test_similarity_plural_variant(self):
        """Тест варианта единственного/множественного числа"""
        result = calculate_string_similarity("apple", "apples")
        assert result >= 0.9

    @patch("app.matcher.get_string_similarity_cached")
    @patch("app.matcher.set_string_similarity_cached")
    def test_similarity_caching(self, mock_set_cache, mock_get_cache):
        """Тест кеширования результатов"""
        mock_get_cache.return_value = None

        calculate_string_similarity("test1", "test2")

        mock_get_cache.assert_called_once()
        mock_set_cache.assert_called_once()


class TestFuzzyFind:
    """Тесты для функции fuzzy_find"""

    def test_fuzzy_find_empty_query(self):
        """Тест с пустым запросом"""
        items = [{"name": "apple"}, {"name": "banana"}]
        result = fuzzy_find("", items)
        assert result == []

    def test_fuzzy_find_empty_items(self):
        """Тест с пустым списком элементов"""
        result = fuzzy_find("apple", [])
        assert result == []

    def test_fuzzy_find_dict_items(self):
        """Тест поиска в словарях"""
        items = [
            {"name": "apple", "id": 1},
            {"name": "banana", "id": 2},
            {"name": "pineapple", "id": 3},
        ]

        result = fuzzy_find("apple", items, threshold=0.6)

        assert len(result) >= 1
        assert any(r["name"] == "apple" for r in result)

    def test_fuzzy_find_object_items(self):
        """Тест поиска в объектах"""

        class TestItem:
            def __init__(self, name, id):
                self.name = name
                self.id = id

        items = [TestItem("apple", 1), TestItem("banana", 2), TestItem("pineapple", 3)]

        result = fuzzy_find("apple", items, threshold=0.6)

        assert len(result) >= 1

    def test_fuzzy_find_threshold_filtering(self):
        """Тест фильтрации по порогу"""
        items = [{"name": "apple"}, {"name": "xyz"}]

        result = fuzzy_find("apple", items, threshold=0.9)

        # Только apple должен пройти высокий порог
        assert len(result) == 1
        assert result[0]["name"] == "apple"

    def test_fuzzy_find_limit(self):
        """Тест ограничения количества результатов"""
        items = [{"name": "apple1"}, {"name": "apple2"}, {"name": "apple3"}, {"name": "apple4"}]

        result = fuzzy_find("apple", items, limit=2)

        assert len(result) <= 2

    def test_fuzzy_find_custom_key(self):
        """Тест поиска по пользовательскому ключу"""
        items = [{"title": "apple", "id": 1}]

        result = fuzzy_find("apple", items, key="title")

        assert len(result) == 1


class TestFuzzyBest:
    """Тесты для функции fuzzy_best"""

    def test_fuzzy_best_empty_query(self):
        """Тест с пустым запросом"""
        items = {"apple": {"id": 1}}
        result = fuzzy_best("", items)
        assert result == ("", 0.0)

    def test_fuzzy_best_dict_input(self):
        """Тест с входным словарем"""
        items = {"apple": {"id": 1}, "banana": {"id": 2}}

        result = fuzzy_best("apple", items)

        assert result[0] == "apple"
        assert result[1] > 90.0  # Высокая оценка для точного совпадения

    def test_fuzzy_best_list_input(self):
        """Тест с входным списком"""
        items = [{"name": "apple", "id": 1}, {"name": "banana", "id": 2}]

        result = fuzzy_best("apple", items)

        assert result[0] == "apple"
        assert result[1] > 90.0

    def test_fuzzy_best_no_match(self):
        """Тест когда нет подходящих совпадений"""
        items = {"apple": {"id": 1}}

        result = fuzzy_best("xyz", items, threshold=0.9)

        assert result == ("", 0.0)

    def test_fuzzy_best_with_threshold(self):
        """Тест с порогом схожести"""
        items = {"apple": {"id": 1}}

        # Низкий порог - должно найти
        result1 = fuzzy_best("aple", items, threshold=0.5)
        assert result1[0] == "apple"

        # Высокий порог - не должно найти
        result2 = fuzzy_best("xyz", items, threshold=0.9)
        assert result2 == ("", 0.0)


class TestMatchSupplier:
    """Тесты для функции match_supplier"""

    def test_match_supplier_empty_name(self):
        """Тест с пустым именем поставщика"""
        suppliers = [{"name": "Test Supplier", "id": 1}]
        result = match_supplier("", suppliers)

        assert result["status"] == "unknown"
        assert result["id"] is None

    def test_match_supplier_empty_list(self):
        """Тест с пустым списком поставщиков"""
        result = match_supplier("Test", [])

        assert result["status"] == "unknown"
        assert result["name"] == "Test"

    def test_match_supplier_exact_match(self):
        """Тест точного совпадения"""
        suppliers = [
            {"name": "Test Supplier", "id": 1, "code": "TS001"},
            {"name": "Other Supplier", "id": 2, "code": "OS002"},
        ]

        result = match_supplier("Test Supplier", suppliers)

        assert result["status"] == "ok"
        assert result["id"] == 1
        assert result["code"] == "TS001"

    def test_match_supplier_fuzzy_match(self):
        """Тест нечеткого совпадения"""
        suppliers = [{"name": "Test Supplier", "id": 1, "code": "TS001"}]

        result = match_supplier("Test Supplyer", suppliers)  # опечатка

        assert result["status"] == "ok"
        assert result["id"] == 1

    def test_match_supplier_no_match(self):
        """Тест отсутствия совпадения"""
        suppliers = [{"name": "Test Supplier", "id": 1}]

        result = match_supplier("Completely Different", suppliers)

        assert result["status"] == "unknown"
        assert result["name"] == "Completely Different"

    def test_match_supplier_object_input(self):
        """Тест с объектами вместо словарей"""

        class Supplier:
            def __init__(self, name, id, code):
                self.name = name
                self.id = id
                self.code = code

        suppliers = [Supplier("Test Supplier", 1, "TS001")]

        result = match_supplier("Test Supplier", suppliers)

        assert result["status"] == "ok"
        assert result["id"] == 1

    def test_match_supplier_custom_threshold(self):
        """Тест с пользовательским порогом"""
        suppliers = [{"name": "Test Supplier", "id": 1}]

        # Высокий порог - не должно найти похожее совпадение
        result = match_supplier("Test Supplyer", suppliers, threshold=0.95)

        assert result["status"] == "unknown"


class TestMatchPositions:
    """Тесты для функции match_positions"""

    def test_match_positions_empty_lists(self):
        """Тест с пустыми списками"""
        result = match_positions([], [])
        assert result == []

    def test_match_positions_basic(self):
        """Тест базового сопоставления"""
        positions = [{"name": "apple", "qty": 5}]
        products = [Product(id="1", name="Apple", alias="apple", code="", unit="", price_hint=None)]

        result = match_positions(positions, products)

        assert len(result) == 1
        assert result[0]["status"] == "ok"
        assert result[0]["matched_name"] == "Apple"

    def test_match_positions_no_match(self):
        """Тест когда нет совпадений"""
        positions = [{"name": "xyz", "qty": 5}]
        products = [Product(id="1", name="Apple", alias="apple", code="", unit="", price_hint=None)]

        result = match_positions(positions, products)

        assert len(result) == 1
        assert result[0]["status"] == "unknown"
        assert result[0]["matched_name"] is None

    def test_match_positions_dict_products(self):
        """Тест с продуктами в виде словарей"""
        positions = [{"name": "apple", "qty": 5}]
        products = [{"name": "Apple", "id": "1"}]

        result = match_positions(positions, products)

        assert len(result) == 1
        assert result[0]["status"] == "ok"

    def test_match_positions_preserves_data(self):
        """Тест сохранения исходных данных позиций"""
        positions = [{"name": "apple", "qty": 5, "price": 100, "custom_field": "test"}]
        products = [Product(id="1", name="Apple", alias="apple", code="", unit="", price_hint=None)]

        result = match_positions(positions, products)

        assert result[0]["custom_field"] == "test"
        assert result[0]["qty"] == 5
        assert result[0]["price"] == 100


class TestFindBestMatch:
    """Тесты для функции find_best_match"""

    def test_find_best_match_basic(self):
        """Тест базового поиска лучшего совпадения"""
        position = {"name": "apple", "unit": "kg", "price": 100}
        products = [
            Product(id="1", name="Apple", alias="apple", code="", unit="kg", price_hint=None)
        ]

        result = find_best_match(position, products)

        assert result["status"] == "ok"
        assert result["matched_product"] is not None
        assert result["unit_match"] is True

    def test_find_best_match_no_match(self):
        """Тест когда нет совпадений"""
        position = {"name": "xyz", "unit": "kg"}
        products = [
            Product(id="1", name="Apple", alias="apple", code="", unit="kg", price_hint=None)
        ]

        result = find_best_match(position, products)

        assert result["status"] == "unknown"
        assert result["matched_product"] is None

    def test_find_best_match_unit_mismatch(self):
        """Тест несовпадения единиц измерения"""
        position = {"name": "apple", "unit": "pcs", "price": 100}
        products = [
            Product(id="1", name="Apple", alias="apple", code="", unit="kg", price_hint=None)
        ]

        result = find_best_match(position, products)

        assert result["status"] == "unit_mismatch"
        assert result["unit_match"] is False

    def test_find_best_match_price_hint(self):
        """Тест с подсказкой цены"""
        position = {"name": "apple", "price": 200}
        products = [
            Product(id="1", name="Apple", alias="apple", code="", unit="", price_hint=100.0)
        ]

        result = find_best_match(position, products)

        # Уверенность должна снизиться из-за большой разницы в цене
        assert result["confidence"] < 1.0


class TestFuzzyMatchProduct:
    """Тесты для функции fuzzy_match_product"""

    def test_fuzzy_match_empty_query(self):
        """Тест с пустым запросом"""
        products = [Product(id="1", name="Apple", alias="apple", code="", unit="", price_hint=None)]

        result = fuzzy_match_product("", products)

        assert result == (None, 0.0)

    def test_fuzzy_match_empty_products(self):
        """Тест с пустым списком продуктов"""
        result = fuzzy_match_product("apple", [])

        assert result == (None, 0.0)

    def test_fuzzy_match_by_name(self):
        """Тест поиска по названию"""
        products = [Product(id="1", name="Apple", alias="apple", code="", unit="", price_hint=None)]

        product, score = fuzzy_match_product("apple", products)

        assert product is not None
        assert score > 0.7

    def test_fuzzy_match_by_alias(self):
        """Тест поиска по алиасу"""
        products = [
            Product(id="1", name="Red Apple", alias="apple", code="", unit="", price_hint=None)
        ]

        product, score = fuzzy_match_product("apple", products)

        assert product is not None
        assert score > 0.7

    def test_fuzzy_match_dict_products(self):
        """Тест с продуктами в виде словарей"""
        products = [{"name": "Apple", "alias": "apple", "id": "1"}]

        product, score = fuzzy_match_product("apple", products)

        assert product is not None
        assert score > 0.7

    def test_fuzzy_match_threshold(self):
        """Тест с порогом схожести"""
        products = [Product(id="1", name="Apple", alias="apple", code="", unit="", price_hint=None)]

        # Высокий порог - не должно найти слабое совпадение
        product, score = fuzzy_match_product("xyz", products, threshold=0.9)

        assert product is None


class TestNormalizeName:
    """Тесты для функции normalize_name (обратная совместимость)"""

    def test_normalize_name_basic(self):
        """Тест базовой нормализации имени"""
        result = normalize_name("Apple-Pie")
        assert result == "apple pie"

    def test_normalize_name_special_chars(self):
        """Тест замены специальных символов"""
        result = normalize_name("test_name-value/other.ext")
        assert result == "test name value other ext"

    def test_normalize_name_multiple_spaces(self):
        """Тест удаления лишних пробелов"""
        result = normalize_name("apple   pie    cake")
        assert result == "apple pie cake"


class TestNormalizeUnit:
    """Тесты для функции normalize_unit"""

    def test_normalize_unit_empty(self):
        """Тест с пустой единицей"""
        result = normalize_unit("")
        assert result == ""

    def test_normalize_unit_kg_variants(self):
        """Тест вариантов килограмма"""
        assert normalize_unit("kilogram") == "kg"
        assert normalize_unit("kilograms") == "kg"
        assert normalize_unit("кг") == "kg"

    def test_normalize_unit_pcs_variants(self):
        """Тест вариантов штук"""
        assert normalize_unit("piece") == "pcs"
        assert normalize_unit("pieces") == "pcs"
        assert normalize_unit("штука") == "pcs"

    def test_normalize_unit_unknown(self):
        """Тест неизвестной единицы"""
        result = normalize_unit("unknown_unit")
        assert result == "unknown_unit"


class TestCheckUnitCompatibility:
    """Тесты для функции check_unit_compatibility"""

    def test_unit_compatibility_same(self):
        """Тест одинаковых единиц"""
        assert check_unit_compatibility("kg", "kg") is True

    def test_unit_compatibility_variants(self):
        """Тест совместимых вариантов"""
        assert check_unit_compatibility("kg", "kilogram") is True
        assert check_unit_compatibility("pcs", "piece") is True

    def test_unit_compatibility_different(self):
        """Тест несовместимых единиц"""
        assert check_unit_compatibility("kg", "pcs") is False

    def test_unit_compatibility_unknown(self):
        """Тест неизвестных единиц"""
        assert check_unit_compatibility("unknown1", "unknown2") is False


class TestCalculateSimilarity:
    """Тесты для функции calculate_similarity (обратная совместимость)"""

    def test_calculate_similarity_empty_strings(self):
        """Тест с пустыми строками"""
        result = calculate_similarity("", "")
        assert result == 1.0

    def test_calculate_similarity_one_empty(self):
        """Тест с одной пустой строкой"""
        result = calculate_similarity("test", "")
        assert result == 0.0

    def test_calculate_similarity_identical(self):
        """Тест идентичных строк"""
        result = calculate_similarity("apple", "apple")
        assert result == 1.0

    def test_calculate_similarity_similar(self):
        """Тест похожих строк"""
        result = calculate_similarity("apple", "aple")
        assert result > 0.8


class TestConstants:
    """Тесты констант модуля"""

    def test_product_variants_structure(self):
        """Тест структуры словаря вариантов продуктов"""
        assert isinstance(PRODUCT_VARIANTS, dict)
        assert "chickpeas" in PRODUCT_VARIANTS
        assert isinstance(PRODUCT_VARIANTS["chickpeas"], list)

    def test_unit_pattern(self):
        """Тест регулярного выражения для единиц"""
        match = UNIT_PATTERN.search("5 kg apples")
        assert match is not None
        assert match.group(1) == "5"
        assert match.group(2) == "kg"


class TestEdgeCases:
    """Тесты граничных случаев"""

    def test_very_long_strings(self):
        """Тест с очень длинными строками"""
        long_string = "a" * 1000
        result = normalize_product_name(long_string)
        assert len(result) <= 1000

    def test_unicode_strings(self):
        """Тест с Unicode строками"""
        result = normalize_product_name("яблоко")
        assert result == "яблоко"

    def test_special_characters(self):
        """Тест со специальными символами"""
        result = normalize_product_name("apple@#$%^&*()")
        assert "apple" in result

    def test_numbers_in_names(self):
        """Тест с числами в названиях"""
        result = normalize_product_name("apple123")
        assert result == "apple123"


if __name__ == "__main__":
    pytest.main([__file__])
