import pytest

from app.parsers.command_parser import parse_compound_command


@pytest.mark.parametrize(
    "user_input,invoice_lines,expected",
    [
        # Пустой ввод
        ("", None, []),
        ("   ", None, []),
        # Некорректные индексы строк
        ("строка -1 количество 5", 3, [{"action": "unknown", "error": "invalid_line_number"}]),
        ("row 0 qty 3", 2, [{"action": "unknown", "error": "invalid_line_number"}]),
        (
            "строка 10 количество 1",
            2,
            [{"action": "unknown", "error": "line_out_of_range", "line": 9}],
        ),
        ("row 5 qty 2", 3, [{"action": "unknown", "error": "line_out_of_range", "line": 4}]),
        # Неправильный формат чисел
        ("строка 1 количество пять", None, [{"action": "unknown", "error": "invalid_qty_value"}]),
        ("row 1 qty five", None, [{"action": "unknown", "error": "invalid_qty_value"}]),
        (
            "общая сумма 12,34,56",
            None,
            [
                {
                    "action": "unknown",
                    "error": "unknown_command",
                    "original_text": "общая сумма 12,34,56",
                    "source": "integrated_parser",
                }
            ],
        ),  # free_parser might handle this
        # Неоднозначные команды или команды с опечатками
        (
            "поставщиик ООО Ромашка",
            None,
            [
                {
                    "action": "unknown",
                    "error": "unknown_command",
                    "original_text": "поставщиик ООО Ромашка",
                    "source": "integrated_parser",
                }
            ],
        ),
        (
            "totall 1234",
            None,
            [
                {
                    "action": "unknown",
                    "error": "unknown_command",
                    "original_text": "totall 1234",
                    "source": "integrated_parser",
                }
            ],
        ),
        (
            "change name in row two to Bread",
            None,
            [
                {
                    "action": "unknown",
                    "error": "unknown_command",
                    "original_text": "change name in row two to Bread",
                    "source": "integrated_parser",
                }
            ],
        ),
        # Многострочные команды
        (
            "поставщик ООО Ромашка\nстрока 1 количество 2",
            None,
            [
                {
                    "action": "unknown",
                    "error": "unknown_command",
                    "original_text": "поставщик ООО Ромашка",
                    "source": "integrated_parser",
                },  # Free parser handles supplier
                {"action": "edit_quantity", "line": 0, "value": 2.0, "source": "local_parser"},
            ],
        ),
        (
            "supplier Acme Corp; row 2 name Milk",
            None,
            [
                {
                    "action": "unknown",
                    "error": "unknown_command",
                    "original_text": "supplier Acme Corp",
                    "source": "integrated_parser",
                },  # Free parser handles supplier
                {"action": "edit_name", "line": 1, "value": "Milk", "source": "local_parser"},
            ],
        ),
        # Команды с запятыми
        (
            "строка 1 цена 100, строка 2 количество 5",
            None,
            [
                {"action": "edit_price", "line": 0, "value": 100.0, "source": "local_parser"},
                {"action": "edit_quantity", "line": 1, "value": 5.0, "source": "local_parser"},
            ],
        ),
        # Команды с точками
        (
            "строка 1 название Молоко. строка 1 цена 200. строка 1 количество 3",
            None,
            [
                {"action": "edit_name", "line": 0, "value": "Молоко", "source": "local_parser"},
                {"action": "edit_price", "line": 0, "value": 200.0, "source": "local_parser"},
                {"action": "edit_quantity", "line": 0, "value": 3.0, "source": "local_parser"},
            ],
        ),
        # Комбинированные разделители
        (
            "поставщик ООО Ромашка; строка 1 цена 100, строка 2 количество 5.",
            None,
            [
                {
                    "action": "unknown",
                    "error": "unknown_command",
                    "original_text": "поставщик ООО Ромашка",
                    "source": "integrated_parser",
                },  # Free parser handles supplier
                {"action": "edit_price", "line": 0, "value": 100.0, "source": "local_parser"},
                {"action": "edit_quantity", "line": 1, "value": 5.0, "source": "local_parser"},
            ],
        ),
        # Проверка, что точки внутри чисел не разделяют команды
        (
            "строка 1 цена 10.5, строка 2 количество 3.14",
            None,
            [
                {"action": "edit_price", "line": 0, "value": 10.5, "source": "local_parser"},
                {"action": "edit_quantity", "line": 1, "value": 3.14, "source": "local_parser"},
            ],
        ),
        # Формат с двоеточием и множественными параметрами
        (
            "line 3: name Cream Cheese; price 250; qty 15; unit krat",
            None,
            [
                {
                    "action": "edit_name",
                    "line": 2,
                    "value": "Cream Cheese",
                    "source": "local_parser",
                },
                {"action": "edit_price", "line": 2, "value": 250.0, "source": "local_parser"},
                {"action": "edit_quantity", "line": 2, "value": 15.0, "source": "local_parser"},
                {"action": "edit_unit", "line": 2, "value": "krat", "source": "local_parser"},
            ],
        ),
        # Формат с множественными параметрами в одной строке
        (
            "line 3 name Cheese price 250 qty 5 unit kg",
            None,
            [
                {"action": "edit_name", "line": 2, "value": "Cheese", "source": "local_parser"},
                {"action": "edit_price", "line": 2, "value": 250.0, "source": "local_parser"},
                {"action": "edit_quantity", "line": 2, "value": 5.0, "source": "local_parser"},
                {"action": "edit_unit", "line": 2, "value": "kg", "source": "local_parser"},
            ],
        ),
    ],
)
def test_parse_commands_edge_cases(user_input, invoice_lines, expected):
    result = (
        parse_compound_command(user_input, invoice_lines)
        if invoice_lines is not None
        else parse_compound_command(user_input)
    )
    assert len(result) == len(expected)
    for res, exp in zip(result, expected):
        # Clean up fields that might differ and are not essential for this test's purpose
        res.pop("user_message", None)
        exp.pop("user_message", None)
        assert res == exp
