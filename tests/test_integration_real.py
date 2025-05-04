from app import data_loader, matcher, formatter
from app.models import ParsedData, Position
from datetime import date


def test_full_flow_with_real_data():
    products = data_loader.load_products("data/base_products.csv")
    parsed = ParsedData(
        supplier="Test Supplier",
        date=date.today(),
        positions=[
            Position(name="Тунец", qty=2, unit="kg"),
            Position(name="Лосось", qty=1, unit="kg"),
        ],
    )
    # Проверка: строка-дату принимает без ошибки
    parsed2 = ParsedData(
        supplier="Test Supplier",
        date="2025-04-28",
        positions=[
            Position(name="Тунец", qty=2, unit="kg"),
        ],
    )
    assert parsed2.date == date(2025, 4, 28)
    match_results = matcher.match_positions(parsed.positions, products)
    report = formatter.build_report(parsed, match_results)
    assert isinstance(report, str)
    assert "Test Supplier" in report
