from app.keyboards import build_position_kb
from app.formatter import build_report

def test_edit_callback_flow():
    # Simulate initial state
    match_results = [
        {"name": "Item A", "qty": 1, "unit": "pcs", "status": "unknown"},
        {"name": "Item B", "qty": 2, "unit": "kg", "status": "ok"},
    ]
    # Simulate edit callback for first line
    kb = build_position_kb(0, match_results[0]["status"])
    assert kb is not None
    # Simulate user editing name
    match_results[0]["name"] = "Corrected Item A"
    match_results[0]["status"] = "ok"
    # Keyboard should now be None for this line
    kb2 = build_position_kb(0, match_results[0]["status"])
    assert kb2 is None
    # Report should reflect updated line
    report = build_report({"supplier": None, "date": "2025-04-28"}, match_results)
    assert "Corrected Item A" in report
    assert "ok" in report
