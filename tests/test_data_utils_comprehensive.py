"""
Comprehensive tests for the centralized data utility functions.
Tests all utility functions that were consolidated from validators.
"""

import pytest
from datetime import date, datetime, timedelta
from app.utils.data_utils import clean_number, parse_date, is_valid_price, is_valid_quantity


class TestCleanNumber:
    """Test suite for clean_number function."""
    
    def test_clean_number_integers(self):
        """Test clean_number with integer inputs."""
        assert clean_number(123) == 123.0
        assert clean_number(0) == 0.0
        assert clean_number(-456) == -456.0
    
    def test_clean_number_floats(self):
        """Test clean_number with float inputs."""
        assert clean_number(123.45) == 123.45
        assert clean_number(0.0) == 0.0
        assert clean_number(-456.78) == -456.78
    
    def test_clean_number_string_basic(self):
        """Test clean_number with basic string inputs."""
        assert clean_number("123") == 123.0
        assert clean_number("123.45") == 123.45
        assert clean_number("-456.78") == -456.78
        assert clean_number("0") == 0.0
    
    def test_clean_number_string_with_commas(self):
        """Test clean_number with comma separators."""
        assert clean_number("1,234.56") == 1234.56
        assert clean_number("1,000") == 1000.0
        assert clean_number("10,000,000") == 10000000.0
    
    def test_clean_number_european_format(self):
        """Test clean_number with European number format (comma as decimal)."""
        assert clean_number("1.234,56") == 1234.56
        assert clean_number("1.000,00") == 1000.0
        assert clean_number("123,45") == 123.45
    
    def test_clean_number_currency_symbols(self):
        """Test clean_number with currency symbols."""
        assert clean_number("Rp 50,000") == 50000.0
        assert clean_number("IDR 100.500") == 100500.0
        assert clean_number("USD 1,234.56") == 1234.56
        assert clean_number("EUR 999,99") == 999.99
    
    def test_clean_number_with_spaces(self):
        """Test clean_number with spaces."""
        assert clean_number("1 234 567") == 1234567.0
        assert clean_number(" 123.45 ") == 123.45
        assert clean_number("1 000,50") == 1000.50
    
    def test_clean_number_abbreviations(self):
        """Test clean_number with number abbreviations."""
        assert clean_number("5k") == 5000.0
        assert clean_number("5K") == 5000.0
        assert clean_number("2m") == 2000000.0
        assert clean_number("2M") == 2000000.0
        assert clean_number("1.5k") == 1500.0
        assert clean_number("3тыс") == 3000.0
        assert clean_number("2млн") == 2000000.0
    
    def test_clean_number_negative_values(self):
        """Test clean_number with negative values."""
        assert clean_number("-123") == -123.0
        assert clean_number("-1,234.56") == -1234.56
        assert clean_number("-Rp 50,000") == -50000.0
        assert clean_number("-5k") == -5000.0
    
    def test_clean_number_invalid_inputs(self):
        """Test clean_number with invalid inputs."""
        assert clean_number("invalid") == 0.0  # Default behavior
        assert clean_number("") == 0.0
        assert clean_number("abc123") == 0.0
        assert clean_number(None) == 0.0
    
    def test_clean_number_with_default(self):
        """Test clean_number with custom default value."""
        assert clean_number("invalid", default=None) is None
        assert clean_number("invalid", default=-1.0) == -1.0
        assert clean_number(None, default=100.0) == 100.0
    
    def test_clean_number_with_bounds(self):
        """Test clean_number with min/max bounds."""
        # Test min_value
        result = clean_number("5", min_value=10.0)
        assert result == 10.0  # Should be clamped to minimum
        
        # Test max_value
        result = clean_number("100", max_value=50.0)
        assert result == 50.0  # Should be clamped to maximum
        
        # Test within bounds
        result = clean_number("25", min_value=10.0, max_value=50.0)
        assert result == 25.0  # Should remain unchanged
    
    def test_clean_number_edge_cases(self):
        """Test clean_number with edge cases."""
        # Multiple decimal points
        assert clean_number("12.34.56") == 1234.56  # Should handle gracefully
        
        # Only decimal point
        assert clean_number(".") == 0.0
        
        # Very long numbers
        assert clean_number("123456789012345") == 123456789012345.0
        
        # Scientific notation
        assert clean_number("1e3") == 1000.0
        assert clean_number("1.5e2") == 150.0


