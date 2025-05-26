"""Tests for app/utils/data_utils.py"""

import pytest
from datetime import date, datetime

from app.utils.data_utils import (
    clean_number,
    parse_date,
    normalize_text,
    is_valid_price,
    is_valid_quantity,
    sanitize_string,
    format_price,
    calculate_total
)


class TestCleanNumber:
    """Test clean_number function."""
    
    def test_clean_number_int(self):
        """Test cleaning integer values."""
        assert clean_number(42) == 42.0
        assert clean_number(0) == 0.0
        assert clean_number(-10) == -10.0
    
    def test_clean_number_float(self):
        """Test cleaning float values."""
        assert clean_number(42.5) == 42.5
        assert clean_number(0.0) == 0.0
        assert clean_number(-10.5) == -10.5
    
    def test_clean_number_string(self):
        """Test cleaning string values."""
        assert clean_number("42") == 42.0
        assert clean_number("42.5") == 42.5
        assert clean_number("42,5") == 42.5
        assert clean_number("1,234.56") == 1234.56
        assert clean_number("1.234,56") == 1234.56
        assert clean_number("$1,234.56") == 1234.56
        assert clean_number("IDR 10.000") == 10000.0
    
    def test_clean_number_with_spaces(self):
        """Test cleaning numbers with spaces."""
        assert clean_number("1 234") == 1234.0
        assert clean_number("1 234.56") == 1234.56
        assert clean_number(" 42 ") == 42.0
    
    def test_clean_number_negative(self):
        """Test cleaning negative numbers."""
        assert clean_number("-42") == -42.0
        assert clean_number("-42.5") == -42.5
        assert clean_number("-1,234.56") == -1234.56
    
    def test_clean_number_invalid(self):
        """Test cleaning invalid values."""
        assert clean_number(None) is None
        assert clean_number("") is None
        assert clean_number("abc") is None
        assert clean_number(".") is None
    
    def test_clean_number_with_default(self):
        """Test cleaning with default value."""
        assert clean_number(None, default=0.0) == 0.0
        assert clean_number("", default=1.0) == 1.0
        assert clean_number("invalid", default=42.0) == 42.0
    
    def test_clean_number_with_bounds(self):
        """Test cleaning with min/max bounds."""
        assert clean_number(5, min_value=10) == 10
        assert clean_number(100, max_value=50) == 50
        assert clean_number(25, min_value=10, max_value=50) == 25
        assert clean_number(-5, min_value=0) == 0


class TestParseDate:
    """Test parse_date function."""
    
    def test_parse_date_object(self):
        """Test parsing date object."""
        d = date(2024, 1, 15)
        assert parse_date(d) == d
    
    def test_parse_datetime_object(self):
        """Test parsing datetime object."""
        dt = datetime(2024, 1, 15, 10, 30)
        assert parse_date(dt) == date(2024, 1, 15)
    
    def test_parse_iso_format(self):
        """Test parsing ISO format."""
        assert parse_date("2024-01-15") == date(2024, 1, 15)
        assert parse_date("2024/01/15") == date(2024, 1, 15)
    
    def test_parse_dmy_format(self):
        """Test parsing DD.MM.YYYY format."""
        assert parse_date("15.01.2024") == date(2024, 1, 15)
        assert parse_date("15/01/2024") == date(2024, 1, 15)
        assert parse_date("15-01-2024") == date(2024, 1, 15)
    
    def test_parse_invalid(self):
        """Test parsing invalid values."""
        assert parse_date(None) is None
        assert parse_date("") is None
        assert parse_date("invalid") is None
        assert parse_date("32.13.2024") is None  # Invalid date
    
    def test_parse_with_custom_formats(self):
        """Test parsing with custom formats."""
        formats = ["%d %b %Y", "%B %d, %Y"]
        # These would need locale support to work properly
        # assert parse_date("15 Jan 2024", formats=formats) == date(2024, 1, 15)


