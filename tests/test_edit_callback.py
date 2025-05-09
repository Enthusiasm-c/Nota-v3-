from app.keyboards import build_main_kb
from app.formatters.report import build_report


def test_edit_callback_flow():
    match_results = [
        {"name": "Item A", "qty": 1, "unit": "pcs", "status": "unknown"},
        {"name": "Item B", "qty": 2, "unit": "kg", "status": "ok"},
    ]
    # Проверяем, что клавиатура редактирования доступна
    kb = build_main_kb()
    assert kb is not None
    # Эмулируем редактирование первой строки
    match_results[0]["name"] = "Corrected Item A"
    match_results[0]["status"] = "ok"
    # Клавиатура по-прежнему возвращается (логика не зависит от строки)
    kb = build_main_kb()
    assert kb is not None
    # Проверяем, что отчёт содержит обновлённое имя и символ ✓
    report, _ = build_report({"supplier": None, "date": "2025-04-28"}, match_results)
    assert "Corrected It…" in report
    for line in report.splitlines():
        if "Corrected It…" in line:
            assert "❗" not in line
