from app.matcher import match_positions

def test_fuzzy_canonicalization():
    positions = [
        {"name": "romane", "qty": 1, "unit": "kg"},
        {"name": "romaine", "qty": 1, "unit": "kg"},
        {"name": "romaine lettuce", "qty": 1, "unit": "kg"}
    ]
    products = [
        {"alias": "romaine lettuce", "name": "romaine lettuce", "id": 1},
        {"alias": "iceberg", "name": "iceberg", "id": 2}
    ]
    # Порог 0.98, romane и romaine должны стать canonical
    results = match_positions(positions, products, threshold=0.9)
    assert results[0]["name"] == "romane"  # не canonical, порог не пройден
    assert results[0]["status"] == "unknown"
    assert results[1]["name"] == "romaine"
    assert results[1]["status"] == "unknown"
    # Третья — точное совпадение
    assert results[2]["name"] == "romaine lettuce"
    assert results[2]["status"] == "ok"
