import pytest
from app.matcher import fuzzy_best, match_positions

def test_fuzzy_best():
    catalog = {"eggplant": "1", "egg": "2", "milk": "3"}
    best, score = fuzzy_best("egg", catalog)
    assert best == "egg"
    assert score == 100
    best, score = fuzzy_best("egplant", catalog)
    assert best == "eggplant"
    assert score >= 75  # Levenshtein similarity for a close typo

def test_fuzzy_similar_length_products():
    products = [
        {"id": "1", "name": "egg"},
        {"id": "2", "name": "eggplant"},
        {"id": "3", "name": "eggs"},
    ]
    positions = [
        {"name": "eggs", "qty": 1, "unit": "pcs"},
        {"name": "egg", "qty": 2, "unit": "pcs"},
        {"name": "eggpant", "qty": 1, "unit": "pcs"},
    ]
    results = match_positions(positions, products, threshold=0.90)
    names = [r["name"] for r in results]
    assert set(names) == {"egg", "eggplant", "eggs"}
    assert len(set(names)) == len(names)  # уникальность

def test_fuzzy_substring_products():
    products = [
        {"id": "1", "name": "milk"},
        {"id": "2", "name": "soymilk"},
        {"id": "3", "name": "almond milk"},
    ]
    positions = [
        {"name": "soymilk", "qty": 1, "unit": "l"},
        {"name": "almondmilk", "qty": 1, "unit": "l"},
        {"name": "milk", "qty": 1, "unit": "l"},
    ]
    results = match_positions(positions, products, threshold=0.90)
    names = [r["name"] for r in results]
    assert set(names) == {"milk", "soymilk", "almond milk"}
    assert len(set(names)) == len(names)

def test_fuzzy_multiple_typos_unique_assignment():
    products = [
        {"id": "1", "name": "apple"},
        {"id": "2", "name": "apricot"},
        {"id": "3", "name": "pineapple"},
    ]
    positions = [
        {"name": "aple", "qty": 1, "unit": "pcs"},  # apple (typo)
        {"name": "apricott", "qty": 1, "unit": "pcs"},  # apricot (typo)
        {"name": "pineapl", "qty": 1, "unit": "pcs"},  # pineapple (typo)
    ]
    results = match_positions(positions, products, threshold=0.85)
    names = [r["name"] for r in results]
    assert set(names) == {"apple", "apricot", "pineapple"}
    assert len(set(names)) == len(names)

def test_fuzzy_no_match_below_threshold():
    products = [
        {"id": "1", "name": "banana"},
        {"id": "2", "name": "orange"},
    ]
    positions = [
        {"name": "xyz", "qty": 1, "unit": "pcs"},
    ]
    results = match_positions(positions, products, threshold=0.95)
    assert results[0]["status"] == "unknown"

def test_fuzzy_rescue_in_match_positions():
    # Simulate a product catalog
    products = [
        {"id": "1", "name": "eggplant"},
        {"id": "2", "name": "egg"},
        {"id": "3", "name": "milk"},
    ]
    # Simulate OCR positions with typo
    positions = [
        {"name": "egplant", "qty": 1, "unit": "pcs"},
        {"name": "egg", "qty": 2, "unit": "pcs"},
        {"name": "milk", "qty": 1, "unit": "l"},
        {"name": "eg", "qty": 1, "unit": "pcs"},
    ]
    # Lower threshold to force rescue
    results = match_positions(positions, products, threshold=0.95)
    names = [r["name"] for r in results]
    statuses = [r["status"] for r in results]
    assert "eggplant" in names
    assert "egg" in names
    assert "milk" in names
    assert any(s == "ok" for s in statuses)