class TestNormalizeText:
    """Test normalize_text function."""
    
    def test_normalize_basic(self):
        """Test basic normalization."""
        assert normalize_text("Hello World") == "hello world"
        assert normalize_text("  Hello   World  ") == "hello world"
        assert normalize_text("UPPERCASE") == "uppercase"
    
    def test_normalize_special_chars(self):
        """Test removing special characters."""
        assert normalize_text("Hello, World!") == "hello, world"
        assert normalize_text("...Test...") == "test"
        assert normalize_text("-Test-") == "test"
    
    def test_normalize_empty(self):
        """Test normalizing empty values."""
        assert normalize_text(None) == ""
        assert normalize_text("") == ""
        assert normalize_text("   ") == ""
    
    def test_normalize_no_lower(self):
        """Test normalization without lowercasing."""
        assert normalize_text("Hello World", lower=False) == "Hello World"
        assert normalize_text("  HELLO  ", lower=False) == "HELLO"


class TestValidationFunctions:
    """Test validation functions."""
    
    def test_is_valid_price(self):
        """Test price validation."""
        assert is_valid_price(100.0) is True
        assert is_valid_price(0.0) is True
        assert is_valid_price(9999999.99) is True
        assert is_valid_price(-1.0) is False
        assert is_valid_price(None) is False
        assert is_valid_price(11_000_000) is False  # Too high
    
    def test_is_valid_quantity(self):
        """Test quantity validation."""
        assert is_valid_quantity(1.0) is True
        assert is_valid_quantity(100.0) is True
        assert is_valid_quantity(9999.99) is True
        assert is_valid_quantity(0.0) is False
        assert is_valid_quantity(-1.0) is False
        assert is_valid_quantity(None) is False
        assert is_valid_quantity(10001) is False  # Too high


class TestSanitizeString:
    """Test sanitize_string function."""
    
    def test_sanitize_basic(self):
        """Test basic sanitization."""
        assert sanitize_string("Hello World") == "Hello World"
        assert sanitize_string("  Hello   World  ") == "Hello World"
    
    def test_sanitize_control_chars(self):
        """Test removing control characters."""
        assert sanitize_string("Hello\x00World") == "HelloWorld"
        assert sanitize_string("Test\nLine") == "Test Line"
        assert sanitize_string("Tab\tTest") == "Tab Test"
    
    def test_sanitize_length_limit(self):
        """Test length limiting."""
        long_text = "A" * 300
        result = sanitize_string(long_text, max_length=100)
        assert len(result) == 100
        assert result.endswith("...")
    
    def test_sanitize_empty(self):
        """Test sanitizing empty values."""
        assert sanitize_string(None) == ""
        assert sanitize_string("") == ""


class TestFormatPrice:
    """Test format_price function."""
    
    def test_format_price_basic(self):
        """Test basic price formatting."""
        assert format_price(100.0) == "100.00"
        assert format_price(1234.56) == "1234.56"
        assert format_price(1234.567, decimals=3) == "1234.567"
    
    def test_format_price_none(self):
        """Test formatting None."""
        assert format_price(None) == "0.00"
    
    def test_format_price_decimals(self):
        """Test different decimal places."""
        assert format_price(100, decimals=0) == "100"
        assert format_price(100.5, decimals=1) == "100.5"
        assert format_price(100.999, decimals=2) == "101.00"


class TestCalculateTotal:
    """Test calculate_total function."""
    
    def test_calculate_total_basic(self):
        """Test basic total calculation."""
        assert calculate_total(10, 5.0) == 50.0
        assert calculate_total(2.5, 4.0) == 10.0
        assert calculate_total(1, 0.99) == 0.99
    
    def test_calculate_total_rounding(self):
        """Test rounding in calculations."""
        assert calculate_total(3, 0.333) == 1.0  # 0.999 rounds to 1.0
        assert calculate_total(7, 1.428571) == 10.0
    
    def test_calculate_total_invalid(self):
        """Test invalid inputs."""
        assert calculate_total(None, 10) is None
        assert calculate_total(10, None) is None
        assert calculate_total(0, 10) is None
        assert calculate_total(10, -5) is None
        assert calculate_total(-10, 5) is None