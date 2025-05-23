from datetime import date

from app.formatters.report import build_report
from app.keyboards import build_main_kb
from app.models import ParsedData


def test_unknown_supplier_triggers_keyboard():
    parsed = ParsedData(
        supplier=None,
        date=date(2025, 4, 28),
        positions=[{"name": "Item A", "qty": 1, "unit": "pcs", "price": 10000}],
    )
    # Проверка: строка-дату принимает без ошибки
    parsed2 = ParsedData(
        supplier=None,
        date="2025-04-28",
        positions=[{"name": "Item A", "qty": 1, "unit": "pcs", "price": 10000}],
    )
    assert parsed2.date == date(2025, 4, 28)
    match_results = [{"name": "Item A", "qty": 1, "unit": "pcs", "status": "unknown"}]
    report, _ = build_report(parsed, match_results)
    assert "Unknown supplier" in report
    kb = build_main_kb()
    assert kb is not None
    assert any("edit:0" in btn.callback_data for row in kb.inline_keyboard for btn in row)