class TestParseDate:
    """Test suite for parse_date function."""
    
    def test_parse_date_none_input(self):
        """Test parse_date with None input."""
        assert parse_date(None) is None
    
    def test_parse_date_datetime_input(self):
        """Test parse_date with datetime input."""
        dt = datetime(2025, 5, 28, 10, 30, 45)
        result = parse_date(dt)
        assert result == date(2025, 5, 28)
    
    def test_parse_date_date_input(self):
        """Test parse_date with date input."""
        d = date(2025, 5, 28)
        result = parse_date(d)
        assert result == d
    
    def test_parse_date_iso_format(self):
        """Test parse_date with ISO format strings."""
        assert parse_date("2025-05-28") == date(2025, 5, 28)
        assert parse_date("2025-01-01") == date(2025, 1, 1)
        assert parse_date("2025-12-31") == date(2025, 12, 31)
    
    def test_parse_date_european_format(self):
        """Test parse_date with European date formats."""
        assert parse_date("28.05.2025") == date(2025, 5, 28)
        assert parse_date("01.01.2025") == date(2025, 1, 1)
        assert parse_date("31.12.2025") == date(2025, 12, 31)
    
    def test_parse_date_slash_format(self):
        """Test parse_date with slash-separated formats."""
        assert parse_date("28/05/2025") == date(2025, 5, 28)
        assert parse_date("01/01/2025") == date(2025, 1, 1)
        assert parse_date("31/12/2025") == date(2025, 12, 31)
    
    def test_parse_date_dash_format(self):
        """Test parse_date with dash-separated formats."""
        assert parse_date("28-05-2025") == date(2025, 5, 28)
        assert parse_date("01-01-2025") == date(2025, 1, 1)
        assert parse_date("31-12-2025") == date(2025, 12, 31)
    
    def test_parse_date_reverse_format(self):
        """Test parse_date with YYYY/MM/DD format."""
        assert parse_date("2025/05/28") == date(2025, 5, 28)
        assert parse_date("2025/01/01") == date(2025, 1, 1)
        assert parse_date("2025/12/31") == date(2025, 12, 31)
    
    def test_parse_date_month_names(self):
        """Test parse_date with month names."""
        # Full month names
        assert parse_date("28 May 2025") == date(2025, 5, 28)
        assert parse_date("January 1, 2025") == date(2025, 1, 1)
        
        # Abbreviated month names
        assert parse_date("28 Jan 2025") == date(2025, 1, 28)
        assert parse_date("Dec 31, 2025") == date(2025, 12, 31)
    
    def test_parse_date_custom_formats(self):
        """Test parse_date with custom format list."""
        custom_formats = ["%m-%d-%Y", "%Y%m%d"]
        
        # US format: MM-DD-YYYY
        assert parse_date("05-28-2025", formats=custom_formats) == date(2025, 5, 28)
        
        # Compact format: YYYYMMDD
        assert parse_date("20250528", formats=custom_formats) == date(2025, 5, 28)
    
    def test_parse_date_invalid_inputs(self):
        """Test parse_date with invalid inputs."""
        assert parse_date("invalid-date") is None
        assert parse_date("") is None
        assert parse_date("2025-13-01") is None  # Invalid month
        assert parse_date("2025-02-30") is None  # Invalid day
        assert parse_date("32/01/2025") is None  # Invalid day
        assert parse_date("not a date") is None
    
    def test_parse_date_edge_cases(self):
        """Test parse_date with edge cases."""
        # Leap year
        assert parse_date("29/02/2024") == date(2024, 2, 29)  # 2024 is leap year
        assert parse_date("29/02/2025") is None  # 2025 is not leap year
        
        # Year boundaries
        assert parse_date("31/12/2024") == date(2024, 12, 31)
        assert parse_date("01/01/2025") == date(2025, 1, 1)
        
        # Month boundaries
        assert parse_date("31/01/2025") == date(2025, 1, 31)
        assert parse_date("28/02/2025") == date(2025, 2, 28)
    
    def test_parse_date_whitespace_handling(self):
        """Test parse_date with extra whitespace."""
        assert parse_date("  2025-05-28  ") == date(2025, 5, 28)
        assert parse_date("\t28.05.2025\n") == date(2025, 5, 28)
        assert parse_date(" 28 / 05 / 2025 ") == date(2025, 5, 28)


