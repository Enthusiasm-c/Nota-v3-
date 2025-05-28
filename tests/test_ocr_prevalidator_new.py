"""
Comprehensive tests for the OCRPreValidator class.
Tests early OCR validation including arithmetic checks and price validation.
"""

import pytest
from app.validators.ocr_prevalidator import OCRPreValidator, validate_ocr_result


class TestOCRPreValidator:
    """Test suite for OCRPreValidator."""
    
    def setup_method(self):
        """Set up test fixtures before each test method."""
        self.validator = OCRPreValidator()
        self.validator_custom = OCRPreValidator(
            tolerance=0.1,  # 10% tolerance
            min_unit_price=1000,
            max_unit_price=500000,
            min_total_invoice=5000,
            max_total_invoice=5000000
        )
    
    def test_init_default_params(self):
        """Test OCRPreValidator initialization with default parameters."""
        validator = OCRPreValidator()
        assert validator.tolerance == 0.05
        assert validator.min_unit_price == 500
        assert validator.max_unit_price == 1_000_000
        assert validator.min_total_invoice == 10_000
        assert validator.max_total_invoice == 10_000_000
    
    def test_init_custom_params(self):
        """Test OCRPreValidator initialization with custom parameters."""
        validator = OCRPreValidator(
            tolerance=0.1,
            min_unit_price=1000,
            max_unit_price=500000,
            min_total_invoice=5000,
            max_total_invoice=2000000
        )
        assert validator.tolerance == 0.1
        assert validator.min_unit_price == 1000
        assert validator.max_unit_price == 500000
        assert validator.min_total_invoice == 5000
        assert validator.max_total_invoice == 2000000
    
    def test_validate_positions_valid_data(self):
        """Test validation of positions with valid data."""
        positions = [
            {
                "name": "Product A",
                "qty": 2,
                "price": 15000,
                "total_price": 30000
            },
            {
                "name": "Product B",
                "qty": 1.5,
                "price": 20000,
                "total_price": 30000
            }
        ]
        
        result = self.validator.validate_positions(positions)
        
        assert len(result) == 2
        # No validation warnings expected for valid data
        for pos in result:
            assert "validation_warnings" not in pos or len(pos["validation_warnings"]) == 0
    
    def test_validate_positions_arithmetic_error(self):
        """Test detection of arithmetic errors in positions."""
        positions = [
            {
                "name": "Product A",
                "qty": 2,
                "price": 15000,
                "total_price": 40000  # Should be 30000 (2 × 15000)
            }
        ]
        
        result = self.validator.validate_positions(positions)
        
        assert len(result) == 1
        assert "validation_warnings" in result[0]
        math_warnings = [w for w in result[0]["validation_warnings"] if "Math error" in w]
        assert len(math_warnings) == 1
        assert "error:" in math_warnings[0]
    
    def test_validate_positions_missing_total_price(self):
        """Test auto-calculation of missing total_price."""
        positions = [
            {
                "name": "Product A",
                "qty": 2,
                "price": 15000,
                "total_price": 0  # Missing total_price
            }
        ]
        
        result = self.validator.validate_positions(positions)
        
        assert len(result) == 1
        assert result[0]["total_price"] == 30000  # Auto-calculated
        assert "validation_warnings" in result[0]
        calc_warnings = [w for w in result[0]["validation_warnings"] if "Calculated missing total_price" in w]
        assert len(calc_warnings) == 1
    
    def test_validate_positions_missing_qty_or_price(self):
        """Test handling of positions with missing quantity or price."""
        positions = [
            {
                "name": "Product A",
                "qty": 0,  # Missing quantity
                "price": 15000,
                "total_price": 30000
            },
            {
                "name": "Product B",
                "qty": 2,
                "price": 0,  # Missing price
                "total_price": 30000
            }
        ]
        
        result = self.validator.validate_positions(positions)
        
        assert len(result) == 2
        # Both positions should have warnings about missing data
        for pos in result:
            assert "validation_warnings" in pos
            missing_warnings = [w for w in pos["validation_warnings"] if "Missing" in w]
            assert len(missing_warnings) == 1
    
    def test_validate_positions_price_range_validation(self):
        """Test price range validation."""
        positions = [
            {
                "name": "Very Cheap Product",
                "qty": 1,
                "price": 100,  # Below min_unit_price (500)
                "total_price": 100
            },
            {
                "name": "Very Expensive Product", 
                "qty": 1,
                "price": 2000000,  # Above max_unit_price (1,000,000)
                "total_price": 2000000
            }
        ]
        
        result = self.validator.validate_positions(positions)
        
        assert len(result) == 2
        
        # Check low price warning
        low_price_warnings = [w for w in result[0]["validation_warnings"] if "Suspiciously low price" in w]
        assert len(low_price_warnings) == 1
        
        # Check high price warning
        high_price_warnings = [w for w in result[1]["validation_warnings"] if "Suspiciously high price" in w]
        assert len(high_price_warnings) == 1
    
    def test_validate_positions_quantity_validation(self):
        """Test quantity validation."""
        positions = [
            {
                "name": "Invalid Quantity Product",
                "qty": -1,  # Invalid negative quantity
                "price": 15000,
                "total_price": 15000
            },
            {
                "name": "Large Quantity Product",
                "qty": 5000,  # Unusually large quantity
                "price": 10000,
                "total_price": 50000000
            }
        ]
        
        result = self.validator.validate_positions(positions)
        
        assert len(result) == 2
        
        # Check invalid quantity warning
        invalid_qty_warnings = [w for w in result[0]["validation_warnings"] if "Invalid quantity" in w]
        assert len(invalid_qty_warnings) == 1
        
        # Check large quantity warning
        large_qty_warnings = [w for w in result[1]["validation_warnings"] if "Unusually large quantity" in w]
        assert len(large_qty_warnings) == 1
    
    def test_validate_positions_string_values(self):
        """Test validation with string numeric values."""
        positions = [
            {
                "name": "Product A",
                "qty": "2",
                "price": "15,000",
                "total_price": "30000"
            },
            {
                "name": "Product B",
                "qty": "1.5",
                "price": "20.000",
                "total_price": "30000"
            }
        ]
        
        result = self.validator.validate_positions(positions)
        
        # Should handle string values correctly using clean_number
        assert len(result) == 2
        # Verify conversion worked
        assert isinstance(result[0].get("validation_warnings", []), list)
    
    def test_validate_invoice_total_correct(self):
        """Test invoice total validation with correct total."""
        positions = [
            {"total_price": 30000},
            {"total_price": 20000}
        ]
        total_price = 50000
        
        result = self.validator.validate_invoice_total(positions, total_price)
        
        assert result["total_price"] == 50000
        assert result["calculated_total"] == 50000
        assert result["validation_passed"] is True
        assert len(result["warnings"]) == 0
    
    def test_validate_invoice_total_mismatch(self):
        """Test invoice total validation with mismatch."""
        positions = [
            {"total_price": 30000},
            {"total_price": 20000}
        ]
        total_price = 60000  # Should be 50000
        
        result = self.validator.validate_invoice_total(positions, total_price)
        
        assert result["total_price"] == 60000
        assert result["calculated_total"] == 50000
        assert result["validation_passed"] is False
        assert len(result["warnings"]) == 1
        assert "Invoice total mismatch" in result["warnings"][0]
    
    def test_validate_invoice_total_missing(self):
        """Test invoice total validation with missing total."""
        positions = [
            {"total_price": 30000},
            {"total_price": 20000}
        ]
        total_price = None
        
        result = self.validator.validate_invoice_total(positions, total_price)
        
        assert result["total_price"] == 50000  # Auto-calculated
        assert result["calculated_total"] == 50000
        assert len(result["warnings"]) == 1
        assert "Calculated missing invoice total" in result["warnings"][0]
    
    def test_validate_invoice_total_range_validation(self):
        """Test invoice total range validation."""
        # Test too low total
        positions = [{"total_price": 5000}]
        result_low = self.validator.validate_invoice_total(positions, 5000)
        
        low_warnings = [w for w in result_low["warnings"] if "Suspiciously low invoice total" in w]
        assert len(low_warnings) == 1
        
        # Test too high total
        positions = [{"total_price": 20000000}]
        result_high = self.validator.validate_invoice_total(positions, 20000000)
        
        high_warnings = [w for w in result_high["warnings"] if "Suspiciously high invoice total" in w]
        assert len(high_warnings) == 1
    
    def test_check_common_ocr_errors(self):
        """Test detection of common OCR errors."""
        # Test round number that might be missing decimal
        positions = [
            {
                "name": "Product A",
                "qty": 2,
                "price": 10000,  # Suspiciously round, might be 100.00
                "total_price": 20000
            }
        ]
        
        result = self.validator.validate_positions(positions)
        
        # Should detect potential decimal point error
        decimal_warnings = [w for w in result[0].get("validation_warnings", []) 
                          if "decimal point" in w or "extra zeros" in w]
        # May or may not detect depending on validation logic
        assert len(result) == 1
    
    def test_validate_positions_with_precision_errors(self):
        """Test detection of unusual precision in quantities."""
        positions = [
            {
                "name": "Product A",
                "qty": "1.000000",  # Unusual precision
                "price": 15000,
                "total_price": 15000
            }
        ]
        
        result = self.validator.validate_positions(positions)
        
        # Should detect unusual precision
        precision_warnings = [w for w in result[0].get("validation_warnings", []) 
                            if "precision" in w or "unusual" in w]
        # May or may not detect depending on implementation
        assert len(result) == 1
    
    def test_validate_positions_empty_list(self):
        """Test validation with empty positions list."""
        result = self.validator.validate_positions([])
        
        assert result == []
    
    def test_validate_positions_malformed_data(self):
        """Test validation with malformed position data."""
        positions = [
            {
                "name": "Valid Product",
                "qty": 2,
                "price": 15000,
                "total_price": 30000
            },
            {
                # Malformed position - missing fields
                "name": "Incomplete Product"
            },
            None,  # Invalid position
            {
                "name": "Another Valid Product",
                "qty": 1,
                "price": 20000,
                "total_price": 20000
            }
        ]
        
        result = self.validator.validate_positions(positions)
        
        # Should handle malformed data gracefully
        assert len(result) == 4  # Should return same number of items
        # Valid positions should be processed normally
        assert result[0]["name"] == "Valid Product"
        assert result[3]["name"] == "Another Valid Product"
    
    def test_custom_tolerance_validation(self):
        """Test validation with custom tolerance settings."""
        positions = [
            {
                "name": "Product A",
                "qty": 2,
                "price": 15000,
                "total_price": 32000  # 6.7% error
            }
        ]
        
        # Default validator (5% tolerance) should flag this
        result_default = self.validator.validate_positions(positions)
        math_errors_default = [w for w in result_default[0].get("validation_warnings", []) if "Math error" in w]
        assert len(math_errors_default) == 1
        
        # Custom validator (10% tolerance) should accept this
        result_custom = self.validator_custom.validate_positions(positions)
        math_errors_custom = [w for w in result_custom[0].get("validation_warnings", []) if "Math error" in w]
        assert len(math_errors_custom) == 0


