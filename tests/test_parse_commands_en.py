import pytest

from app.parsers.command_parser import parse_compound_command


@pytest.mark.parametrize(
    "user_input,expected",
    [
        # Supplier modification
        (
            "supplier Acme Corp",
            [
                {
                    "action": "unknown",
                    "error": "unknown_command",
                    "original_text": "supplier Acme Corp",
                    "source": "integrated_parser",
                }
            ],
        ),  # Free parser handles supplier
        (
            "change supplier to Smith LLC",
            [
                {
                    "action": "unknown",
                    "error": "unknown_command",
                    "original_text": "change supplier to Smith LLC",
                    "source": "integrated_parser",
                }
            ],
        ),  # Free parser handles supplier
        # Total amount adjustment
        (
            "total 12345",
            [
                {
                    "action": "unknown",
                    "error": "unknown_command",
                    "original_text": "total 12345",
                    "source": "integrated_parser",
                }
            ],
        ),  # Free parser handles total
        (
            "total amount 9999.50",
            [
                {
                    "action": "unknown",
                    "error": "unknown_command",
                    "original_text": "total amount 9999.50",
                    "source": "integrated_parser",
                }
            ],
        ),  # Free parser handles total
        (
            "итого 7777.77",
            [
                {
                    "action": "unknown",
                    "error": "unknown_command",
                    "original_text": "итого 7777.77",
                    "source": "integrated_parser",
                }
            ],
        ),  # mixed input, Free parser handles total
        # Line item name editing
        (
            "row 2 name Milk",
            [{"action": "edit_name", "line": 1, "value": "Milk", "source": "local_parser"}],
        ),
        (
            "change name in row 3 to Bread",
            [{"action": "edit_name", "line": 2, "value": "Bread", "source": "local_parser"}],
        ),
        # Line item quantity editing
        (
            "row 1 qty 5",
            [{"action": "edit_quantity", "line": 0, "value": 5.0, "source": "local_parser"}],
        ),
        (
            "change qty in row 2 to 2.5",
            [{"action": "edit_quantity", "line": 1, "value": 2.5, "source": "local_parser"}],
        ),
        (
            "row 1 qty 1.5",
            [{"action": "edit_quantity", "line": 0, "value": 1.5, "source": "local_parser"}],
        ),
        (
            "row 1 qty 2,75",
            [{"action": "edit_quantity", "line": 0, "value": 2.75, "source": "local_parser"}],
        ),
    ],
)
def test_parse_commands_en(user_input, expected):
    result = parse_compound_command(user_input)
    assert len(result) == len(expected)
    for res, exp in zip(result, expected):
        res.pop("user_message", None)
        exp.pop("user_message", None)
        assert res == exp
