import pytest
from app.parsers.command_parser import parse_compound_command

@pytest.mark.parametrize("user_input,expected", [
    # Редактирование поставщика
    ("поставщик ООО Ромашка", [{"action": "unknown", "error": "unknown_command", "original_text": "поставщик ООО Ромашка", "source": "integrated_parser"}]), # Free parser handles supplier
    ("изменить поставщика на ИП Иванов", [{"action": "unknown", "error": "unknown_command", "original_text": "изменить поставщика на ИП Иванов", "source": "integrated_parser"}]), # Free parser handles supplier
    # Изменение суммы
    ("общая сумма 12345", [{"action": "unknown", "error": "unknown_command", "original_text": "общая сумма 12345", "source": "integrated_parser"}]), # Free parser handles total
    ("итого 9999,50", [{"action": "unknown", "error": "unknown_command", "original_text": "итого 9999,50", "source": "integrated_parser"}]), # Free parser handles total
    ("total 111.11", [{"action": "unknown", "error": "unknown_command", "original_text": "total 111.11", "source": "integrated_parser"}]), # Free parser handles total
    # Редактирование наименования и количества в строке
    ("строка 2 название Сметана", [{"action": "edit_name", "line": 1, "value": "Сметана", "source": "local_parser"}]),
    ("строка 1 количество 5", [{"action": "edit_quantity", "line": 0, "value": 5.0, "source": "local_parser"}]),
    ("изменить количество в строке 3 на 2,5", [{"action": "edit_quantity", "line": 2, "value": 2.5, "source": "local_parser"}]),
    # Обработка дробных чисел и разных форматов
    ("строка 1 количество 1,5", [{"action": "edit_quantity", "line": 0, "value": 1.5, "source": "local_parser"}]),
    ("строка 1 количество 2.75", [{"action": "edit_quantity", "line": 0, "value": 2.75, "source": "local_parser"}]),
])
def test_parse_commands_ru(user_input, expected):
    result = parse_compound_command(user_input)
    assert len(result) == len(expected)
    for res, exp in zip(result, expected):
        res.pop("user_message", None)
        exp.pop("user_message", None)
        assert res == exp