class TestIsValidPrice:
    """Test suite for is_valid_price function."""
    
    def test_is_valid_price_valid_prices(self):
        """Test is_valid_price with valid prices."""
        assert is_valid_price(100.0) is True
        assert is_valid_price(0.0) is True
        assert is_valid_price(1.50) is True
        assert is_valid_price(999999.99) is True
        assert is_valid_price(10000000) is True  # At default max
    
    def test_is_valid_price_invalid_prices(self):
        """Test is_valid_price with invalid prices."""
        assert is_valid_price(-1.0) is False  # Negative
        assert is_valid_price(-100.0) is False  # Negative
        assert is_valid_price(10000001) is False  # Above default max
        assert is_valid_price(None) is False  # None
    
    def test_is_valid_price_custom_max(self):
        """Test is_valid_price with custom maximum."""
        assert is_valid_price(500.0, max_price=1000.0) is True
        assert is_valid_price(1000.0, max_price=1000.0) is True
        assert is_valid_price(1001.0, max_price=1000.0) is False
    
    def test_is_valid_price_edge_cases(self):
        """Test is_valid_price with edge cases."""
        # Very small positive values
        assert is_valid_price(0.01) is True
        assert is_valid_price(0.0001) is True
        
        # Zero
        assert is_valid_price(0.0) is True
        
        # Boundary values
        assert is_valid_price(10000000.0) is True  # Exactly at default max
        assert is_valid_price(10000000.01) is False  # Just over default max


class TestIsValidQuantity:
    """Test suite for is_valid_quantity function."""
    
    def test_is_valid_quantity_valid_quantities(self):
        """Test is_valid_quantity with valid quantities."""
        assert is_valid_quantity(1.0) is True
        assert is_valid_quantity(0.5) is True
        assert is_valid_quantity(100.0) is True
        assert is_valid_quantity(9999.0) is True
        assert is_valid_quantity(10000.0) is True  # At default max
    
    def test_is_valid_quantity_invalid_quantities(self):
        """Test is_valid_quantity with invalid quantities."""
        assert is_valid_quantity(-1.0) is False  # Negative
        assert is_valid_quantity(0.0) is False  # Zero
        assert is_valid_quantity(10001.0) is False  # Above default max
        assert is_valid_quantity(None) is False  # None
    
    def test_is_valid_quantity_custom_max(self):
        """Test is_valid_quantity with custom maximum."""
        assert is_valid_quantity(50.0, max_qty=100.0) is True
        assert is_valid_quantity(100.0, max_qty=100.0) is True
        assert is_valid_quantity(101.0, max_qty=100.0) is False
    
    def test_is_valid_quantity_edge_cases(self):
        """Test is_valid_quantity with edge cases."""
        # Very small positive values
        assert is_valid_quantity(0.001) is True
        assert is_valid_quantity(0.1) is True
        
        # Boundary values
        assert is_valid_quantity(10000.0) is True  # Exactly at default max
        assert is_valid_quantity(10000.01) is False  # Just over default max


