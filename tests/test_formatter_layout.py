from app.formatters.report import build_report
import re


def test_report_layout_strict():
    parsed_data = {"supplier": "UD. WIDI WIGUNA", "date": "2025-04-29"}
    match_results = [
        {
            "name": "olive oil orille 5liter",
            "qty": 2,
            "unit": "gh",
            "price": None,
            "status": "unknown",
        },
        {
            "name": "lumajang",
            "qty": 30,
            "unit": "kg",
            "price": None,
            "status": "unknown",
        },
        {
            "name": "verylongproductnamethatiswaytoolong",
            "qty": 1,
            "unit": "kg",
            "price": 1234.56,
            "status": "ok",
        },
    ]
    report, _ = build_report(parsed_data, match_results)
    # Проверяем шапку
    import re
    # Проверяем, что Supplier выводится в любом месте HTML
    assert "Supplier:" in report
    assert "UD. WIDI WIGUNA" in report
    assert "Invoice date:" in report
    assert "2025-04-29" in report
    # Проверяем divider (─)
    assert "─" in report
    # Проверяем <pre> для таблицы
    assert "<pre>" in report
    # Проверяем статусы
    assert "✓" in report
    assert "🚫" in report
    # Проверяем корректные данные
    assert "olive oil orille 5liter" in report
    assert "lumajang" in report
    assert "verylongproductnamethatiswaytoolong" in report
    # Проверяем summary
    assert "Correct:" in report
    assert "Issues:" in report
