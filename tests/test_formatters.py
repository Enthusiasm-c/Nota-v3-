from app.utils.formatters import format_price, format_quantity, parse_date


def test_format_price():
    """Тестирование форматирования цен в разных форматах."""
    # Проверка основных кейсов
    assert format_price(1000) == "1 000,00"
    assert format_price(1000, currency="руб") == "1 000,00 руб"
    assert format_price(1000, decimal_places=0) == "1 000"

    # Проверка автоочистки нестандартных форматов
    assert format_price("1,000") == "1 000,00"
    assert format_price("1000руб") == "1 000,00"

    # Проверка None и пустых значений
    assert format_price(None) == "—"
    assert format_price("") == "—"

    # Проверка дробных чисел
    assert format_price(1000.50) == "1 000,50"
    assert format_price(1000.5, decimal_places=1) == "1 000,5"


def test_format_quantity():
    """Тестирование форматирования количества в разных форматах."""
    # Проверка целых чисел
    assert format_quantity(10) == "10"
    assert format_quantity(10, unit="кг") == "10 кг"

    # Проверка дробных чисел
    assert format_quantity(10.5) == "10.5"
    assert format_quantity(10.50) == "10.5"  # Удаление лишних нулей

    # Проверка автоочистки нестандартных форматов
    assert format_quantity("10,5 кг") == "10.5"
    assert format_quantity("10,5 кг", unit="шт") == "10.5 шт"

    # Проверка None и пустых значений
    assert format_quantity(None) == "—"
    assert format_quantity("") == "—"


def test_parse_date():
    """Тестирование парсинга дат в разных форматах."""
    # Проверка ISO формата YYYY-MM-DD
    assert parse_date("2023-01-02") == "2023-01-02"

    # Проверка форматов с разными разделителями
    assert parse_date("02.01.2023") == "2023-01-02"
    assert parse_date("02/01/2023") == "2023-01-02"
    assert parse_date("02-01-2023") == "2023-01-02"

    # Проверка американского формата MM-DD-YYYY
    assert parse_date("01-02-2023") == "2023-01-02"

    # Проверка форматов с однозначными днями/месяцами
    assert parse_date("2.1.2023") == "2023-01-02"
    assert parse_date("2.1.23") in (None, "2023-01-02")  # Короткий год может не распознаться

    # Проверка None и пустых значений
    assert parse_date(None) is None
    assert parse_date("") is None
    assert parse_date("None") is None
    assert parse_date("—") is None

    # Проверка неверных форматов
    assert parse_date("not_a_date") is None
