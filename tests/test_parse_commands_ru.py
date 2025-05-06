import pytest
from app.assistants.client import parse_edit_command  # или ваш актуальный парсер

@pytest.mark.parametrize("user_input,expected", [
    # Редактирование поставщика
    ("поставщик ООО Ромашка", [{"action": "set_supplier", "supplier": "ООО Ромашка"}]),
    ("изменить поставщика на ИП Иванов", [{"action": "set_supplier", "supplier": "ИП Иванов"}]),
    # Изменение суммы
    ("общая сумма 12345", [{"action": "set_total", "total": 12345.0}]),
    ("итого 9999,50", [{"action": "set_total", "total": 9999.50}]),
    ("total 111.11", [{"action": "set_total", "total": 111.11}]),
    # Редактирование наименования и количества в строке
    ("строка 2 название Сметана", [{"action": "set_name", "line": 1, "name": "Сметана"}]),
    ("строка 1 количество 5", [{"action": "set_qty", "line": 0, "qty": 5.0}]),
    ("изменить количество в строке 3 на 2,5", [{"action": "set_qty", "line": 2, "qty": 2.5}]),
    # Обработка дробных чисел и разных форматов
    ("строка 1 количество 1,5", [{"action": "set_qty", "line": 0, "qty": 1.5}]),
    ("строка 1 количество 2.75", [{"action": "set_qty", "line": 0, "qty": 2.75}]),
])
def test_parse_commands_ru(user_input, expected):
    result = parse_edit_command(user_input)
    # Сравниваем только ключи, которые ожидаем (чтобы не падать на лишних)
    for res, exp in zip(result, expected):
        for key, val in exp.items():
            assert res[key] == val
