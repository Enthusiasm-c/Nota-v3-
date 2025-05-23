from app.matcher import (
    calculate_string_similarity,
    fuzzy_best,
    fuzzy_find,
    match_positions,
    match_supplier,
    normalize_product_name,
)


def test_normalize_product_name():
    # Тестирование базовой функциональности нормализации названий
    assert normalize_product_name("apples") == "apples"  # Сохраняем форму слова
    assert normalize_product_name("tomatoes") == "tomatoes"  # Сохраняем форму слова
    assert normalize_product_name("cherries") == "cherries"  # Сохраняем форму слова
    assert normalize_product_name("romaine lettuce") == "romaine"  # Обработка синонимов
    assert normalize_product_name("eggplant") == "eggplant"  # Без изменений
    assert normalize_product_name("aubergine") == "eggplant"  # Синоним
    assert normalize_product_name("  TOMATOES  ") == "tomatoes"  # Обработка пробелов и регистра
    assert normalize_product_name("fresh tomatoes") == "tomatoes"  # Удаление филлеров
    assert normalize_product_name("organic apples") == "apples"  # Удаление филлеров
    assert normalize_product_name("premium bananas") == "bananas"  # Удаление филлеров


def test_normalize_product_name_edge_cases():
    # Тестирование граничных случаев
    assert normalize_product_name("") == ""  # Пустая строка
    assert normalize_product_name(None) == ""  # None
    assert normalize_product_name("dragonfruit") == "dragonfruit"  # Неизвестное слово
    assert normalize_product_name("exotic_fruit") == "exotic_fruit"  # Слово с подчеркиванием
    assert normalize_product_name("TOMATOES") == "tomatoes"  # Только верхний регистр
    assert normalize_product_name("tomatoes 1kg") == "tomatoes"  # Удаление единиц измерения
    assert (
        normalize_product_name("apples 2.5 kg") == "apples"
    )  # Удаление единиц измерения с дробным числом
    assert (
        normalize_product_name("fresh organic premium tomatoes") == "tomatoes"
    )  # Множество филлеров


def test_calculate_string_similarity_basic():
    # Тестирование базовой функциональности сравнения строк
    assert calculate_string_similarity("apple", "apple") == 1.0  # Идентичные строки
    assert 0.7 < calculate_string_similarity("apple", "aple") < 1.0  # Опечатка
    assert calculate_string_similarity("apple", "banana") < 0.5  # Разные слова
    assert calculate_string_similarity("tomato", "tomatoes") >= 0.9  # Множественное число
    assert calculate_string_similarity("cherry", "cherries") >= 0.9  # Множественное число с -ies


def test_calculate_string_similarity_normalization():
    # Тестирование нормализации при сравнении
    assert calculate_string_similarity("apple", "Apple") == 1.0  # Регистр
    assert calculate_string_similarity("  apple  ", "apple") == 1.0  # Пробелы
    assert calculate_string_similarity("apples", "apple") >= 0.9  # Множественное число
    assert calculate_string_similarity("fresh apple", "apple") >= 0.9  # Филлеры
    assert (
        calculate_string_similarity("organic apples", "apple") >= 0.9
    )  # Филлеры + множественное число
    assert calculate_string_similarity("apple 1kg", "apple") >= 0.9  # Единицы измерения


def test_calculate_string_similarity_edge_cases():
    # Тестирование граничных случаев
    assert calculate_string_similarity("", "") == 0.0  # Пустые строки
    assert calculate_string_similarity("", "apple") == 0.0  # Одна пустая строка
    assert calculate_string_similarity("apple", "") == 0.0  # Другая пустая строка
    assert calculate_string_similarity(None, None) == 0.0  # None значения
    assert calculate_string_similarity(None, "apple") == 0.0  # Один None
    assert calculate_string_similarity("apple", None) == 0.0  # Другой None


def test_calculate_string_similarity_product_variants():
    # Тестирование особых случаев с синонимами продуктов
    assert calculate_string_similarity("roma", "romaine") >= 0.8  # Частичное совпадение
    assert (
        calculate_string_similarity("romaine lettuce", "romaine") >= 0.9
    )  # Синоним с дополнительным словом
    assert calculate_string_similarity("tomato", "tomatoes") >= 0.9  # Множественное число
    assert calculate_string_similarity("eggplant", "aubergine") >= 0.9  # Полные синонимы
    assert calculate_string_similarity("chili", "chilli") >= 0.9  # Вариации написания
    assert (
        calculate_string_similarity("fresh organic tomatoes", "tomato") >= 0.9
    )  # Филлеры и множественное число
    assert calculate_string_similarity("premium eggplant", "aubergine") >= 0.9  # Филлеры и синонимы


