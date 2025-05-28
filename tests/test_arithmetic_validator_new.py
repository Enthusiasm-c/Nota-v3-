"""
Comprehensive tests for the ArithmeticValidator class.
Tests all arithmetic validation functionality including auto-fixing.
"""

import pytest
from app.validators.arithmetic_validator import ArithmeticValidator


class TestArithmeticValidator:
    """Test suite for ArithmeticValidator."""
    
    def setup_method(self):
        """Set up test fixtures before each test method."""
        self.validator = ArithmeticValidator(tolerance=0.01, auto_fix=True)
        self.validator_no_fix = ArithmeticValidator(tolerance=0.01, auto_fix=False)
    
    def test_init_default_params(self):
        """Test ArithmeticValidator initialization with default parameters."""
        validator = ArithmeticValidator()
        assert validator.tolerance == 0.01
        assert validator.auto_fix is True
    
    def test_init_custom_params(self):
        """Test ArithmeticValidator initialization with custom parameters."""
        validator = ArithmeticValidator(tolerance=0.05, auto_fix=False)
        assert validator.tolerance == 0.05
        assert validator.auto_fix is False
    
    def test_validate_correct_arithmetic(self):
        """Test validation of invoice lines with correct arithmetic."""
        invoice_data = {
            "lines": [
                {"qty": 2, "price": 10.5, "amount": 21.0},
                {"qty": 1, "price": 100, "amount": 100},
                {"qty": 3.5, "price": 20, "amount": 70}
            ]
        }
        
        result = self.validator.validate(invoice_data)
        
        assert "lines" in result
        assert "issues" in result
        assert len(result["issues"]) == 0
        assert len(result["lines"]) == 3
    
    def test_validate_with_string_numbers(self):
        """Test validation with string numeric values."""
        invoice_data = {
            "lines": [
                {"qty": "2", "price": "10.5", "amount": "21.0"},
                {"qty": "3", "price": "15,50", "amount": "46.50"}
            ]
        }
        
        result = self.validator.validate(invoice_data)
        
        assert len(result["issues"]) == 0
        assert len(result["lines"]) == 2
    
    def test_validate_missing_amount_auto_fix(self):
        """Test auto-fixing missing amount calculation."""
        invoice_data = {
            "lines": [
                {"qty": 2, "price": 15.0, "amount": 0}  # Missing amount
            ]
        }
        
        result = self.validator.validate(invoice_data)
        
        assert len(result["issues"]) == 1
        assert result["issues"][0]["type"] == "ARITHMETIC_FIX"
        assert result["issues"][0]["field"] == "amount"
        assert result["lines"][0]["amount"] == 30.0
        assert "Fixed amount: 2.0 × 15.0 = 30.0" in result["issues"][0]["message"]
    
    def test_validate_missing_quantity_auto_fix(self):
        """Test auto-fixing missing quantity calculation."""
        invoice_data = {
            "lines": [
                {"qty": 0, "price": 15.0, "amount": 45.0}  # Missing quantity
            ]
        }
        
        result = self.validator.validate(invoice_data)
        
        assert len(result["issues"]) == 1
        assert result["issues"][0]["type"] == "ARITHMETIC_FIX"
        assert result["issues"][0]["field"] == "qty"
        assert result["lines"][0]["qty"] == 3.0
        assert "Fixed quantity: 45.0 ÷ 15.0 = 3.0" in result["issues"][0]["message"]
    
    def test_validate_missing_price_auto_fix(self):
        """Test auto-fixing missing price calculation."""
        invoice_data = {
            "lines": [
                {"qty": 3, "price": 0, "amount": 45.0}  # Missing price
            ]
        }
        
        result = self.validator.validate(invoice_data)
        
        assert len(result["issues"]) == 1
        assert result["issues"][0]["type"] == "ARITHMETIC_FIX"
        assert result["issues"][0]["field"] == "price"
        assert result["lines"][0]["price"] == 15.0
        assert "Fixed price: 45.0 ÷ 3.0 = 15.0" in result["issues"][0]["message"]
    
    def test_validate_decimal_errors_fix(self):
        """Test fixing decimal point errors."""
        invoice_data = {
            "lines": [
                {"qty": 2, "price": 150, "amount": 30.0}  # Price should be 15.0
            ]
        }
        
        result = self.validator.validate(invoice_data)
        
        # Should detect and fix decimal error
        assert len(result["issues"]) >= 1
        # Check that some arithmetic fix was applied
        fixed_issues = [issue for issue in result["issues"] if issue["type"] == "ARITHMETIC_FIX"]
        assert len(fixed_issues) >= 1
    
    def test_validate_zero_errors_fix(self):
        """Test fixing errors with missing or extra zeros."""
        invoice_data = {
            "lines": [
                {"qty": 2, "price": 1500, "amount": 30000}  # Price should be 15000
            ]
        }
        
        result = self.validator.validate(invoice_data)
        
        # Should detect and fix zero error
        assert len(result["issues"]) >= 1
        fixed_issues = [issue for issue in result["issues"] if issue["type"] == "ARITHMETIC_FIX"]
        assert len(fixed_issues) >= 1
    
    def test_validate_arithmetic_error_not_fixable(self):
        """Test arithmetic errors that cannot be automatically fixed."""
        invoice_data = {
            "lines": [
                {"qty": 2, "price": 10, "amount": 50}  # Error too large to fix
            ]
        }
        
        result = self.validator.validate(invoice_data)
        
        # Should report error but not fix it
        error_issues = [issue for issue in result["issues"] if issue["type"] == "ARITHMETIC_ERROR"]
        assert len(error_issues) >= 1
        assert "Calculation error" in error_issues[0]["message"]
    
    def test_validate_with_auto_fix_disabled(self):
        """Test validation with auto-fix disabled."""
        invoice_data = {
            "lines": [
                {"qty": 2, "price": 15.0, "amount": 0}  # Missing amount
            ]
        }
        
        result = self.validator_no_fix.validate(invoice_data)
        
        # Should detect issue but not fix it
        assert len(result["issues"]) >= 1
        assert result["lines"][0]["amount"] == 0  # Not fixed
    
    def test_validate_empty_lines(self):
        """Test validation with empty lines list."""
        invoice_data = {"lines": []}
        
        result = self.validator.validate(invoice_data)
        
        assert result["lines"] == []
        assert result["issues"] == []
    
    def test_validate_no_lines_key(self):
        """Test validation with missing lines key."""
        invoice_data = {}
        
        result = self.validator.validate(invoice_data)
        
        assert result.get("lines", []) == []
        assert result.get("issues", []) == []
    
    def test_validate_invalid_data_types(self):
        """Test validation with invalid data types."""
        invoice_data = {
            "lines": [
                {"qty": "invalid", "price": 15.0, "amount": 30.0},
                {"qty": None, "price": 15.0, "amount": 30.0}
            ]
        }
        
        result = self.validator.validate(invoice_data)
        
        # Should handle gracefully and continue processing
        assert "lines" in result
        assert "issues" in result
    
    def test_is_close_method(self):
        """Test the internal _is_close method indirectly."""
        # Test values within tolerance
        invoice_data = {
            "lines": [
                {"qty": 2, "price": 10.0, "amount": 20.1}  # 0.5% error (within 1% tolerance)
            ]
        }
        
        result = self.validator.validate(invoice_data)
        
        # Should pass without issues (within tolerance)
        arithmetic_errors = [issue for issue in result["issues"] if issue["type"] == "ARITHMETIC_ERROR"]
        assert len(arithmetic_errors) == 0
    
    def test_is_missing_or_zero_method(self):
        """Test handling of zero and missing values."""
        invoice_data = {
            "lines": [
                {"qty": 0, "price": 10.0, "amount": 0},
                {"qty": 2, "price": 0, "amount": 0},
                {"price": 10.0, "amount": 20.0}  # Missing qty
            ]
        }
        
        result = self.validator.validate(invoice_data)
        
        # Should handle zero values appropriately
        assert "lines" in result
        assert "issues" in result
    
    def test_validation_error_handling(self):
        """Test error handling during validation."""
        # Test with malformed line data
        invoice_data = {
            "lines": [
                {"qty": 2, "price": 10.0, "amount": 20.0},  # Valid line
                None,  # Invalid line
                {"qty": 2, "price": 10.0, "amount": 20.0}   # Valid line
            ]
        }
        
        result = self.validator.validate(invoice_data)
        
        # Should handle errors gracefully
        assert "lines" in result
        assert "issues" in result
    
    def test_complex_invoice_validation(self):
        """Test validation of a complex invoice with multiple line types."""
        invoice_data = {
            "lines": [
                {"qty": 2, "price": 10.0, "amount": 20.0},      # Perfect match
                {"qty": 3, "price": 15.5, "amount": 46.5},      # Perfect match
                {"qty": 1, "price": 25.0, "amount": 0},         # Missing amount (fixable)
                {"qty": 0, "price": 12.0, "amount": 36.0},      # Missing qty (fixable)
                {"qty": 2, "price": 0, "amount": 50.0},         # Missing price (fixable)
                {"qty": 2, "price": 10.0, "amount": 30.0},      # Arithmetic error (not fixable)
                {"qty": "2", "price": "15,50", "amount": "31"}, # String values
            ],
            "issues": []  # Start with empty issues
        }
        
        result = self.validator.validate(invoice_data)
        
        # Verify structure
        assert len(result["lines"]) == 7
        assert "issues" in result
        
        # Count different types of issues
        fix_issues = [issue for issue in result["issues"] if issue["type"] == "ARITHMETIC_FIX"]
        error_issues = [issue for issue in result["issues"] if issue["type"] == "ARITHMETIC_ERROR"]
        validation_errors = [issue for issue in result["issues"] if issue["type"] == "VALIDATION_ERROR"]
        
        # Should have multiple fixes and possibly some errors
        assert len(fix_issues) >= 2  # At least the missing amount and qty fixes
        
        # Verify that auto-fixes were applied
        assert result["lines"][2]["amount"] == 25.0  # Fixed missing amount
        assert result["lines"][3]["qty"] == 3.0      # Fixed missing qty
        assert result["lines"][4]["price"] == 25.0   # Fixed missing price


