"""
Comprehensive tests for the DateValidator class.
Tests date validation, extraction, and business logic validation.
"""

import pytest
from datetime import date, datetime, timedelta
from app.validators.date_validator import DateValidator


class TestDateValidator:
    """Test suite for DateValidator."""
    
    def setup_method(self):
        """Set up test fixtures before each test method."""
        self.validator = DateValidator()
    
    def test_init_default_params(self):
        """Test DateValidator initialization with default parameters."""
        validator = DateValidator()
        assert validator.max_future_days == 7
        assert validator.max_past_days == 365
        assert validator.auto_fix == True
    
    def test_init_custom_params(self):
        """Test DateValidator initialization with custom parameters."""
        validator = DateValidator(max_future_days=3, max_past_days=180, auto_fix=False)
        assert validator.max_future_days == 3
        assert validator.max_past_days == 180
        assert validator.auto_fix is False
    
    def test_validate_invoice_date_with_valid_date(self):
        """Test validation with valid invoice date."""
        today = date.today()
        invoice_data = {
            "invoice_date": today.strftime("%Y-%m-%d")
        }
        
        result = self.validator.validate_invoice_date(invoice_data)
        
        assert result["valid"] is True
        assert result["date"] == today
        assert len(result["issues"]) == 0
    
    def test_validate_invoice_date_with_datetime_object(self):
        """Test validation with datetime object."""
        now = datetime.now()
        invoice_data = {
            "invoice_date": now
        }
        
        result = self.validator.validate_invoice_date(invoice_data)
        
        assert result["valid"] is True
        assert result["date"] == now.date()
        assert len(result["issues"]) == 0
    
    def test_validate_invoice_date_with_date_object(self):
        """Test validation with date object."""
        today = date.today()
        invoice_data = {
            "invoice_date": today
        }
        
        result = self.validator.validate_invoice_date(invoice_data)
        
        assert result["valid"] is True
        assert result["date"] == today
        assert len(result["issues"]) == 0
    
    def test_validate_invoice_date_missing(self):
        """Test validation with missing invoice date."""
        invoice_data = {}
        
        result = self.validator.validate_invoice_date(invoice_data)
        
        assert result["valid"] is False
        assert result["date"] is None
        assert len(result["issues"]) == 1
        assert result["issues"][0]["type"] == "DATE_MISSING"
    
    def test_validate_invoice_date_invalid_format(self):
        """Test validation with invalid date format."""
        invoice_data = {
            "invoice_date": "invalid-date"
        }
        
        result = self.validator.validate_invoice_date(invoice_data)
        
        assert result["valid"] is False
        assert result["date"] is None
        assert len(result["issues"]) == 1
        assert result["issues"][0]["type"] == "DATE_PARSE_ERROR"
    
    def test_validate_invoice_date_future_warning(self):
        """Test validation with future date (within allowed range)."""
        future_date = date.today() + timedelta(days=5)
        invoice_data = {
            "invoice_date": future_date.strftime("%Y-%m-%d")
        }
        
        result = self.validator.validate_invoice_date(invoice_data)
        
        assert result["valid"] is True
        assert result["date"] == future_date
        assert len(result["issues"]) == 1
        assert result["issues"][0]["type"] == "DATE_FUTURE_WARNING"
        assert result["issues"][0]["severity"] == "warning"
    
    def test_validate_invoice_date_too_far_future(self):
        """Test validation with date too far in the future."""
        future_date = date.today() + timedelta(days=30)
        invoice_data = {
            "invoice_date": future_date.strftime("%Y-%m-%d")
        }
        
        result = self.validator.validate_invoice_date(invoice_data)
        
        assert result["valid"] is False
        assert result["date"] == future_date
        assert len(result["issues"]) == 1
        assert result["issues"][0]["type"] == "DATE_TOO_FAR_FUTURE"
        assert result["issues"][0]["severity"] == "error"
    
    def test_validate_invoice_date_too_far_past(self):
        """Test validation with date too far in the past."""
        past_date = date.today() - timedelta(days=400)
        invoice_data = {
            "invoice_date": past_date.strftime("%Y-%m-%d")
        }
        
        result = self.validator.validate_invoice_date(invoice_data)
        
        assert result["valid"] is False
        assert result["date"] == past_date
        assert len(result["issues"]) == 1
        assert result["issues"][0]["type"] == "DATE_TOO_FAR_PAST"
        assert result["issues"][0]["severity"] == "error"
    
    def test_extract_date_from_invoice_top_level(self):
        """Test date extraction from top-level invoice fields."""
        invoice_data = {
            "date": "2025-05-28",
            "invoice_date": "2025-05-29",
            "created_date": "2025-05-30"
        }
        
        extracted_date = self.validator._extract_date_from_invoice(invoice_data)
        
        # Should prefer invoice_date over other fields
        assert extracted_date == date(2025, 5, 29)
    
    def test_extract_date_from_invoice_positions(self):
        """Test date extraction from positions when top-level fields missing."""
        invoice_data = {
            "lines": [
                {"name": "Item 1", "qty": 2},
                {"name": "Item 2", "date": "2025-05-28", "qty": 1}
            ]
        }
        
        extracted_date = self.validator._extract_date_from_invoice(invoice_data)
        
        assert extracted_date == date(2025, 5, 28)
    
    def test_extract_date_from_invoice_no_date(self):
        """Test date extraction when no date is found."""
        invoice_data = {
            "supplier": "Test Supplier",
            "lines": [
                {"name": "Item 1", "qty": 2, "price": 10}
            ]
        }
        
        extracted_date = self.validator._extract_date_from_invoice(invoice_data)
        
        assert extracted_date is None
    
    def test_validate_date_range_valid_range(self):
        """Test date range validation for valid dates."""
        today = date.today()
        
        result = self.validator._validate_date_range(today)
        
        assert result["valid"] is True
        assert len(result["issues"]) == 0
    
    def test_validate_date_range_weekend_warning(self):
        """Test weekend date warning."""
        # Find next Saturday
        today = date.today()
        days_ahead = 5 - today.weekday()  # Saturday is 5
        if days_ahead <= 0:
            days_ahead += 7
        saturday = today + timedelta(days=days_ahead)
        
        result = self.validator._validate_date_range(saturday)
        
        # Should be valid but with weekend warning
        assert result["valid"] is True
        weekend_warnings = [issue for issue in result["issues"] if issue["type"] == "DATE_WEEKEND_WARNING"]
        assert len(weekend_warnings) == 1
    
    def test_validate_date_range_suspicious_old(self):
        """Test suspicious old date detection."""
        old_date = date.today() - timedelta(days=180)
        
        result = self.validator._validate_date_range(old_date)
        
        assert result["valid"] is True
        suspicious_warnings = [issue for issue in result["issues"] if issue["type"] == "DATE_SUSPICIOUS_OLD"]
        assert len(suspicious_warnings) == 1
    
    def test_validate_invoice_dates_multiple_formats(self):
        """Test validation with various date formats."""
        test_cases = [
            ("2025-05-28", date(2025, 5, 28)),
            ("28/05/2025", date(2025, 5, 28)),
            ("28.05.2025", date(2025, 5, 28)),
            ("28-05-2025", date(2025, 5, 28)),
        ]
        
        for date_str, expected_date in test_cases:
            invoice_data = {"invoice_date": date_str}
            result = self.validator.validate_invoice_date(invoice_data)
            
            assert result["valid"] is True, f"Failed for format: {date_str}"
            assert result["date"] == expected_date, f"Wrong date for format: {date_str}"
    
    def test_validate_invoice_dates_function(self):
        """Test the validate_invoice_dates function."""
        invoice_data = {
            "invoice_date": date.today().strftime("%Y-%m-%d"),
            "lines": [
                {"name": "Item 1", "qty": 2, "price": 10}
            ]
        }
        
        result = self.validator.validate_invoice_dates(invoice_data)
        
        assert "date_validation" in result
        assert result["date_validation"]["valid"] is True
        assert result["date_validation"]["date"] == date.today()
    
    def test_auto_fix_disabled(self):
        """Test validation with auto-fix disabled."""
        validator = DateValidator(auto_fix=False)
        future_date = date.today() + timedelta(days=30)
        
        invoice_data = {
            "invoice_date": future_date.strftime("%Y-%m-%d")
        }
        
        result = validator.validate_invoice_date(invoice_data)
        
        # Should detect error but not suggest fixes
        assert result["valid"] is False
        assert result["date"] == future_date