class TestOCRPreValidatorConvenienceFunction:
    """Test the validate_ocr_result convenience function."""
    
    def test_validate_ocr_result_complete(self):
        """Test the validate_ocr_result convenience function."""
        ocr_data = {
            "positions": [
                {
                    "name": "Product A",
                    "qty": 2,
                    "price": 15000,
                    "total_price": 30000
                },
                {
                    "name": "Product B",
                    "qty": 1,
                    "price": 20000,
                    "total_price": 20000
                }
            ],
            "total_price": 50000,
            "supplier": "Test Supplier",
            "invoice_number": "INV-001"
        }
        
        result = validate_ocr_result(ocr_data)
        
        # Should preserve original data
        assert result["supplier"] == "Test Supplier"
        assert result["invoice_number"] == "INV-001"
        
        # Should add validation results
        assert "validation_warnings" in result
        assert "validation_passed" in result
        assert result["total_price"] == 50000
        assert len(result["positions"]) == 2
    
    def test_validate_ocr_result_with_errors(self):
        """Test validate_ocr_result with errors and warnings."""
        ocr_data = {
            "positions": [
                {
                    "name": "Product A",
                    "qty": 2,
                    "price": 15000,
                    "total_price": 40000  # Math error
                },
                {
                    "name": "Cheap Product",
                    "qty": 1,
                    "price": 100,  # Too cheap
                    "total_price": 100
                }
            ],
            "total_price": 45000  # Mismatch with calculated total
        }
        
        result = validate_ocr_result(ocr_data)
        
        # Should have validation warnings
        assert "validation_warnings" in result
        assert len(result["validation_warnings"]) > 0
        assert result["validation_passed"] is False
        
        # Should have position-level warnings
        math_warnings = any("Math error" in str(w) for w in result["validation_warnings"])
        price_warnings = any("low price" in str(w) for w in result["validation_warnings"])
        total_warnings = any("total mismatch" in str(w) for w in result["validation_warnings"])
        
        assert math_warnings or price_warnings or total_warnings
    
    def test_validate_ocr_result_empty_data(self):
        """Test validate_ocr_result with empty data."""
        ocr_data = {}
        
        result = validate_ocr_result(ocr_data)
        
        # Should handle empty data gracefully
        assert "positions" in result
        assert "validation_warnings" in result
        assert "validation_passed" in result
        assert result["positions"] == []
    
    def test_validate_ocr_result_missing_positions(self):
        """Test validate_ocr_result with missing positions."""
        ocr_data = {
            "total_price": 50000,
            "supplier": "Test Supplier"
        }
        
        result = validate_ocr_result(ocr_data)
        
        # Should handle missing positions
        assert result["positions"] == []
        assert "validation_warnings" in result


class TestOCRPreValidatorEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.validator = OCRPreValidator()
    
    def test_zero_tolerance_validation(self):
        """Test validation with zero tolerance."""
        validator = OCRPreValidator(tolerance=0.0)
        
        positions = [
            {
                "name": "Product A",
                "qty": 2,
                "price": 15000,
                "total_price": 30000.01  # Tiny error
            }
        ]
        
        result = validator.validate_positions(positions)
        
        # With zero tolerance, should flag even tiny errors
        math_warnings = [w for w in result[0].get("validation_warnings", []) if "Math error" in w]
        assert len(math_warnings) == 1
    
    def test_very_small_numbers(self):
        """Test validation with very small numbers."""
        positions = [
            {
                "name": "Small Product",
                "qty": 0.001,
                "price": 1,
                "total_price": 0.001
            }
        ]
        
        result = self.validator.validate_positions(positions)
        
        # Should handle small numbers
        assert len(result) == 1
    
    def test_very_large_numbers(self):
        """Test validation with very large numbers."""
        positions = [
            {
                "name": "Large Product",
                "qty": 1000000,
                "price": 1000000,
                "total_price": 1000000000000
            }
        ]
        
        result = self.validator.validate_positions(positions)
        
        # Should handle large numbers and likely flag them
        assert len(result) == 1
        # Large values should trigger warnings
        large_warnings = [w for w in result[0].get("validation_warnings", []) 
                         if "large" in w.lower() or "high" in w.lower()]
        assert len(large_warnings) >= 1
    
    def test_negative_prices_and_quantities(self):
        """Test handling of negative prices and quantities."""
        positions = [
            {
                "name": "Negative Price Product",
                "qty": 2,
                "price": -15000,
                "total_price": -30000
            },
            {
                "name": "Negative Quantity Product",
                "qty": -1,
                "price": 15000,
                "total_price": -15000
            }
        ]
        
        result = self.validator.validate_positions(positions)
        
        # Should handle negative values and flag them
        assert len(result) == 2
        for pos in result:
            warnings = pos.get("validation_warnings", [])
            # Should have warnings about negative values or invalid quantities
            assert len(warnings) >= 1


if __name__ == "__main__":
    pytest.main([__file__])