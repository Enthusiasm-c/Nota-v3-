import pytest
from app.assistants.client import parse_edit_command

@pytest.mark.parametrize("user_input,expected", [
    # Supplier modification
    ("supplier Acme Corp", [{"action": "set_supplier", "supplier": "Acme Corp"}]),
    ("change supplier to Smith LLC", [{"action": "set_supplier", "supplier": "Smith LLC"}]),
    # Total amount adjustment
    ("total 12345", [{"action": "set_total", "total": 12345.0}]),
    ("total amount 9999.50", [{"action": "set_total", "total": 9999.50}]),
    ("итого 7777.77", [{"action": "set_total", "total": 7777.77}]),  # mixed input
    # Line item name editing
    ("row 2 name Milk", [{"action": "set_name", "line": 1, "name": "Milk"}]),
    ("change name in row 3 to Bread", [{"action": "set_name", "line": 2, "name": "Bread"}]),
    # Line item quantity editing
    ("row 1 qty 5", [{"action": "set_qty", "line": 0, "qty": 5.0}]),
    ("change qty in row 2 to 2.5", [{"action": "set_qty", "line": 1, "qty": 2.5}]),
    ("row 1 qty 1.5", [{"action": "set_qty", "line": 0, "qty": 1.5}]),
    ("row 1 qty 2,75", [{"action": "set_qty", "line": 0, "qty": 2.75}]),
])
def test_parse_commands_en(user_input, expected):
    result = parse_edit_command(user_input)
    for res, exp in zip(result, expected):
        for key, val in exp.items():
            assert res[key] == val
