from app.formatter import build_report
import re

def test_report_layout_strict():
    parsed_data = {
        "supplier": "UD. WIDI WIGUNA",
        "date": "2025-04-29"
    }
    match_results = [
        {"name": "olive oil orille 5liter", "qty": 2, "unit": "gh", "price": None, "status": "unknown"},
        {"name": "lumajang", "qty": 30, "unit": "kg", "price": None, "status": "unknown"},
        {"name": "verylongproductnamethatiswaytoolong", "qty": 1, "unit": "kg", "price": 1234.56, "status": "ok"},
    ]
    report = build_report(parsed_data, match_results)
    # Проверяем шапку
    assert "*Supplier:* UD. WIDI WIGUNA" in report
    assert "*Invoice date:* 2025-04-29" in report
    # Проверяем разделитель (строка из 10+ символов '─')
    assert re.search(r"─{10,}", report)
    # Проверяем, что ровно две строки-делителя (любая длина, но только строки)
    divider_lines = [line for line in report.splitlines() if set(line) == {"─"}]
    assert len(divider_lines) == 2, f"divider_lines: {divider_lines}"
    # Проверяем code block для таблицы
    assert "#  NAME" in report
    # Проверяем обрезку длинного имени
    assert "verylongproductnametha…" in report
    # Проверяем PRICE = '—' если None
    assert "—" in report
    # Проверяем итоговую строку
    assert "ok" in report or "need check" in report
    # Проверяем, что нет тройных backticks
    assert "```" not in report
    # Проверяем, что все строки таблицы внутри code block (backtick)
    for line in report.splitlines():
        if line.strip().startswith("#  NAME") or "STATUS" in line:
            assert line.startswith("`") and line.endswith("`")
    # Проверяем, что итоговая строка вне code block
    summary_line = report.strip().split("\n")[-1]
    assert "ok" in summary_line or "need check" in summary_line
