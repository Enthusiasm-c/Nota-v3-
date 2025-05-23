import pytest
from decimal import Decimal
from app.formatter import escape_md, format_idr, _row, W_IDX, W_NAME, W_QTY, W_UNIT, W_PRICE, W_TOTAL, W_STATUS


class TestEscapeMd:
    """Test escape_md function."""

    def test_escape_md_basic_characters(self):
        """Test escaping basic special characters."""
        text = "_*[]()~`>#+-=|{}.!"
        result = escape_md(text)
        expected = r"\_\*\[\]\(\)\~\`\>\#\+\-\=\|\{\}\.\!"
        assert result == expected

    def test_escape_md_mixed_text(self):
        """Test escaping mixed text with special characters."""
        text = "Hello *world*! How are you?"
        result = escape_md(text)
        expected = r"Hello \*world\*\! How are you?"  # ? is NOT escaped
        assert result == expected

    def test_escape_md_no_special_characters(self):
        """Test text without special characters."""
        text = "Hello world"
        result = escape_md(text)
        assert result == "Hello world"

    def test_escape_md_empty_string(self):
        """Test escaping empty string."""
        result = escape_md("")
        assert result == ""

    def test_escape_md_non_string_input(self):
        """Test escaping non-string input."""
        result = escape_md(123)
        assert result == "123"
        
        result = escape_md(None)
        assert result == "None"
        
        result = escape_md([1, 2, 3])
        assert result == r"\[1, 2, 3\]"

    def test_escape_md_version_parameter(self):
        """Test that version parameter is accepted."""
        text = "Hello *world*"
        result1 = escape_md(text, version=1)
        result2 = escape_md(text, version=2)
        # Both should work the same way
        assert result1 == result2
        assert result1 == r"Hello \*world\*"

    def test_escape_md_complex_markdown(self):
        """Test escaping complex markdown structures."""
        text = "[link](https://example.com) `code` **bold** __italic__"
        result = escape_md(text)
        expected = r"\[link\]\(https://example\.com\) \`code\` \*\*bold\*\* \_\_italic\_\_"
        assert result == expected

    def test_escape_md_code_block(self):
        """Test escaping code block syntax."""
        text = "```python\nprint('hello')\n```"
        result = escape_md(text)
        # Newlines are NOT escaped, they remain as actual newlines
        expected = "\\`\\`\\`python\nprint\\('hello'\\)\n\\`\\`\\`"
        assert result == expected


class TestFormatIdr:
    """Test format_idr function."""

    def test_format_idr_integer(self):
        """Test formatting integer values."""
        assert format_idr(1234) == "1\u2009234 IDR"
        assert format_idr(1000000) == "1\u2009000\u2009000 IDR"
        assert format_idr(0) == "0 IDR"

    def test_format_idr_float(self):
        """Test formatting float values."""
        assert format_idr(1234.56) == "1\u2009235 IDR"  # Rounded
        assert format_idr(1234.00) == "1\u2009234 IDR"

    def test_format_idr_decimal(self):
        """Test formatting Decimal values."""
        assert format_idr(Decimal("1234")) == "1\u2009234 IDR"
        assert format_idr(Decimal("1234567.89")) == "1\u2009234\u2009568 IDR"

    def test_format_idr_string_numbers(self):
        """Test formatting string numbers."""
        assert format_idr("1234") == "1\u2009234 IDR"
        assert format_idr("1234.56") == "1\u2009235 IDR"

    def test_format_idr_none(self):
        """Test formatting None value."""
        assert format_idr(None) == "—"

    def test_format_idr_invalid_values(self):
        """Test formatting invalid values."""
        assert format_idr("invalid") == "—"
        assert format_idr("abc123") == "—"
        assert format_idr([1, 2, 3]) == "—"
        assert format_idr({"key": "value"}) == "—"

    def test_format_idr_negative_values(self):
        """Test formatting negative values."""
        assert format_idr(-1234) == "-1\u2009234 IDR"
        assert format_idr(-1000000) == "-1\u2009000\u2009000 IDR"

    def test_format_idr_large_numbers(self):
        """Test formatting very large numbers."""
        assert format_idr(1234567890) == "1\u2009234\u2009567\u2009890 IDR"
        assert format_idr(999999999999) == "999\u2009999\u2009999\u2009999 IDR"

    def test_format_idr_edge_cases(self):
        """Test edge cases."""
        assert format_idr("") == "—"
        assert format_idr("0") == "0 IDR"
        assert format_idr("0.0") == "0 IDR"


