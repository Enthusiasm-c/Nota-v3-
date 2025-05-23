import pytest
from app.parsers.general_parser import parse_supplier_command, parse_total_command
from unittest.mock import patch, MagicMock

# Test cases for parse_supplier_command
@pytest.mark.parametrize(
    "text, expected",
    [
        ("поставщик ООО Ромашка", {"action": "set_supplier", "supplier": "ООО Ромашка", "source": "general_parser"}),
        ("supplier ACME Corp", {"action": "set_supplier", "supplier": "ACME Corp", "source": "general_parser"}),
        ("изменить поставщика на ЗАО Вектор", {"action": "set_supplier", "supplier": "ЗАО Вектор", "source": "general_parser"}),
        ("change supplier to Bubba Gump", {"action": "set_supplier", "supplier": "Bubba Gump", "source": "general_parser"}),
        ("поставщик   Много  Пробелов  ", {"action": "set_supplier", "supplier": "Много  Пробелов", "source": "general_parser"}),
        ("поставщик", {"action": "unknown", "error": "empty_supplier_name", "original_text": "поставщик", "source": "general_parser"}), # Just keyword
        ("supplier ", {"action": "unknown", "error": "empty_supplier_name", "original_text": "supplier ", "source": "general_parser"}), # Keyword with space
        ("изменить поставщика на", {"action": "unknown", "error": "empty_supplier_name", "original_text": "изменить поставщика на", "source": "general_parser"}), # Prefix without value
        ("change supplier to ", {"action": "unknown", "error": "empty_supplier_name", "original_text": "change supplier to ", "source": "general_parser"}), # Prefix with space
        ("поставщик поставщик", {"action": "unknown", "error": "empty_supplier_name", "original_text": "поставщик поставщик", "source": "general_parser"}), # Keyword as name
        ("supplier supplier", {"action": "unknown", "error": "empty_supplier_name", "original_text": "supplier supplier", "source": "general_parser"}), # Keyword as name
        ("не команда поставщика", None), # Not a supplier command
        ("", None), # Empty string
    ],
)
def test_parse_supplier_command(text, expected):
    assert parse_supplier_command(text) == expected

# Test cases for parse_total_command
# These tests will implicitly test the fallback parse_number if text_processor.parse_number is not found.
@pytest.mark.parametrize(
    "text, expected_action, expected_total, expected_error, expected_original_value",
    [
        ("общая сумма 123.45", "set_total", 123.45, None, None),
        ("total 5000", "set_total", 5000.0, None, None),
        ("итого 100к", "set_total", 100000.0, None, None),
        ("общая сумма 200,75", "set_total", 200.75, None, None),
        ("total 300.000", "set_total", 300000.0, None, None), # "300.000" likely parsed as 300 with k by fallback
        ("итого 50,5к", "set_total", 50500.0, None, None),
        ("общая сумма 1 000 000", "set_total", 1000000.0, None, None), # Number with spaces
        ("total amount 123.45", "set_total", 123.45, None, None), # "total amount" variant
        ("общая сумма abc", "unknown", None, "invalid_total_value", "abc"), # Invalid number
        ("total", "unknown", None, "empty_total_value", None), # Keyword without value
        ("итого ", "unknown", None, "empty_total_value", None), # Keyword with space, no value
        ("общая сумма", "unknown", None, "empty_total_value", None), # Keyword, no value
        ("не команда суммы", None, None, None, None), # Not a total command
        ("", None, None, None, None), # Empty string
        ("total 10.5k", "set_total", 10500.0, None, None),
        ("итого 1.234к", "set_total", 1234.0, None, None), # Fallback might parse "1.234" as 1.234 then *1000
        ("общая сумма 0.5к", "set_total", 500.0, None, None),
        ("total 1,2k", "set_total", 1200.0, None, None),
    ],
)
def test_parse_total_command_with_fallback_parse_number(text, expected_action, expected_total, expected_error, expected_original_value):
    # This test runs using the fallback parse_number by default if text_processor.parse_number is not in sys.modules
    # For more controlled testing, we could explicitly mock the import.

    # Simulate text_processor.parse_number not being available to test fallback
    with patch.dict('sys.modules', {'app.parsers.text_processor': None}):
        # Need to reload general_parser for the import error to be triggered
        import importlib
        from app.parsers import general_parser
        importlib.reload(general_parser)
        
        result = general_parser.parse_total_command(text)

        if expected_action is None: # Should not parse
            assert result is None
        else:
            assert result["action"] == expected_action
            assert result["source"] == "general_parser"
            if expected_error:
                assert result["error"] == expected_error
                if expected_original_value:
                    assert result["original_value"] == expected_original_value
            else:
                assert result.get("total") == expected_total
        
        # Reload again to restore normal behavior for other tests if any
        # This is tricky because modules are cached.
        # A cleaner way would be to mock the import directly.
        # For now, let's assume each test file runs in a somewhat isolated manner for module loading,
        # or rely on the fact that the actual import will be attempted once per module load.


