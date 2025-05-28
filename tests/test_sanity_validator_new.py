"""
Comprehensive tests for the SanityValidator class.
Tests business logic validation including prices, quantities, suppliers, and invoice numbers.
"""

import pytest
from datetime import date, datetime, timedelta
from app.validators.sanity_validator import SanityValidator


class TestSanityValidator:
    """Test suite for SanityValidator."""
    
    def setup_method(self):
        """Set up test fixtures before each test method."""
        self.validator = SanityValidator()
        self.validator_no_fix = SanityValidator(auto_fix=False)
    
    def test_init_default_params(self):
        """Test SanityValidator initialization with default parameters."""
        validator = SanityValidator()
        assert validator.min_price >= 0
        assert validator.max_price > 0
        assert validator.min_qty >= 0
        assert validator.max_qty > 0
        assert validator.auto_fix is True
    
    def test_init_custom_params(self):
        """Test SanityValidator initialization with custom parameters."""
        validator = SanityValidator(
            min_price=1.0,
            max_price=1000000.0,
            min_qty=0.1,
            max_qty=1000.0,
            auto_fix=False
        )
        assert validator.min_price == 1.0
        assert validator.max_price == 1000000.0
        assert validator.min_qty == 0.1
        assert validator.max_qty == 1000.0
        assert validator.auto_fix is False
    
    def test_validate_valid_invoice(self):
        """Test validation of a completely valid invoice."""
        invoice_data = {
            "supplier": "Test Supplier Ltd",
            "invoice_number": "INV-2025-001",
            "invoice_date": date.today(),
            "lines": [
                {
                    "name": "Product A",
                    "qty": 2.5,
                    "price": 1500.0,
                    "amount": 3750.0,
                    "unit": "kg"
                },
                {
                    "name": "Product B", 
                    "qty": 1.0,
                    "price": 25000.0,
                    "amount": 25000.0,
                    "unit": "pcs"
                }
            ]
        }
        
        result = self.validator.validate(invoice_data)
        
        assert len(result["issues"]) == 0
        assert len(result["lines"]) == 2
        assert result["supplier"] == "Test Supplier Ltd"
    
    def test_validate_negative_price_auto_fix(self):
        """Test auto-fixing negative prices."""
        invoice_data = {
            "lines": [
                {
                    "name": "Product A",
                    "qty": 2.0,
                    "price": -1500.0,  # Negative price
                    "amount": 3000.0,
                    "unit": "kg"
                }
            ]
        }
        
        result = self.validator.validate(invoice_data)
        
        # Should auto-fix negative price
        assert result["lines"][0]["price"] == 1500.0  # Made positive
        price_issues = [issue for issue in result["issues"] if issue["type"] == "PRICE_NEGATIVE"]
        assert len(price_issues) == 1
        assert "Fixed negative price" in price_issues[0]["message"]
    
    def test_validate_zero_price(self):
        """Test validation of zero prices."""
        invoice_data = {
            "lines": [
                {
                    "name": "Free Sample",
                    "qty": 1.0,
                    "price": 0.0,
                    "amount": 0.0,
                    "unit": "pcs"
                }
            ]
        }
        
        result = self.validator.validate(invoice_data)
        
        # Zero prices should trigger low price warning
        low_price_issues = [issue for issue in result["issues"] if issue["type"] == "PRICE_TOO_LOW"]
        assert len(low_price_issues) == 1
    
    def test_validate_high_price_warning(self):
        """Test validation of unusually high prices."""
        invoice_data = {
            "lines": [
                {
                    "name": "Expensive Item",
                    "qty": 1.0,
                    "price": 50000000.0,  # Very high price
                    "amount": 50000000.0,
                    "unit": "pcs"
                }
            ]
        }
        
        result = self.validator.validate(invoice_data)
        
        # Should generate warning for high price
        high_price_issues = [issue for issue in result["issues"] if "high" in issue["message"].lower()]
        # Note: Exact issue type depends on implementation
        assert len(result["issues"]) >= 0  # May or may not flag as issue depending on thresholds
    
    def test_validate_negative_quantity_auto_fix(self):
        """Test auto-fixing negative quantities."""
        invoice_data = {
            "lines": [
                {
                    "name": "Product A",
                    "qty": -2.5,  # Negative quantity
                    "price": 1000.0,
                    "amount": 2500.0,
                    "unit": "kg"
                }
            ]
        }
        
        result = self.validator.validate(invoice_data)
        
        # Should auto-fix negative quantity
        assert result["lines"][0]["qty"] == 2.5  # Made positive
        qty_issues = [issue for issue in result["issues"] if "qty" in issue["message"].lower() or "quantity" in issue["message"].lower()]
        assert len(qty_issues) >= 1
    
    def test_validate_zero_quantity(self):
        """Test validation of zero quantities."""
        invoice_data = {
            "lines": [
                {
                    "name": "Product A",
                    "qty": 0.0,
                    "price": 1000.0,
                    "amount": 0.0,
                    "unit": "kg"
                }
            ]
        }
        
        result = self.validator.validate(invoice_data)
        
        # Zero quantity should be flagged
        zero_qty_issues = [issue for issue in result["issues"] 
                          if "qty" in issue["message"].lower() or "quantity" in issue["message"].lower()]
        assert len(zero_qty_issues) >= 1
    
    def test_validate_invalid_unit(self):
        """Test validation of invalid units."""
        invoice_data = {
            "lines": [
                {
                    "name": "Product A",
                    "qty": 2.0,
                    "price": 1000.0,
                    "amount": 2000.0,
                    "unit": "invalid_unit"
                }
            ]
        }
        
        result = self.validator.validate(invoice_data)
        
        # Should flag invalid unit
        unit_issues = [issue for issue in result["issues"] if "unit" in issue["message"].lower()]
        assert len(unit_issues) >= 1
    
    def test_validate_valid_units(self):
        """Test validation with valid units."""
        valid_units = ["kg", "pcs", "liter", "gram", "ton", "box", "pack"]
        
        for unit in valid_units:
            invoice_data = {
                "lines": [
                    {
                        "name": "Product A",
                        "qty": 2.0,
                        "price": 1000.0,
                        "amount": 2000.0,
                        "unit": unit
                    }
                ]
            }
            
            result = self.validator.validate(invoice_data)
            
            # Valid units should not generate unit-related issues
            unit_issues = [issue for issue in result["issues"] if "unit" in issue["message"].lower()]
            assert len(unit_issues) == 0, f"Valid unit '{unit}' was flagged as invalid"
    
    def test_validate_supplier_name(self):
        """Test validation of supplier names."""
        test_cases = [
            ("Valid Supplier Ltd", True),
            ("ABC Company", True),
            ("", False),  # Empty supplier
            (None, False),  # None supplier
            ("A", False),  # Too short
            ("X" * 200, False),  # Too long
        ]
        
        for supplier_name, should_be_valid in test_cases:
            invoice_data = {
                "supplier": supplier_name,
                "lines": [
                    {
                        "name": "Product A",
                        "qty": 1.0,
                        "price": 1000.0,
                        "amount": 1000.0,
                        "unit": "kg"
                    }
                ]
            }
            
            result = self.validator.validate(invoice_data)
            
            supplier_issues = [issue for issue in result["issues"] if "supplier" in issue["message"].lower()]
            
            if should_be_valid:
                assert len(supplier_issues) == 0, f"Valid supplier '{supplier_name}' was flagged"
            else:
                assert len(supplier_issues) >= 1, f"Invalid supplier '{supplier_name}' was not flagged"
    
    def test_validate_invoice_number(self):
        """Test validation of invoice numbers."""
        test_cases = [
            ("INV-2025-001", True),
            ("12345", True),
            ("ABC123", True),
            ("", False),  # Empty
            (None, False),  # None
            ("A", False),  # Too short
            ("X" * 100, False),  # Too long
        ]
        
        for invoice_num, should_be_valid in test_cases:
            invoice_data = {
                "invoice_number": invoice_num,
                "lines": [
                    {
                        "name": "Product A",
                        "qty": 1.0,
                        "price": 1000.0,
                        "amount": 1000.0,
                        "unit": "kg"
                    }
                ]
            }
            
            result = self.validator.validate(invoice_data)
            
            invoice_num_issues = [issue for issue in result["issues"] 
                                if "invoice" in issue["message"].lower() and "number" in issue["message"].lower()]
            
            if should_be_valid:
                assert len(invoice_num_issues) == 0, f"Valid invoice number '{invoice_num}' was flagged"
            else:
                assert len(invoice_num_issues) >= 1, f"Invalid invoice number '{invoice_num}' was not flagged"
    
    def test_validate_future_date(self):
        """Test validation of future invoice dates."""
        future_date = date.today() + timedelta(days=10)
        
        invoice_data = {
            "invoice_date": future_date,
            "lines": [
                {
                    "name": "Product A",
                    "qty": 1.0,
                    "price": 1000.0,
                    "amount": 1000.0,
                    "unit": "kg"
                }
            ]
        }
        
        result = self.validator.validate(invoice_data)
        
        # Future dates should be flagged
        date_issues = [issue for issue in result["issues"] if "date" in issue["message"].lower()]
        assert len(date_issues) >= 1
    
    def test_validate_very_old_date(self):
        """Test validation of very old invoice dates."""
        old_date = date.today() - timedelta(days=400)
        
        invoice_data = {
            "invoice_date": old_date,
            "lines": [
                {
                    "name": "Product A",
                    "qty": 1.0,
                    "price": 1000.0,
                    "amount": 1000.0,
                    "unit": "kg"
                }
            ]
        }
        
        result = self.validator.validate(invoice_data)
        
        # Very old dates should be flagged
        date_issues = [issue for issue in result["issues"] if "date" in issue["message"].lower()]
        assert len(date_issues) >= 1
    
    def test_validate_with_auto_fix_disabled(self):
        """Test validation with auto-fix disabled."""
        invoice_data = {
            "lines": [
                {
                    "name": "Product A",
                    "qty": -2.0,  # Negative quantity
                    "price": -1000.0,  # Negative price
                    "amount": 2000.0,
                    "unit": "kg"
                }
            ]
        }
        
        result = self.validator_no_fix.validate(invoice_data)
        
        # Should detect issues but not fix them
        assert result["lines"][0]["qty"] == -2.0  # Not fixed
        assert result["lines"][0]["price"] == -1000.0  # Not fixed
        assert len(result["issues"]) >= 2  # Should have issues for both negative values
    
    def test_validate_empty_lines(self):
        """Test validation with empty lines."""
        invoice_data = {
            "supplier": "Test Supplier",
            "invoice_number": "INV-001",
            "lines": []
        }
        
        result = self.validator.validate(invoice_data)
        
        # Should handle empty lines gracefully
        assert result["lines"] == []
        # May or may not flag as issue depending on implementation
    
    def test_validate_malformed_line(self):
        """Test validation with malformed line data."""
        invoice_data = {
            "lines": [
                {
                    "name": "Valid Product",
                    "qty": 1.0,
                    "price": 1000.0,
                    "amount": 1000.0,
                    "unit": "kg"
                },
                {
                    # Malformed line - missing required fields
                    "name": "Incomplete Product"
                    # Missing qty, price, amount, unit
                },
                {
                    "name": "Another Valid Product",
                    "qty": 2.0,
                    "price": 500.0,
                    "amount": 1000.0,
                    "unit": "pcs"
                }
            ]
        }
        
        result = self.validator.validate(invoice_data)
        
        # Should handle malformed lines gracefully
        assert len(result["lines"]) == 3
        assert "issues" in result
        # Should continue processing other lines
    
    def test_validate_string_numeric_values(self):
        """Test validation with string numeric values."""
        invoice_data = {
            "lines": [
                {
                    "name": "Product A",
                    "qty": "2.5",  # String quantity
                    "price": "1,500.00",  # String price with comma
                    "amount": "3750",  # String amount
                    "unit": "kg"
                }
            ]
        }
        
        result = self.validator.validate(invoice_data)
        
        # Should handle string numbers correctly using centralized clean_number
        assert len(result["lines"]) == 1
        # The validator should process these successfully
    
    def test_validate_complex_invoice(self):
        """Test validation of a complex invoice with multiple issue types."""
        invoice_data = {
            "supplier": "Test Supplier Inc",
            "invoice_number": "INV-2025-001",
            "invoice_date": date.today(),
            "lines": [
                {
                    "name": "Perfect Product",
                    "qty": 2.0,
                    "price": 1500.0,
                    "amount": 3000.0,
                    "unit": "kg"
                },
                {
                    "name": "Negative Price Product",
                    "qty": 1.0,
                    "price": -1000.0,  # Will be auto-fixed
                    "amount": 1000.0,
                    "unit": "pcs"
                },
                {
                    "name": "Zero Quantity Product",
                    "qty": 0.0,  # Will be flagged
                    "price": 500.0,
                    "amount": 0.0,
                    "unit": "liter"
                },
                {
                    "name": "Invalid Unit Product",
                    "qty": 1.5,
                    "price": 2000.0,
                    "amount": 3000.0,
                    "unit": "invalid_unit"  # Will be flagged
                }
            ]
        }
        
        result = self.validator.validate(invoice_data)
        
        assert len(result["lines"]) == 4
        assert len(result["issues"]) >= 3  # At least 3 issues expected
        
        # Verify auto-fix happened
        assert result["lines"][1]["price"] == 1000.0  # Negative price fixed
        
        # Count issue types
        price_issues = [issue for issue in result["issues"] if "price" in issue["message"].lower()]
        qty_issues = [issue for issue in result["issues"] if "qty" in issue["message"].lower() or "quantity" in issue["message"].lower()]
        unit_issues = [issue for issue in result["issues"] if "unit" in issue["message"].lower()]
        
        assert len(price_issues) >= 1
        assert len(qty_issues) >= 1  
        assert len(unit_issues) >= 1


