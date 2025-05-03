from app.data_loader import load_products, load_suppliers
from app.ocr import ParsedData
from app.matcher import match_positions
from datetime import date

def test_csv_loaded():
    assert load_products("data/sample/base_products.csv")  # list non-empty
    assert load_suppliers("data/sample/base_suppliers.csv")


def test_matcher_stub():
    parsed = ParsedData(
        supplier="Any Supplier",
        date=None,
        positions=[{"name": "Tuna loin", "qty": 1, "unit": "kg"}],
    )
    # Convert Position objects to dicts for matcher
    positions = [p.model_dump() if hasattr(p, 'model_dump') else p for p in parsed.positions]
    results = match_positions(positions, load_products("data/sample/base_products.csv"))
    assert len(results) == 1
    assert results[0]["status"] in {"ok", "unknown"}