# Test parse_total_command specifically with a mocked successful import of parse_number
def test_parse_total_command_with_mocked_text_processor_parse_number():
    mock_parse_number = MagicMock()

    # Define a side effect for the mock that mimics actual parse_number
    def mock_parse_number_side_effect(value_str):
        if value_str == "123.45_mock":
            return 123.45
        elif value_str == "500k_mock":
            return 500000.0
        elif value_str == "invalid_mock":
            return None
        return None # Default fallback

    mock_parse_number.side_effect = mock_parse_number_side_effect

    with patch.dict('sys.modules', {'app.parsers.text_processor': MagicMock(parse_number=mock_parse_number)}):
        import importlib
        from app.parsers import general_parser
        importlib.reload(general_parser) # Reload to use the mocked import

        # Test case 1: Valid number parsed by mock
        text1 = "total 123.45_mock"
        expected1 = {"action": "set_total", "total": 123.45, "source": "general_parser"}
        assert general_parser.parse_total_command(text1) == expected1
        mock_parse_number.assert_called_with("123.45_mock")

        # Test case 2: Valid number with 'k' parsed by mock
        text2 = "total 500k_mock"
        expected2 = {"action": "set_total", "total": 500000.0, "source": "general_parser"}
        assert general_parser.parse_total_command(text2) == expected2
        mock_parse_number.assert_called_with("500k_mock")
        
        # Test case 3: Invalid number parsed by mock (returns None)
        text3 = "total invalid_mock"
        expected3 = {"action": "unknown", "error": "invalid_total_value", "original_value": "invalid_mock", "source": "general_parser"}
        assert general_parser.parse_total_command(text3) == expected3
        mock_parse_number.assert_called_with("invalid_mock")

        # Test case 4: Empty value string after keyword
        text4 = "total " # The regex captures an empty string for the value part
        expected4 = {"action": "unknown", "error": "empty_total_value", "original_text": "total ", "source": "general_parser"}
        # parse_number should not be called if the captured value_str is empty
        # The check `if not total_value_str:` should handle this before `parse_number` is called.
        # Let's adjust the mock and test
        mock_parse_number.reset_mock()
        assert general_parser.parse_total_command(text4) == expected4
        mock_parse_number.assert_not_called()


# It's hard to directly test the fallback `parse_number` in `general_parser.py`
# without also testing `parse_total_command` or complex import manipulations.
# The parametrize test for `parse_total_command` already covers cases where the
# fallback `parse_number` would be used if the import `from app.parsers.text_processor import parse_number` fails.

# Let's add a specific test for the fallback parse_number if we can force its direct use
# This requires ensuring the primary `parse_number` is not imported.
# We can achieve this by removing `app.parsers.text_processor` from `sys.modules`
# and then reloading `app.parsers.general_parser`.

@pytest.mark.parametrize(
    "value_str, expected_num",
    [
        ("100", 100.0),
        ("123.45", 123.45),
        ("200,75", 200.75),
        ("1k", 1000.0),
        ("0.5k", 500.0),
        ("1.2K", 1200.0),
        ("1,5к", 1500.0),
        ("  1 000 k  ", 1000000.0), # Spaces and k
        ("abc", None),
        ("1.2.3", None), # Invalid number format
        ("k", None), # Just k
        ("100 kk", None) # Double k
    ]
)
def test_internal_fallback_parse_number(value_str, expected_num):
    # This is a bit of a hack to test the internal fallback.
    # It assumes that if `app.parsers.text_processor` is removed from sys.modules
    # and `general_parser` is reloaded, the ImportError will trigger the fallback definition.
    with patch.dict('sys.modules'):
        if 'app.parsers.text_processor' in sys.modules:
            del sys.modules['app.parsers.text_processor']
        
        import importlib
        from app.parsers import general_parser # Reload the module
        importlib.reload(general_parser)

        # Now, general_parser.parse_number should be the fallback version.
        # Note: This direct access might not be standard if it's meant to be "private"
        # but the code defines it at the module level in the except block.
        assert hasattr(general_parser, 'parse_number'), "Fallback parse_number not defined as expected"
        assert general_parser.parse_number(value_str) == expected_num

        # It's important to restore sys.modules if other tests depend on the original state.
        # Pytest usually isolates test files, but internal module caching can be tricky.
        # For this specific structure, it might be better to test parse_number
        # via parse_total_command as done in test_parse_total_command_with_fallback_parse_number
        # or if text_processor.py and its parse_number is available, test that separately.
        # This test is more of a "white-box" test for the fallback.
```
