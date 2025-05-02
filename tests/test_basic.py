from app.data_loader import load_products, load_suppliers
from app.ocr import ParsedData
from app.matcher import match_positions
from datetime import date

def test_csv_loaded():
    assert load_products()  # list non-empty
    assert load_suppliers()

def test_matcher_stub():
    parsed = ParsedData(
        supplier="Any Supplier",
        date=date.today(),
        positions=[{"name": "Tuna loin", "qty": 1, "unit": "kg"}],
    )
    results = match_positions(parsed.positions, load_products())
    assert len(results) == 1
    assert results[0]["status"] in {"ok", "unknown"}
