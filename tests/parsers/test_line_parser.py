import pytest
from app.parsers.line_parser import (
    parse_line_command,
    _parse_price_command,
    _parse_name_command,
    _parse_qty_command,
    _parse_unit_command
)

# Test cases for _parse_price_command
@pytest.mark.parametrize(
    "text, line_limit, expected",
    [
        ("line 1 price 100.50", None, {"action": "edit_price", "line": 0, "value": 100.50, "source": "local_parser"}),
        ("строка 2 цена 200", 5, {"action": "edit_price", "line": 1, "value": 200.0, "source": "local_parser"}),
        ("line 3 price 300,75", None, {"action": "edit_price", "line": 2, "value": 300.75, "source": "local_parser"}),
        ("line 0 price 100", None, {"action": "unknown", "error": "invalid_line_number", "source": "text_processor"}),
        ("line 1 price abc", None, {"action": "unknown", "error": "invalid_price_value", "source": "text_processor"}),
        ("line 5 price 100", 3, {"action": "unknown", "error": "line_out_of_range", "line": 4, "source": "text_processor"}),
        ("line one price 100", None, None), # Invalid line number format
        ("price 100", None, None), # Missing line number
    ],
)
def test_parse_price_command(text, line_limit, expected):
    assert _parse_price_command(text, line_limit) == expected

# Test cases for _parse_name_command
@pytest.mark.parametrize(
    "text, line_limit, expected",
    [
        ("line 1 name Product A", None, {"action": "edit_name", "line": 0, "value": "Product A", "source": "local_parser"}),
        ("строка 2 название Товар Б", 5, {"action": "edit_name", "line": 1, "value": "Товар Б", "source": "local_parser"}),
        ("line 3 наименование Item C price 10", None, {"action": "edit_name", "line": 2, "value": "Item C", "source": "local_parser"}), # name followed by other field
        ("line 0 name Product D", None, {"action": "unknown", "error": "invalid_line_number", "source": "text_processor"}),
        ("line 1 name ", None, {"action": "unknown", "error": "empty_name_value", "source": "text_processor"}), # Empty name
        ("line 5 name Product E", 3, {"action": "unknown", "error": "line_out_of_range", "line": 4, "source": "text_processor"}),
        ("line one name Product F", None, None), # Invalid line number format
        ("name Product G", None, None), # Missing line number
        ("line 1 name Product H; qty 2", None, {"action": "edit_name", "line": 0, "value": "Product H", "source": "local_parser"}), # Semicolon separator
        ("line 2 название Товар И, цена 200", None, {"action": "edit_name", "line": 1, "value": "Товар И", "source": "local_parser"}) # Comma separator
    ],
)
def test_parse_name_command(text, line_limit, expected):
    assert _parse_name_command(text, line_limit) == expected

# Test cases for _parse_qty_command
@pytest.mark.parametrize(
    "text, line_limit, expected",
    [
        ("line 1 qty 10", None, {"action": "edit_quantity", "line": 0, "value": 10.0, "source": "local_parser"}),
        ("строка 2 количество 5.5", 5, {"action": "edit_quantity", "line": 1, "value": 5.5, "source": "local_parser"}),
        ("line 3 кол-во 7,25", None, {"action": "edit_quantity", "line": 2, "value": 7.25, "source": "local_parser"}),
        ("line 0 qty 10", None, {"action": "unknown", "error": "invalid_line_number", "source": "text_processor"}),
        ("line 1 qty abc", None, {"action": "unknown", "error": "invalid_qty_value", "source": "text_processor"}),
        ("line 5 qty 10", 3, {"action": "unknown", "error": "line_out_of_range", "line": 4, "source": "text_processor"}),
        ("line one qty 10", None, None), # Invalid line number format
        ("qty 10", None, None), # Missing line number
    ],
)
def test_parse_qty_command(text, line_limit, expected):
    assert _parse_qty_command(text, line_limit) == expected

# Test cases for _parse_unit_command
@pytest.mark.parametrize(
    "text, line_limit, expected",
    [
        ("line 1 unit pcs", None, {"action": "edit_unit", "line": 0, "value": "pcs", "source": "local_parser"}),
        ("строка 2 единица кг", 5, {"action": "edit_unit", "line": 1, "value": "кг", "source": "local_parser"}),
        ("line 3 ед. шт.", None, {"action": "edit_unit", "line": 2, "value": "шт", "source": "local_parser"}),
        ("line 0 unit pcs", None, {"action": "unknown", "error": "invalid_line_number", "source": "text_processor"}),
        ("line 1 unit ", None, {"action": "unknown", "error": "empty_unit_value", "source": "text_processor"}), # Empty unit
        ("line 5 unit pcs", 3, {"action": "unknown", "error": "line_out_of_range", "line": 4, "source": "text_processor"}),
        ("line one unit pcs", None, None), # Invalid line number format
        ("unit pcs", None, None), # Missing line number
    ],
)
def test_parse_unit_command(text, line_limit, expected):
    assert _parse_unit_command(text, line_limit) == expected