def test_fuzzy_find_basic():
    # Тестирование базовой функциональности fuzzy_find
    products = [
        {"id": "1", "name": "apple"},
        {"id": "2", "name": "banana"},
        {"id": "3", "name": "orange"},
    ]

    # Точное совпадение
    res = fuzzy_find("apple", products)
    assert len(res) == 1
    assert res[0]["name"] == "apple"
    assert res[0]["original"]["id"] == "1"
    assert res[0]["score"] == 1.0

    # Частичное совпадение
    res = fuzzy_find("banan", products)
    assert len(res) == 1
    assert res[0]["name"] == "banana"
    assert res[0]["original"]["id"] == "2"
    assert res[0]["score"] > 0.8

    # Нет совпадения
    res = fuzzy_find("xyz", products)
    assert res == []


def test_fuzzy_find_threshold():
    # Тестирование работы порога сходства
    products = [
        {"id": "1", "name": "apple"},
        {"id": "2", "name": "apricot"},
        {"id": "3", "name": "avocado"},
    ]

    # С высоким порогом находим только точные совпадения
    res = fuzzy_find("app", products, threshold=0.9)
    assert len(res) == 0

    # С низким порогом находим частичные совпадения
    res = fuzzy_find("app", products, threshold=0.5)
    assert len(res) >= 1
    assert any(r["name"] == "apple" for r in res)


def test_fuzzy_find_edge_cases():
    # Тестирование граничных случаев
    products = [{"id": "1", "name": "apple"}, {"id": "2", "name": "banana"}]

    # Пустой запрос
    assert fuzzy_find("", products) == []

    # None запрос
    assert fuzzy_find(None, products) == []

    # Пустой список продуктов
    assert fuzzy_find("apple", []) == []

    # None список продуктов
    assert fuzzy_find("apple", None) == []


def test_fuzzy_find_object_products():
    # Тестирование работы с объектами вместо словарей
    class Product:
        def __init__(self, id, name):
            self.id = id
            self.name = name

    products = [Product("1", "apple"), Product("2", "banana")]

    # Должен работать с объектами
    res = fuzzy_find("apple", products)
    assert len(res) == 1
    assert res[0]["name"] == "apple"
    assert res[0]["original"].id == "1"


def test_fuzzy_best_basic():
    # Тестирование базовой функциональности fuzzy_best
    catalog = {"apple": "1", "banana": "2", "orange": "3"}

    # Точное совпадение
    best, score = fuzzy_best("apple", catalog)
    assert best["name"] == "apple"
    assert best["id"] == "1"
    assert score == 100

    # Близкое совпадение
    best, score = fuzzy_best("aple", catalog)
    assert best["name"] == "apple"
    assert score >= 80

    # Нет близкого совпадения
    best, score = fuzzy_best("xyz", catalog)
    assert best == ""
    assert score < 50


def test_fuzzy_best_edge_cases():
    # Тестирование граничных случаев
    catalog = {"apple": "1", "banana": "2"}

    # Пустой запрос
    best, score = fuzzy_best("", catalog)
    assert best == ""
    assert score == 0

    # Пустой каталог
    best, score = fuzzy_best("apple", {})
    assert best == ""
    assert score == 0


def test_match_supplier_basic():
    # Тестирование базовой функциональности match_supplier
    suppliers = [
        {"id": "1", "name": "Apple Inc", "code": "APPL"},
        {"id": "2", "name": "Banana Corp", "code": "BNNA"},
        {"id": "3", "name": "Orange Ltd", "code": "ORNG"},
    ]

    # Точное совпадение
    result = match_supplier("Apple Inc", suppliers)
    assert result["name"] == "Apple Inc"
    assert result["id"] == "1"
    assert result["code"] == "APPL"
    assert result["status"] == "ok"
    assert result["score"] == 1.0

    # Близкое совпадение
    result = match_supplier("Aple Inc", suppliers, threshold=0.8)
    assert result["name"] == "Apple Inc"
    assert result["id"] == "1"
    assert result["status"] == "ok"
    assert result["score"] >= 0.8

    # Нет совпадения
    result = match_supplier("XYZ Corp", suppliers)
    assert result["name"] == "XYZ Corp"
    assert result["id"] is None
    assert result["status"] == "unknown"