class TestArithmeticValidatorEdgeCases:
    """Test edge cases and boundary conditions for ArithmeticValidator."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.validator = ArithmeticValidator(tolerance=0.01, auto_fix=True)
    
    def test_very_small_numbers(self):
        """Test validation with very small numbers."""
        invoice_data = {
            "lines": [
                {"qty": 0.001, "price": 0.01, "amount": 0.00001}
            ]
        }
        
        result = self.validator.validate(invoice_data)
        
        # Should handle small numbers appropriately
        assert "lines" in result
        assert "issues" in result
    
    def test_very_large_numbers(self):
        """Test validation with very large numbers."""
        invoice_data = {
            "lines": [
                {"qty": 1000000, "price": 1000000, "amount": 1000000000000}
            ]
        }
        
        result = self.validator.validate(invoice_data)
        
        # Should handle large numbers appropriately
        assert "lines" in result
        assert "issues" in result
    
    def test_negative_numbers(self):
        """Test validation with negative numbers."""
        invoice_data = {
            "lines": [
                {"qty": -2, "price": 10.0, "amount": -20.0},
                {"qty": 2, "price": -10.0, "amount": -20.0}
            ]
        }
        
        result = self.validator.validate(invoice_data)
        
        # Should handle negative numbers
        assert "lines" in result
        assert "issues" in result
    
    def test_zero_tolerance(self):
        """Test validation with zero tolerance."""
        validator = ArithmeticValidator(tolerance=0.0, auto_fix=True)
        
        invoice_data = {
            "lines": [
                {"qty": 2, "price": 10.0, "amount": 20.01}  # Tiny error
            ]
        }
        
        result = validator.validate(invoice_data)
        
        # With zero tolerance, should flag even tiny errors
        error_issues = [issue for issue in result["issues"] 
                       if issue["type"] in ["ARITHMETIC_ERROR", "ARITHMETIC_FIX"]]
        assert len(error_issues) >= 1
    
    def test_high_tolerance(self):
        """Test validation with high tolerance."""
        validator = ArithmeticValidator(tolerance=0.1, auto_fix=True)  # 10% tolerance
        
        invoice_data = {
            "lines": [
                {"qty": 2, "price": 10.0, "amount": 21.0}  # 5% error
            ]
        }
        
        result = validator.validate(invoice_data)
        
        # With high tolerance, should pass
        error_issues = [issue for issue in result["issues"] if issue["type"] == "ARITHMETIC_ERROR"]
        assert len(error_issues) == 0


if __name__ == "__main__":
    pytest.main([__file__])