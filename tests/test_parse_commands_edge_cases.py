import pytest
from app.assistants.client import parse_edit_command

@pytest.mark.parametrize("user_input,invoice_lines,expected", [
    # Пустой ввод
    ("", None, []),
    ("   ", None, []),
    # Некорректные индексы строк
    ("строка -1 количество 5", 3, [{"action": "unknown", "error": "line_out_of_range", "line": 0}]),
    ("row 0 qty 3", 2, [{"action": "unknown", "error": "line_out_of_range", "line": 0}]),
    ("строка 10 количество 1", 2, [{"action": "unknown", "error": "line_out_of_range", "line": 9}]),
    ("row 5 qty 2", 3, [{"action": "unknown", "error": "line_out_of_range", "line": 4}]),
    # Неправильный формат чисел
    ("строка 1 количество пять", None, [{"action": "unknown", "error": "invalid_line_or_qty"}]),
    ("row 1 qty five", None, [{"action": "unknown", "error": "invalid_line_or_qty"}]),
    ("общая сумма 12,34,56", None, [{"action": "unknown", "error": "invalid_total_value"}]),
    # Неоднозначные команды или команды с опечатками
    ("поставщиик ООО Ромашка", None, []),  # опечатка
    ("totall 1234", None, []),  # опечатка
    ("change name in row two to Bread", None, []),  # нераспознанный индекс
    # Многострочные команды
    ("поставщик ООО Ромашка\nстрока 1 количество 2", None, [
        {"action": "set_supplier", "supplier": "ООО Ромашка"},
        {"action": "set_qty", "line": 0, "qty": 2.0}
    ]),
    ("supplier Acme Corp; row 2 name Milk", None, [
        {"action": "set_supplier", "supplier": "Acme Corp"},
        {"action": "set_name", "line": 1, "name": "Milk"}
    ]),
])
def test_parse_commands_edge_cases(user_input, invoice_lines, expected):
    result = parse_edit_command(user_input, invoice_lines) if invoice_lines is not None else parse_edit_command(user_input)
    assert len(result) == len(expected)
    for res, exp in zip(result, expected):
        for key, val in exp.items():
            assert res.get(key) == val