def test_match_supplier_edge_cases():
    # Тестирование граничных случаев
    suppliers = [{"id": "1", "name": "Apple Inc", "code": "APPL"}]

    # Пустой запрос
    result = match_supplier("", suppliers)
    assert result["name"] == ""
    assert result["id"] is None
    assert result["status"] == "unknown"

    # None запрос
    result = match_supplier(None, suppliers)
    assert result["name"] is None
    assert result["id"] is None
    assert result["status"] == "unknown"

    # Пустой список поставщиков
    result = match_supplier("Apple Inc", [])
    assert result["name"] == "Apple Inc"
    assert result["id"] is None
    assert result["status"] == "unknown"


def test_match_supplier_object_suppliers():
    # Тестирование работы с объектами вместо словарей
    class Supplier:
        def __init__(self, id, name, code):
            self.id = id
            self.name = name
            self.code = code

    suppliers = [Supplier("1", "Apple Inc", "APPL"), Supplier("2", "Banana Corp", "BNNA")]

    # Должен работать с объектами
    result = match_supplier("Apple Inc", suppliers)
    assert result["name"] == "Apple Inc"
    assert result["id"] == "1"
    assert result["code"] == "APPL"
    assert result["status"] == "ok"


def test_match_positions_basic():
    # Тестирование базовой функциональности match_positions
    products = [
        {"id": "1", "name": "Apple"},
        {"id": "2", "name": "Banana"},
        {"id": "3", "name": "Orange"},
    ]

    positions = [
        {"name": "Apple", "qty": 1, "unit": "kg"},
        {"name": "Banan", "qty": 2, "unit": "kg"},  # опечатка
        {"name": "Pineapple", "qty": 3, "unit": "kg"},  # нет в продуктах
    ]

    results = match_positions(positions, products, threshold=0.9)

    # Проверяем результаты
    assert len(results) == 3

    # Точное совпадение
    assert results[0]["name"] == "Apple"
    assert results[0]["status"] == "ok"
    assert results[0]["score"] >= 0.9

    # Близкое совпадение
    assert results[1]["name"] == "Banan"
    assert results[1]["status"] == "unknown"  # Теперь unknown из-за высокого порога
    assert results[1]["score"] < 0.9

    # Нет совпадения
    assert results[2]["name"] == "Pineapple"
    assert results[2]["status"] == "unknown"


def test_match_positions_with_suggestions():
    # Тестирование возврата предложений для неизвестных позиций
    products = [
        {"id": "1", "name": "Apple"},
        {"id": "2", "name": "Apricot"},
        {"id": "3", "name": "Avocado"},
        {"id": "4", "name": "Tomato"},
    ]

    positions = [
        {"name": "Appl", "qty": 1, "unit": "kg"},  # Близко к "Apple"
        {"name": "Tomatoe", "qty": 2, "unit": "kg"},  # Близко к "Tomato"
        {"name": "XYZ", "qty": 3, "unit": "kg"},  # Нет близких совпадений
    ]

    results = match_positions(positions, products, threshold=0.95, return_suggestions=True)

    # Проверяем результаты
    assert len(results) == 3

    # Проверяем первую позицию (Appl)
    assert results[0]["name"] == "Appl"
    assert results[0]["status"] == "unknown"
    assert "suggestions" in results[0]
    assert len(results[0]["suggestions"]) >= 1
    assert any(s["name"].lower() == "apple" for s in results[0]["suggestions"])

    # Проверяем вторую позицию (Tomatoe)
    assert results[1]["name"] == "Tomatoe"
    assert results[1]["status"] == "unknown"
    assert "suggestions" in results[1]
    assert len(results[1]["suggestions"]) >= 1
    assert any(s["name"].lower() == "tomato" for s in results[1]["suggestions"])

    # Проверяем третью позицию (XYZ)
    assert results[2]["name"] == "XYZ"
    assert results[2]["status"] == "unknown"
    assert "suggestions" not in results[2] or len(results[2]["suggestions"]) == 0


