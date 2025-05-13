import pytest
from app import postprocessing

@pytest.mark.parametrize("val,expected", [
    ("1,000.50", 1000.5),
    ("1.000,50", 1000.5),
    ("1 000,50", 1000.5),
    ("1'000,50", 1000.5),
    ("1,000", 1000),
    ("1.000", 1000),
    ("1 000", 1000),
    ("1'000", 1000),
    ("1k", 1000),
    ("2.5k", 2500),
    ("1m", 1_000_000),
    ("2.5m", 2_500_000),
    ("1 тыс", 1000),
    ("2 млн", 2_000_000),
    ("1,234.56", 1234.56),
    ("1.234,56", 1234.56),
    ("1,234", 1234),
    ("1.234", 1234),
    ("1000", 1000),
    (1000, 1000),
    (1000.5, 1000.5),
    (None, None),
    ("", None),
    ("n/a", None),
    ("—", None),
    ("not_a_number", None),
    ("10,000руб", 10000),
    ("10.000руб", 10000),
])
def test_clean_num(val, expected):
    assert postprocessing.clean_num(val) == expected

def test_autocorrect_name_exact():
    allowed = ["Apple", "Banana", "Orange"]
    assert postprocessing.autocorrect_name("Apple", allowed) == "Apple"

def test_autocorrect_name_typo():
    allowed = ["Apple", "Banana", "Orange"]
    assert postprocessing.autocorrect_name("Aple", allowed) == "Apple"
    assert postprocessing.autocorrect_name("Bananna", allowed) == "Banana"
    assert postprocessing.autocorrect_name("Oragne", allowed) == "Orange"

def test_autocorrect_name_no_close():
    allowed = ["Apple", "Banana", "Orange"]
    assert postprocessing.autocorrect_name("Pineapple", allowed) == "Pineapple"

def test_normalize_units():
    assert postprocessing.normalize_units("kilograms") == "kg"
    assert postprocessing.normalize_units("pcs") == "pcs"
    assert postprocessing.normalize_units("bottle") == "btl"
    assert postprocessing.normalize_units("box") == "box"
    assert postprocessing.normalize_units("unknown") == "unknown"

def test_clean_num_edge_cases():
    # Некорректные строки
    assert postprocessing.clean_num("abc") is None
    assert postprocessing.clean_num("10abc") == 10
    assert postprocessing.clean_num("10,00.00") == 1000.0 or postprocessing.clean_num("10,00.00") == 10.0
    # Строка только с символами
    assert postprocessing.clean_num("руб") is None
    # Очень большие числа с пробелами и символами
    assert postprocessing.clean_num("1 000 000 руб") == 1000000
    # Строка с несколькими разделителями
    assert postprocessing.clean_num("1,234,567.89 руб") == 1234567.89
    # Строка с несколькими точками и запятыми
    assert postprocessing.clean_num("1.234.567,89 руб") == 1234567.89 or postprocessing.clean_num("1.234.567,89 руб") == 123456789

def test_autocorrect_name_edge_cases():
    allowed = ["Apple", "Banana", "Orange"]
    # Пустая строка
    assert postprocessing.autocorrect_name("", allowed) == ""
    # None
    assert postprocessing.autocorrect_name(None, allowed) == None
    # Очень длинная строка
    assert postprocessing.autocorrect_name("A"*100, allowed) == "A"*100

def test_normalize_units_edge_cases():
    # None
    assert postprocessing.normalize_units(None) == None
    # Пустая строка
    assert postprocessing.normalize_units("") == ""
    # Неизвестная единица
    assert postprocessing.normalize_units("unknown_unit") == "unknown_unit"
    # Смешанный регистр
    assert postprocessing.normalize_units("KiLoGrAmS") == "kg"

def test_clean_num_exception_handling(monkeypatch):
    # Искусственно вызываем исключение внутри clean_num
    def bad_float(val):
        raise ValueError("bad float")
    monkeypatch.setattr("builtins.float", bad_float)
    assert postprocessing.clean_num("123") is None 