class TestDateValidatorEdgeCases:
    """Test edge cases and boundary conditions for DateValidator."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.validator = DateValidator()
    
    def test_leap_year_date(self):
        """Test validation with leap year date."""
        leap_year_date = date(2024, 2, 29)  # 2024 is a leap year
        invoice_data = {
            "invoice_date": leap_year_date
        }
        
        result = self.validator.validate_invoice_date(invoice_data)
        
        assert result["valid"] is True
        assert result["date"] == leap_year_date
    
    def test_year_boundary_dates(self):
        """Test validation with year boundary dates."""
        test_dates = [
            date(2024, 12, 31),  # New Year's Eve
            date(2025, 1, 1),    # New Year's Day
        ]
        
        for test_date in test_dates:
            invoice_data = {"invoice_date": test_date}
            result = self.validator.validate_invoice_date(invoice_data)
            
            # Should handle year boundaries correctly
            assert result["date"] == test_date
    
    def test_month_boundary_dates(self):
        """Test validation with month boundary dates."""
        test_dates = [
            date(2025, 1, 31),   # End of January
            date(2025, 2, 1),    # Start of February
            date(2025, 2, 28),   # End of February (non-leap year)
        ]
        
        for test_date in test_dates:
            invoice_data = {"invoice_date": test_date}
            result = self.validator.validate_invoice_date(invoice_data)
            
            assert result["date"] == test_date
    
    def test_ambiguous_date_formats(self):
        """Test handling of ambiguous date formats."""
        # Test cases where day/month could be swapped
        test_cases = [
            ("01/02/2025", date(2025, 2, 1)),   # Assumes DD/MM/YYYY
            ("13/02/2025", date(2025, 2, 13)),  # Unambiguous (13 > 12)
        ]
        
        for date_str, expected_date in test_cases:
            invoice_data = {"invoice_date": date_str}
            result = self.validator.validate_invoice_date(invoice_data)
            
            # Should parse according to expected format
            assert result["date"] == expected_date, f"Failed for: {date_str}"
    
    def test_malformed_date_strings(self):
        """Test handling of malformed date strings."""
        malformed_dates = [
            "2025-13-01",     # Invalid month
            "2025-02-30",     # Invalid day for February
            "2025/02/30",     # Invalid day with different separator
            "32/01/2025",     # Invalid day
            "01/13/2025",     # Could be invalid month in DD/MM format
            "",               # Empty string
            "not-a-date",     # Completely invalid
            "2025",           # Incomplete
            "05/2025",        # Missing day
        ]
        
        for malformed_date in malformed_dates:
            invoice_data = {"invoice_date": malformed_date}
            result = self.validator.validate_invoice_date(invoice_data)
            
            # Should handle gracefully and return parse error
            assert result["valid"] is False
            assert result["date"] is None
            parse_errors = [issue for issue in result["issues"] if issue["type"] == "DATE_PARSE_ERROR"]
            assert len(parse_errors) == 1, f"Failed to detect parse error for: {malformed_date}"
    
    def test_extreme_date_values(self):
        """Test validation with extreme date values."""
        # Test very old dates
        old_date = date(1900, 1, 1)
        invoice_data = {"invoice_date": old_date}
        result = self.validator.validate_invoice_date(invoice_data)
        
        assert result["valid"] is False
        assert result["date"] == old_date
        past_errors = [issue for issue in result["issues"] if issue["type"] == "DATE_TOO_FAR_PAST"]
        assert len(past_errors) == 1
        
        # Test very future dates
        future_date = date(2100, 12, 31)
        invoice_data = {"invoice_date": future_date}
        result = self.validator.validate_invoice_date(invoice_data)
        
        assert result["valid"] is False
        assert result["date"] == future_date
        future_errors = [issue for issue in result["issues"] if issue["type"] == "DATE_TOO_FAR_FUTURE"]
        assert len(future_errors) == 1
    
    def test_timezone_handling(self):
        """Test handling of timezone-aware datetime objects."""
        # Note: This assumes the system handles timezone-naive datetime
        # In a real system, you might want to handle timezones explicitly
        now_naive = datetime.now()
        
        invoice_data = {"invoice_date": now_naive}
        result = self.validator.validate_invoice_date(invoice_data)
        
        assert result["valid"] is True
        assert result["date"] == now_naive.date()
    
    def test_custom_date_field_names(self):
        """Test extraction from custom date field names."""
        # Test with various field names that might contain dates
        invoice_data = {
            "created_at": "2025-05-28",
            "timestamp": "2025-05-29",
            "date_issued": "2025-05-30",
            "lines": []
        }
        
        # The current implementation should find one of these dates
        extracted_date = self.validator._extract_date_from_invoice(invoice_data)
        
        # Should find at least one date
        assert extracted_date is not None
        assert isinstance(extracted_date, date)


class TestDateValidatorIntegration:
    """Integration tests for DateValidator with other components."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.validator = DateValidator()
    
    def test_integration_with_parse_date_utility(self):
        """Test integration with the centralized parse_date utility."""
        # This test verifies that the DateValidator correctly uses
        # the centralized parse_date function from data_utils
        
        invoice_data = {
            "invoice_date": "28.05.2025"  # European format
        }
        
        result = self.validator.validate_invoice_date(invoice_data)
        
        assert result["valid"] is True
        assert result["date"] == date(2025, 5, 28)
    
    def test_full_invoice_validation_workflow(self):
        """Test complete date validation workflow."""
        # Simulate a complete invoice validation scenario
        invoice_data = {
            "supplier": "Test Supplier",
            "invoice_number": "INV-001",
            "invoice_date": date.today().strftime("%Y-%m-%d"),
            "lines": [
                {"name": "Item 1", "qty": 2, "price": 10.0, "amount": 20.0},
                {"name": "Item 2", "qty": 1, "price": 15.0, "amount": 15.0}
            ]
        }
        
        # Validate dates
        result = self.validator.validate_invoice_dates(invoice_data)
        
        # Should preserve all original data while adding validation results
        assert "supplier" in result
        assert "invoice_number" in result
        assert "lines" in result
        assert len(result["lines"]) == 2
        
        # Should add date validation results
        assert "date_validation" in result
        assert result["date_validation"]["valid"] is True
        assert result["date_validation"]["date"] == date.today()


if __name__ == "__main__":
    pytest.main([__file__])