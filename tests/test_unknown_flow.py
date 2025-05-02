from app.models import ParsedData
from app.formatter import build_report
from app.keyboards import build_position_kb

from datetime import date

def test_unknown_supplier_triggers_keyboard():
    parsed = ParsedData(
        supplier=None,
        date=None,
        positions=[{"name": "Item A", "qty": 1, "unit": "pcs", "price": 10000}]
    )
    match_results = [
        {"name": "Item A", "qty": 1, "unit": "pcs", "status": "unknown"}
    ]
    report = build_report(parsed, match_results)
    assert "Unknown supplier" in report
    kb = build_position_kb(0, match_results[0]["status"])
    assert kb is not None
    assert any("edit:0" in btn.callback_data for row in kb.inline_keyboard for btn in row)
