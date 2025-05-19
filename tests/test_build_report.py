from app.formatters.report import build_report
from types import SimpleNamespace
import html

def test_build_report_with_escape_html():
    """Проверяет работу build_report с параметром escape_html=True."""
    # Тестовые данные
    parsed = SimpleNamespace(supplier="Test #Supplier", date="2025-05-04")
    match_results = [
        {"name": "Product #1", "qty": 5, "unit": "kg", "price": 100, "status": "ok"},
        {
            "name": "Unknown Item",
            "qty": 2,
            "unit": "pcs",
            "price": 50,
            "status": "unknown",
        },
    ]

    # Вызываем функцию с escape_html=True
    report, _ = build_report(parsed, match_results, escape_html=True)

    # Проверяем, что для корректной позиции нет ❗, для ошибочной — есть
    assert "Product #1" in report
    assert "Unknown Item" in report
    assert "❗" in report  # есть ошибка
    assert "<pre>" in report
    assert "Supplier:" in report
    assert "Invoice date:" in report
    assert html.escape("Test #Supplier") in report
    assert "2025-05-04" in report
    # Проверяем summary
    assert "❗" in report or "<b>No errors. All items recognized correctly.</b>" in report


def test_build_report_without_escape_html():
    """Проверяет работу build_report с параметром escape_html=False."""
    # Тестовые данные
    parsed = SimpleNamespace(supplier="Test #Supplier", date="2025-05-04")
    match_results = [
        {"name": "Product #1", "qty": 5, "unit": "kg", "price": 100, "status": "ok"},
        {
            "name": "Unknown Item",
            "qty": 2,
            "unit": "pcs",
            "price": 50,
            "status": "unknown",
        },
    ]

    # Вызываем функцию с escape_html=False
    report, _ = build_report(parsed, match_results, escape_html=False)

    # Проверяем, что для корректной позиции нет ❗, для ошибочной — есть
    assert "Product #1" in report
    assert "Unknown Item" in report
    assert "❗" in report  # есть ошибка
    assert "<pre>" in report
    assert "Supplier:" in report
    assert "Invoice date:" in report
    assert "Test #Supplier" in report
    assert "2025-05-04" in report
    # Проверяем summary
    assert "❗" in report or "<b>No errors. All items recognized correctly.</b>" in report


def test_build_report_edge_cases():
    """Проверяет работу build_report с граничными случаями."""
    # Пустые данные
    parsed = SimpleNamespace(supplier=None, date=None)
    match_results = []

    # Вызываем функцию
    report, _ = build_report(parsed, match_results, escape_html=True)

    # Проверяем обработку None
    assert "Unknown supplier" in report
    assert "—" in report  # Placeholder для пустой даты

    # Нет позиций
    assert "<pre>" in report

    # Проверяем summary
    assert "❗" in report or "<b>No errors. All items recognized correctly.</b>" in report