def test_match_positions_edge_cases():
    # Тестирование граничных случаев
    products = [{"id": "1", "name": "Apple"}]

    # Пустые позиции
    assert match_positions([], products) == []

    # Пустые продукты
    positions = [{"name": "Apple", "qty": 1}]
    results = match_positions(positions, [])
    assert len(results) == 1
    assert results[0]["status"] == "unknown"

    # None значения
    positions = [{"name": None, "qty": None}]
    results = match_positions(positions, products)
    assert len(results) == 1
    assert results[0]["status"] == "unknown"
    assert results[0]["score"] == 0.0

    # Пустые строки
    positions = [{"name": "", "qty": 1}]
    results = match_positions(positions, products)
    assert len(results) == 1
    assert results[0]["status"] == "unknown"
    assert results[0]["score"] == 0.0


def test_match_positions_object_inputs():
    # Тестирование работы с объектами вместо словарей
    class Product:
        def __init__(self, id, name):
            self.id = id
            self.name = name

    class Position:
        def __init__(self, name, qty, unit=None):
            self.name = name
            self.qty = qty
            self.unit = unit

    products = [Product("1", "Apple"), Product("2", "Banana")]

    positions = [Position("Apple", 1, "kg"), Position("Banan", 2, "kg")]

    # Должен работать с объектами
    results = match_positions(positions, products)
    assert len(results) == 2
    assert results[0]["name"] == "Apple"
    assert results[1]["name"] == "Banan"


def test_match_positions_price_calculations():
    # Тестирование вычисления цен и сумм
    positions = [
        {"name": "apple", "qty": 2, "price": 10},
        {"name": "banana", "qty": 3, "price": 5},
    ]

    products = [
        {"id": "1", "name": "apple", "price": 10},
        {"id": "2", "name": "banana", "price": 5},
    ]

    results = match_positions(positions, products)

    for result in results:
        assert result["status"] == "ok"
        assert "total" in result
        if result["name"] == "apple":
            assert result["total"] == 20  # 2 * 10
        elif result["name"] == "banana":
            assert result["total"] == 15  # 3 * 5


def test_match_positions_with_fillers():
    # Тестирование работы с филлерами и вариациями названий
    products = [
        {"id": "1", "name": "Apple"},
        {"id": "2", "name": "Tomato"},
        {"id": "3", "name": "Eggplant"},
    ]

    positions = [
        {"name": "Fresh Apples", "qty": 1},  # Филлер + множественное число
        {"name": "Organic Tomatoes", "qty": 2},  # Филлер + множественное число
        {"name": "Premium Aubergine", "qty": 3},  # Филлер + синоним
    ]

    results = match_positions(positions, products, threshold=0.8)

    # Проверяем результаты
    assert len(results) == 3

    # Fresh Apples -> Apple
    assert results[0]["status"] == "ok"
    assert results[0]["id"] == "1"
    assert results[0]["score"] >= 0.8

    # Organic Tomatoes -> Tomato
    assert results[1]["status"] == "ok"
    assert results[1]["id"] == "2"
    assert results[1]["score"] >= 0.8

    # Premium Aubergine -> Eggplant
    assert results[2]["status"] == "ok"
    assert results[2]["id"] == "3"
    assert results[2]["score"] >= 0.8


def test_levenshtein_ratio():
    # Тестирование функции levenshtein_ratio
    assert levenshtein_ratio("apple", "apple") == 1.0
    assert 0 < levenshtein_ratio("apple", "aple") < 1.0
    assert levenshtein_ratio("apple", "banana") < 0.5

    # Тестирование с процессором
    assert levenshtein_ratio("APPLE", "apple", processor=str.lower) == 1.0

    # Тестирование с порогом
    assert levenshtein_ratio("apple", "appl", score_cutoff=0.8) > 0
    assert levenshtein_ratio("apple", "banana", score_cutoff=0.8) == 0


def test_levenshtein_distance():
    # Тестирование функции levenshtein_distance
    assert levenshtein_distance("apple", "apple") == 0
    assert levenshtein_distance("apple", "aple") == 1
    assert levenshtein_distance("apple", "applee") == 1
    assert levenshtein_distance("apple", "banana") > 3

    # Тестирование с весами
    weights = (1, 1, 1)  # (insertion, deletion, substitution)
    assert levenshtein_distance("apple", "aple", weights=weights) == 1

    # Тестирование с процессором
    assert levenshtein_distance("APPLE", "apple", processor=str.lower) == 0

    # Тестирование с порогом
    assert levenshtein_distance("apple", "appl", score_cutoff=2) == 1
    assert levenshtein_distance("apple", "banana", score_cutoff=3) > 3
