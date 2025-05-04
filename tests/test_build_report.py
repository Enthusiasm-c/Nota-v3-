import pytest
from app.formatters.report import build_report
from types import SimpleNamespace


def test_build_report_with_escape():
    """Проверяет работу build_report с параметром escape=True."""
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

    # Вызываем функцию с escape=True
    report, _ = build_report(parsed, match_results, escape=True)

    # Проверяем экранирование специальных символов
    assert r"Test \#Supplier" in report
    assert "Product \#1" in report

    # Проверяем наличие статусов
    assert "✅ ok" in report
    assert "❓ not found" in report

    # Проверяем числа в отчете
    assert "5" in report
    assert "kg" in report
    assert "100" in report

    # Проверяем блок кода для таблицы
    assert "```" in report


def test_build_report_without_escape():
    """Проверяет работу build_report с параметром escape=False."""
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

    # Вызываем функцию с escape=False
    report, _ = build_report(parsed, match_results, escape=False)

    # Проверяем отсутствие экранирования специальных символов
    assert "Test #Supplier" in report
    assert "Product #1" in report

    # Проверяем наличие статусов
    assert "✅ ok" in report
    assert "❓ not found" in report

    # Проверяем числа в отчете
    assert "5" in report
    assert "kg" in report
    assert "100" in report

    # Проверяем блок кода для таблицы
    assert "```" in report


def test_build_report_edge_cases():
    """Проверяет работу build_report с граничными случаями."""
    # Пустые данные
    parsed = SimpleNamespace(supplier=None, date=None)
    match_results = []

    # Вызываем функцию
    report, _ = build_report(parsed, match_results, escape=True)

    # Проверяем обработку None
    assert "Unknown supplier" in report
    assert "—" in report  # Placeholder для пустой даты

    # Нет позиций
    assert "```" in report

    # Проверяем отчет без OK позиций
    assert "✅" not in report.split("```")[-1]  # После блока кода не должно быть OK