class TestDataUtilsIntegration:
    """Integration tests for data utility functions."""
    
    def test_price_validation_with_clean_number(self):
        """Test integration between clean_number and is_valid_price."""
        # Clean and validate in sequence
        price_str = "Rp 15,000.50"
        cleaned_price = clean_number(price_str)
        is_valid = is_valid_price(cleaned_price)
        
        assert cleaned_price == 15000.50
        assert is_valid is True
    
    def test_quantity_validation_with_clean_number(self):
        """Test integration between clean_number and is_valid_quantity."""
        # Clean and validate in sequence
        qty_str = "2.5k"
        cleaned_qty = clean_number(qty_str)
        is_valid = is_valid_quantity(cleaned_qty)
        
        assert cleaned_qty == 2500.0
        assert is_valid is True
    
    def test_date_parsing_edge_cases(self):
        """Test date parsing with various real-world scenarios."""
        # Test with different separators and formats that might come from OCR
        test_cases = [
            ("2025-05-28", date(2025, 5, 28)),
            ("28.05.2025", date(2025, 5, 28)),
            ("28/05/2025", date(2025, 5, 28)),
            ("28-05-2025", date(2025, 5, 28)),
            ("2025/05/28", date(2025, 5, 28)),
        ]
        
        for date_str, expected in test_cases:
            result = parse_date(date_str)
            assert result == expected, f"Failed for {date_str}"
    
    def test_number_cleaning_real_world_scenarios(self):
        """Test number cleaning with real-world OCR scenarios."""
        # Scenarios that might come from OCR
        test_cases = [
            ("15.000", 15000.0),  # Indonesian format
            ("15,000", 15000.0),  # US format with comma separator
            ("15 000", 15000.0),  # Space separator
            ("Rp15.000", 15000.0),  # Currency prefix
            ("15.000,-", 15000.0),  # Indonesian format with suffix
            ("USD 1,234.56", 1234.56),  # US currency
        ]
        
        for input_str, expected in test_cases:
            result = clean_number(input_str)
            assert result == expected, f"Failed for {input_str}"
    
    def test_validation_pipeline_simulation(self):
        """Simulate a complete validation pipeline using all utilities."""
        # Simulate OCR data that needs cleaning and validation
        raw_invoice_data = {
            "lines": [
                {
                    "qty": "2,5",  # European decimal format
                    "price": "Rp 15.000",  # Indonesian format
                    "amount": "37.500"  # Indonesian format
                },
                {
                    "qty": "1.0",
                    "price": "USD 25,000.00",  # US format
                    "amount": "25,000"
                }
            ],
            "invoice_date": "28.05.2025",
            "total_amount": "62.500"
        }
        
        # Clean and validate all numeric values
        for line in raw_invoice_data["lines"]:
            line["qty_clean"] = clean_number(line["qty"])
            line["price_clean"] = clean_number(line["price"])
            line["amount_clean"] = clean_number(line["amount"])
            
            line["qty_valid"] = is_valid_quantity(line["qty_clean"])
            line["price_valid"] = is_valid_price(line["price_clean"])
        
        # Parse date
        invoice_date = parse_date(raw_invoice_data["invoice_date"])
        
        # Verify results
        assert raw_invoice_data["lines"][0]["qty_clean"] == 2.5
        assert raw_invoice_data["lines"][0]["price_clean"] == 15000.0
        assert raw_invoice_data["lines"][0]["amount_clean"] == 37500.0
        assert raw_invoice_data["lines"][0]["qty_valid"] is True
        assert raw_invoice_data["lines"][0]["price_valid"] is True
        
        assert raw_invoice_data["lines"][1]["qty_clean"] == 1.0
        assert raw_invoice_data["lines"][1]["price_clean"] == 25000.0
        assert raw_invoice_data["lines"][1]["amount_clean"] == 25000.0
        assert raw_invoice_data["lines"][1]["qty_valid"] is True
        assert raw_invoice_data["lines"][1]["price_valid"] is True
        
        assert invoice_date == date(2025, 5, 28)


class TestDataUtilsErrorHandling:
    """Test error handling and edge cases for data utilities."""
    
    def test_clean_number_type_errors(self):
        """Test clean_number with unexpected types."""
        # Should handle gracefully
        assert clean_number([1, 2, 3]) == 0.0  # List
        assert clean_number({"value": 123}) == 0.0  # Dict
        assert clean_number(True) == 1.0  # Boolean True
        assert clean_number(False) == 0.0  # Boolean False
    
    def test_parse_date_type_errors(self):
        """Test parse_date with unexpected types."""
        # Should handle gracefully
        assert parse_date(123) is None  # Integer
        assert parse_date([2025, 5, 28]) is None  # List
        assert parse_date({"year": 2025, "month": 5, "day": 28}) is None  # Dict
    
    def test_validation_functions_type_errors(self):
        """Test validation functions with unexpected types."""
        # Should handle gracefully
        assert is_valid_price("not a number") is False
        assert is_valid_price([100]) is False
        assert is_valid_quantity("not a number") is False
        assert is_valid_quantity([5]) is False
    
    def test_extreme_values(self):
        """Test utilities with extreme values."""
        # Very large numbers
        large_num = 999999999999999999
        assert clean_number(str(large_num)) == float(large_num)
        
        # Very small numbers
        small_num = 0.000000001
        assert clean_number(str(small_num)) == small_num
        
        # Test validation with extreme values
        assert is_valid_price(large_num) is False  # Above reasonable max
        assert is_valid_price(small_num) is True  # Small but positive
        
        assert is_valid_quantity(large_num) is False  # Above reasonable max
        assert is_valid_quantity(small_num) is True  # Small but positive


if __name__ == "__main__":
    pytest.main([__file__])