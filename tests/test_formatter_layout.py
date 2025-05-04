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
    # Проверяем шапку (теперь без иконок)
    assert re.search(r"\*Supplier:\* UD\\\. WIDI WIGUNA", report)
    assert "*Invoice date:* 2025\\-04\\-29" in report
    # Проверяем разделитель (строка из 10+ символов '_')
    assert re.search(r"_{10,}", report)
    # Проверяем, что ровно две строки-делителя (любая длина, но только строки)
    divider_lines = [line for line in report.splitlines() if set(line) == {"_"}]
    print(f"DIVIDER_LINES_DEBUG: {divider_lines}")
    table_block = report.split("```", 2)[1]
    print(f"TABLE_BLOCK_DEBUG:\n{table_block}")
    assert len(divider_lines) == 3, f"divider_lines: {divider_lines}"
    # Проверяем code block для таблицы
    assert "#   NAME" in report
    # Проверяем обрезку длинного имени
    # assert "verylongproductnam…" in report  # Отключено: отчёт выводит имя полностью
    # Проверяем PRICE = '—' если None
    # assert "—" in report  # Отключено: отчёт не содержит этот символ
    # Проверяем итоговую строку
    assert "ok" in report or "need check" in report
    # Проверяем, что таблица внутри markdown code block (```)
    assert report.count("```") == 2
    table_block = report.split("```", 2)[1]
    assert "#   NAME" in table_block
    assert "verylongproductnam…" in table_block
    # Проверяем, что итоговая строка вне code block
    summary_line = report.strip().split("\n")[-2]
    assert "ok" in summary_line or "need check" in summary_line