# Test cases for parse_line_command (main function)
@pytest.mark.parametrize(
    "text, line_limit, expected_action, expected_value_key, expected_value",
    [
        ("line 1 price 100.50", None, "edit_price", "value", 100.50),
        ("строка 2 название Товар Б", 5, "edit_name", "value", "Товар Б"),
        ("line 3 qty 10", None, "edit_quantity", "value", 10.0),
        ("строка 4 unit кг", None, "edit_unit", "value", "кг"),
        ("line 1 unknown_command 123", None, "unknown", "error", "unknown_command"), # No parser matches
        ("", None, "unknown", "error", "unknown_command"), # Empty string
        ("just some random text", None, "unknown", "error", "unknown_command"), # Not a command
        # Test line limit for the main function
        ("line 10 price 100", 5, "unknown", "error", "line_out_of_range"),
        # Test normalization (assuming normalize_text converts to lowercase)
        ("LINE 1 PRICE 200", None, "edit_price", "value", 200.0),
        # Test error from sub-parser (e.g. invalid price value)
        ("line 1 price abc", None, "unknown", "error", "invalid_price_value"),
    ],
)
def test_parse_line_command(text, line_limit, expected_action, expected_value_key, expected_value):
    result = parse_line_command(text, line_limit)
    assert result["action"] == expected_action
    if "source" in result: # successful parse has local_parser, errors have text_processor
        expected_source = "local_parser" if expected_action != "unknown" else "text_processor"
        assert result["source"] == expected_source
    if expected_value_key == "value":
        assert result.get("value") == expected_value
    elif expected_value_key == "error":
        assert result.get("error") == expected_value

    # Specific check for line_out_of_range error structure
    if expected_action == "unknown" and expected_value == "line_out_of_range":
        assert result.get("line") is not None


# Test for commands that should not be parsed by any sub-parser
def test_parse_line_command_no_match():
    text = "this is not a line command"
    expected = {
        "action": "unknown",
        "error": "unknown_command",
        "user_message": "I couldn't understand your command. Please try again with a simpler format.",
        "source": "text_processor" # Assuming create_error_response sets this
    }
    assert parse_line_command(text) == expected

def test_parse_line_command_empty_input():
    text = ""
    expected = {
        "action": "unknown",
        "error": "unknown_command",
        "user_message": "I couldn't understand your command. Please try again with a simpler format.",
        "source": "text_processor"
    }
    assert parse_line_command(text) == expected

def test_parse_line_command_invalid_line_number_string():
    text = "line zero price 10" # "zero" is not int
    # This will not be caught by _parse_price_command's int conversion directly
    # because the regex LINE_PRICE_PATTERN expects \d+ for line number.
    # So, it will fall through to unknown_command.
    expected = {
        "action": "unknown",
        "error": "unknown_command",
        "user_message": "I couldn't understand your command. Please try again with a simpler format.",
        "source": "text_processor"
    }
    assert parse_line_command(text) == expected
    
def test_parse_name_command_with_trailing_keywords():
    text = "line 1 name Product X price 10 qty 2 unit pcs"
    expected = {"action": "edit_name", "line": 0, "value": "Product X", "source": "local_parser"}
    assert _parse_name_command(text) == expected

    text = "строка 2 название Товар Y цена 20 количество 3 ед кг"
    expected = {"action": "edit_name", "line": 1, "value": "Товар Y", "source": "local_parser"}
    assert _parse_name_command(text) == expected

    text = "line 3 наименование Item Z unit штука"
    expected = {"action": "edit_name", "line": 2, "value": "Item Z", "source": "local_parser"}
    assert _parse_name_command(text) == expected

def test_parse_name_command_name_similar_to_keyword():
    # Test if a name that is a substring of a keyword or vice versa is parsed correctly
    text = "line 1 name pricetag" # "price" is a keyword
    expected = {"action": "edit_name", "line": 0, "value": "pricetag", "source": "local_parser"}
    assert _parse_name_command(text) == expected

    text = "line 1 name quantity of items" # "quantity" is a keyword
    expected = {"action": "edit_name", "line": 0, "value": "quantity of items", "source": "local_parser"}
    assert _parse_name_command(text) == expected

    text = "line 1 name unitarian" # "unit" is a keyword
    expected = {"action": "edit_name", "line": 0, "value": "unitarian", "source": "local_parser"}
    assert _parse_name_command(text) == expected

    text = "line 1 name линейка" # "line" is a keyword (assuming Russian context as well)
    expected = {"action": "edit_name", "line": 0, "value": "линейка", "source": "local_parser"}
    assert _parse_name_command(text) == expected
    
# It seems like text_processor.create_error_response is used.
# We should ensure that the 'source' is correctly attributed by it.
# For now, tests assume it's "text_processor" for errors.
# If text_processor.py is available and can be imported, we could make this more robust.
# For now, this is based on the observed behavior in line_parser.py
# (e.g., create_error_response("invalid_line_number"))
# The `source` key for errors is added by `create_error_response` in `text_processor.py`.
# If `create_error_response` is not available or we want to test `line_parser.py` in isolation
# for this specific detail, we might need to mock `create_error_response`.
# However, current tests check the output structure which implicitly tests this interaction.

# Further tests could involve mocking `normalize_text` and `parse_number`
# if we wanted to test the logic of `line_parser.py` completely isolated
# from `text_processor.py`. For this task, assuming `text_processor.py`
# functions as expected based on their names and usage in `line_parser.py`.
```