class TestRow:
    """Test _row function."""

    def test_row_basic(self):
        """Test basic row formatting."""
        result = _row(1, "Apple", 10, "kg", 5000, 50000, "ok")
        
        # Check that all components are present
        assert "1" in result
        assert "Apple" in result
        assert "10" in result
        assert "kg" in result
        assert "5\u2009000 IDR" in result
        assert "50\u2009000 IDR" in result
        assert "ok" in result

    def test_row_long_name_truncated(self):
        """Test that long names are truncated."""
        long_name = "Very long product name that should be truncated"
        result = _row(1, long_name, 5, "pcs", 1000, 5000, "partial")
        
        # Name should be truncated with ellipsis
        assert "…" in result
        # Should not contain the full long name
        assert long_name not in result

    def test_row_with_none_values(self):
        """Test row with None price and total."""
        result = _row(2, "Product", 3, "l", None, None, None)
        
        assert "2" in result
        assert "Product" in result
        assert "3" in result
        assert "l" in result
        # None values should be shown as dashes
        assert "—" in result

    def test_row_with_empty_values(self):
        """Test row with empty string values."""
        result = _row(3, "Item", 1, "unit", "", "", "")
        
        assert "3" in result
        assert "Item" in result
        assert "1" in result
        assert "unit" in result
        # Empty strings should be shown as dashes for price/total
        assert "—" in result

    def test_row_with_float_quantities(self):
        """Test row with float quantities."""
        result = _row(4, "Milk", 2.5, "l", 15000, 37500, "ok")
        
        assert "4" in result
        assert "Milk" in result
        assert "2.5" in result
        assert "l" in result

    def test_row_with_string_index(self):
        """Test row with string index."""
        result = _row("A", "Product", 1, "pcs", 1000, 1000, "verified")
        
        assert "A" in result
        assert "Product" in result

    def test_row_formatting_alignment(self):
        """Test that row has proper formatting and alignment."""
        result = _row(1, "Test", 5, "kg", 10000, 50000, "ok")
        
        # Should be a single line
        assert "\n" not in result
        
        # Should have proper spacing
        assert len(result.split()) >= 6  # At least 6 components

    def test_row_exact_name_length(self):
        """Test name that is exactly the maximum width."""
        # Create name exactly W_NAME characters long
        exact_name = "A" * W_NAME
        result = _row(1, exact_name, 1, "pcs", 1000, 1000, "ok")
        
        # Should not be truncated
        assert "…" not in result
        assert exact_name in result

    def test_row_name_just_over_limit(self):
        """Test name that is just over the limit."""
        # Create name one character longer than W_NAME
        over_limit_name = "A" * (W_NAME + 1)
        result = _row(1, over_limit_name, 1, "pcs", 1000, 1000, "ok")
        
        # Should be truncated
        assert "…" in result
        assert over_limit_name not in result


class TestFormatterConstants:
    """Test formatter constants."""

    def test_width_constants_are_positive(self):
        """Test that all width constants are positive integers."""
        constants = [W_IDX, W_NAME, W_QTY, W_UNIT, W_PRICE, W_TOTAL, W_STATUS]
        
        for const in constants:
            assert isinstance(const, int)
            assert const > 0

    def test_width_constants_reasonable_values(self):
        """Test that width constants have reasonable values."""
        # These should be reasonable for table formatting
        assert W_IDX >= 3  # At least 3 chars for index
        assert W_NAME >= 10  # At least 10 chars for name
        assert W_QTY >= 4  # At least 4 chars for quantity
        assert W_UNIT >= 4  # At least 4 chars for unit
        assert W_PRICE >= 8  # At least 8 chars for price
        assert W_TOTAL >= 8  # At least 8 chars for total
        assert W_STATUS >= 6  # At least 6 chars for status


class TestFormatterIntegration:
    """Integration tests for formatter module."""

    def test_full_invoice_line_formatting(self):
        """Test formatting a complete invoice line."""
        # Simulate a real invoice line
        result = _row(
            idx=1,
            name="Fresh Apples",
            qty=5.5,
            unit="kg",
            price=25000,
            total=137500,
            status="verified"
        )
        
        # Should contain all expected elements
        assert "1" in result
        assert "Fresh Apples" in result
        assert "5.5" in result
        assert "kg" in result
        assert "25\u2009000 IDR" in result
        assert "137\u2009500 IDR" in result
        assert "verified" in result

    def test_markdown_escaping_with_special_names(self):
        """Test markdown escaping with product names containing special chars."""
        special_name = "Coca-Cola [500ml] (Fresh!)"
        escaped = escape_md(special_name)
        
        # Should escape special characters
        assert "\\" in escaped
        assert "[" not in escaped or "\\[" in escaped
        assert "]" not in escaped or "\\]" in escaped
        assert "(" not in escaped or "\\(" in escaped
        assert ")" not in escaped or "\\)" in escaped
        assert "!" not in escaped or "\\!" in escaped

    def test_zero_values_formatting(self):
        """Test formatting with zero values."""
        result = _row(0, "Free Sample", 0, "", 0, 0, "")
        
        assert "0" in result
        assert "Free Sample" in result
        assert "0 IDR" in result

    def test_very_large_numbers(self):
        """Test formatting with very large numbers."""
        large_price = 999999999
        large_total = 9999999990
        
        result = _row(999, "Expensive Item", 10, "pcs", large_price, large_total, "pending")
        
        # Should format large numbers correctly
        assert "999\u2009999\u2009999 IDR" in result
        assert "9\u2009999\u2009999\u2009990 IDR" in result 
 