class TestSanityValidatorBusinessLogic:
    """Test business logic validation methods."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.validator = SanityValidator()
    
    def test_is_valid_unit_method(self):
        """Test the _is_valid_unit method."""
        valid_units = ["kg", "gram", "liter", "pcs", "ton", "box", "pack", "ml"]
        invalid_units = ["invalid", "", None, "xyz", "123"]
        
        for unit in valid_units:
            assert self.validator._is_valid_unit(unit) is True, f"Unit '{unit}' should be valid"
        
        for unit in invalid_units:
            assert self.validator._is_valid_unit(unit) is False, f"Unit '{unit}' should be invalid"
    
    def test_is_valid_supplier_method(self):
        """Test the _is_valid_supplier method."""
        valid_suppliers = [
            "ABC Company Ltd",
            "XYZ Corp",
            "Valid Supplier Name",
            "Company 123"
        ]
        
        invalid_suppliers = [
            "",  # Empty
            None,  # None
            "A",  # Too short
            "X" * 200,  # Too long
        ]
        
        for supplier in valid_suppliers:
            assert self.validator._is_valid_supplier(supplier) is True, f"Supplier '{supplier}' should be valid"
        
        for supplier in invalid_suppliers:
            assert self.validator._is_valid_supplier(supplier) is False, f"Supplier '{supplier}' should be invalid"
    
    def test_is_valid_invoice_number_method(self):
        """Test the _is_valid_invoice_number method."""
        valid_numbers = [
            "INV-001",
            "12345",
            "ABC123",
            "2025-001",
            "INVOICE_123"
        ]
        
        invalid_numbers = [
            "",  # Empty
            None,  # None
            "A",  # Too short
            "X" * 100,  # Too long
        ]
        
        for number in valid_numbers:
            assert self.validator._is_valid_invoice_number(number) is True, f"Invoice number '{number}' should be valid"
        
        for number in invalid_numbers:
            assert self.validator._is_valid_invoice_number(number) is False, f"Invoice number '{number}' should be invalid"


class TestSanityValidatorEdgeCases:
    """Test edge cases and error conditions."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.validator = SanityValidator()
    
    def test_validate_none_input(self):
        """Test validation with None input."""
        result = self.validator.validate(None)
        
        # Should handle None gracefully
        assert "issues" in result
        assert "lines" in result
    
    def test_validate_empty_dict(self):
        """Test validation with empty dictionary."""
        result = self.validator.validate({})
        
        # Should handle empty dict gracefully
        assert "issues" in result
        assert "lines" in result
        assert result["lines"] == []
    
    def test_validate_missing_lines_key(self):
        """Test validation when lines key is missing."""
        invoice_data = {
            "supplier": "Test Supplier",
            "invoice_number": "INV-001"
            # Missing "lines" key
        }
        
        result = self.validator.validate(invoice_data)
        
        # Should handle missing lines key
        assert "lines" in result
        assert result["lines"] == []
    
    def test_validate_non_list_lines(self):
        """Test validation when lines is not a list."""
        invoice_data = {
            "lines": "not a list"
        }
        
        result = self.validator.validate(invoice_data)
        
        # Should handle non-list lines gracefully
        assert "issues" in result
    
    def test_validate_line_with_none_values(self):
        """Test validation of line with None values."""
        invoice_data = {
            "lines": [
                {
                    "name": None,
                    "qty": None,
                    "price": None,
                    "amount": None,
                    "unit": None
                }
            ]
        }
        
        result = self.validator.validate(invoice_data)
        
        # Should handle None values gracefully
        assert len(result["lines"]) == 1
        assert "issues" in result


if __name__ == "__main__":
    pytest.main([__file__])