from app.formatters.report import build_report


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
    # Проверяем шапку (левое выравнивание, PRICE вместо TOTAL)
    assert "#  NAME" in report
    assert "QTY" in report and "UNIT" in report and "PRICE" in report
    # Supplier и дата
    assert "Supplier:" in report
    assert "UD. WIDI WIGUNA" in report
    assert "Invoice date:" in report
    assert "2025-04-29" in report

    # Divider и <pre>
    def pad(text, width):
        return str(text)[:width].ljust(width)

    header = f"#  {pad('NAME',14)}{pad('QTY',5)}{pad('UNIT',5)}{pad('PRICE',6)}! "
    assert header in report
    assert "<pre>" in report
    # Проверяем, что имя товара обрезано по ширине столбца
    assert "olive oil or…" in report
    assert "verylongprod…" in report
    # Проверяем, что для ошибочных позиций есть ❗
    assert report.count("❗") >= 2  # две ошибочные строки
    # Проверяем, что для корректной позиции (verylongproductnamethatiswaytoolong) нет ❗ в её строке
    for line in report.splitlines():
        if "verylongproductnamethatiswaytoolong" in line and "|" in line:
            assert "❗" not in line
    # Проверяем summary
    assert "❗" in report or "<b>Нет ошибок. Все позиции распознаны корректно.</b>" in report
    # Удалили символ 🚫 из отчёта
    # Проверяем корректные данные
    assert "lumajang" in report
    # Проверяем summary
    assert "Correct:" in report
    assert "Issues:" in report
    # Проверяем, что итоговая сумма не выводится (есть нераспознанные цены)
    assert "Invoice total" not in report
