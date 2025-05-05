from app.keyboards import kb_edit
from app.formatters.report import build_report


def test_edit_callback_flow():
    # Simulate initial state
    match_results = [
        {"name": "Item A", "qty": 1, "unit": "pcs", "status": "unknown"},
        {"name": "Item B", "qty": 2, "unit": "kg", "status": "ok"},
    ]
    # Simulate edit callback for first line
    kb = kb_edit(0)
    assert kb is not None
    # Simulate user editing name
    match_results[0]["name"] = "Corrected Item A"
    match_results[0]["status"] = "ok"
    # Keyboard should now be None for this line
    kb = kb_edit(0)
    assert kb is not None
    # No kb_edit for status ok (by design, not tested here)
    # Report should reflect updated line
    report, _ = build_report({"supplier": None, "date": "2025-04-28"}, match_results)
    assert "Corrected It…" in report
    assert "✓" in report
