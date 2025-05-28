"""
Comprehensive tests for the Syrve handler module.
Tests invoice processing, validation, and API integration.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from datetime import date, datetime
from app.handlers.syrve_handler import (
    validate_and_send_to_syrve,
    format_syrve_payload,
    handle_syrve_confirmation,
    process_invoice_for_syrve
)


class TestSyrveHandler:
    """Test suite for Syrve handler functions."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.sample_invoice = {
            "supplier": "Test Supplier Ltd",
            "invoice_number": "INV-2025-001",
            "invoice_date": date.today(),
            "lines": [
                {
                    "name": "Product A",
                    "qty": 2.0,
                    "price": 15000.0,
                    "amount": 30000.0,
                    "unit": "kg"
                },
                {
                    "name": "Product B",
                    "qty": 1.0,
                    "price": 25000.0,
                    "amount": 25000.0,
                    "unit": "pcs"
                }
            ],
            "total_amount": 55000.0
        }
        
        self.sample_message = Mock()
        self.sample_message.from_user.id = 12345
        self.sample_message.chat.id = 67890
        self.sample_message.reply = AsyncMock()
        
        self.sample_bot = Mock()
        self.sample_bot.send_message = AsyncMock()
        self.sample_bot.edit_message_text = AsyncMock()
    
    @pytest.mark.asyncio
    async def test_validate_and_send_to_syrve_valid_invoice(self):
        """Test validation and sending of a valid invoice."""
        with patch('app.handlers.syrve_handler.validate_invoice_for_syrve') as mock_validate, \
             patch('app.handlers.syrve_handler.send_to_syrve_api') as mock_send:
            
            # Mock validation success
            mock_validate.return_value = {
                "valid": True,
                "issues": [],
                "invoice": self.sample_invoice
            }
            
            # Mock API success
            mock_send.return_value = {
                "success": True,
                "syrve_id": "SYR-12345",
                "message": "Invoice sent successfully"
            }
            
            result = await validate_and_send_to_syrve(
                self.sample_invoice,
                self.sample_message,
                self.sample_bot
            )
            
            assert result["success"] is True
            assert result["syrve_id"] == "SYR-12345"
            mock_validate.assert_called_once()
            mock_send.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_validate_and_send_to_syrve_validation_failure(self):
        """Test handling of validation failures."""
        with patch('app.handlers.syrve_handler.validate_invoice_for_syrve') as mock_validate:
            
            # Mock validation failure
            mock_validate.return_value = {
                "valid": False,
                "issues": [
                    {"type": "ARITHMETIC_ERROR", "message": "Math error in line 1"},
                    {"type": "DATE_INVALID", "message": "Invalid invoice date"}
                ],
                "invoice": self.sample_invoice
            }
            
            result = await validate_and_send_to_syrve(
                self.sample_invoice,
                self.sample_message,
                self.sample_bot
            )
            
            assert result["success"] is False
            assert "validation_errors" in result
            assert len(result["validation_errors"]) == 2
            
            # Should send error message to user
            self.sample_bot.send_message.assert_called()
            call_args = self.sample_bot.send_message.call_args[1]
            assert "validation" in call_args["text"].lower()
    
    @pytest.mark.asyncio
    async def test_validate_and_send_to_syrve_api_failure(self):
        """Test handling of Syrve API failures."""
        with patch('app.handlers.syrve_handler.validate_invoice_for_syrve') as mock_validate, \
             patch('app.handlers.syrve_handler.send_to_syrve_api') as mock_send:
            
            # Mock validation success
            mock_validate.return_value = {
                "valid": True,
                "issues": [],
                "invoice": self.sample_invoice
            }
            
            # Mock API failure
            mock_send.return_value = {
                "success": False,
                "error": "Connection timeout",
                "message": "Failed to connect to Syrve API"
            }
            
            result = await validate_and_send_to_syrve(
                self.sample_invoice,
                self.sample_message,
                self.sample_bot
            )
            
            assert result["success"] is False
            assert "error" in result
            
            # Should send error message to user
            self.sample_bot.send_message.assert_called()
            call_args = self.sample_bot.send_message.call_args[1]
            assert "error" in call_args["text"].lower() or "failed" in call_args["text"].lower()
    
    def test_format_syrve_payload_basic(self):
        """Test basic Syrve payload formatting."""
        payload = format_syrve_payload(self.sample_invoice)
        
        # Check required fields
        assert "supplier" in payload
        assert "invoice_number" in payload
        assert "invoice_date" in payload
        assert "lines" in payload
        assert "total_amount" in payload
        
        # Check data integrity
        assert payload["supplier"] == "Test Supplier Ltd"
        assert payload["invoice_number"] == "INV-2025-001"
        assert len(payload["lines"]) == 2
        assert payload["total_amount"] == 55000.0
    
    def test_format_syrve_payload_date_formatting(self):
        """Test date formatting in Syrve payload."""
        # Test with date object
        invoice_with_date = self.sample_invoice.copy()
        invoice_with_date["invoice_date"] = date(2025, 5, 28)
        
        payload = format_syrve_payload(invoice_with_date)
        
        # Date should be formatted as string
        assert isinstance(payload["invoice_date"], str)
        assert payload["invoice_date"] == "2025-05-28"
        
        # Test with datetime object
        invoice_with_datetime = self.sample_invoice.copy()
        invoice_with_datetime["invoice_date"] = datetime(2025, 5, 28, 10, 30)
        
        payload = format_syrve_payload(invoice_with_datetime)
        assert payload["invoice_date"] == "2025-05-28"
    
    def test_format_syrve_payload_line_processing(self):
        """Test line item processing in Syrve payload."""
        payload = format_syrve_payload(self.sample_invoice)
        
        lines = payload["lines"]
        assert len(lines) == 2
        
        # Check first line
        line1 = lines[0]
        assert line1["name"] == "Product A"
        assert line1["quantity"] == 2.0
        assert line1["unit_price"] == 15000.0
        assert line1["total_price"] == 30000.0
        assert line1["unit"] == "kg"
        
        # Check second line
        line2 = lines[1]
        assert line2["name"] == "Product B"
        assert line2["quantity"] == 1.0
        assert line2["unit_price"] == 25000.0
        assert line2["total_price"] == 25000.0
        assert line2["unit"] == "pcs"
    
    def test_format_syrve_payload_missing_fields(self):
        """Test payload formatting with missing fields."""
        incomplete_invoice = {
            "supplier": "Test Supplier",
            "lines": [
                {
                    "name": "Product A",
                    "qty": 1.0,
                    "price": 10000.0
                    # Missing amount and unit
                }
            ]
            # Missing invoice_number, date, total_amount
        }
        
        payload = format_syrve_payload(incomplete_invoice)
        
        # Should handle missing fields gracefully
        assert "supplier" in payload
        assert "lines" in payload
        
        # Missing fields should have default values or be None
        assert payload.get("invoice_number") is None or payload.get("invoice_number") == ""
        assert payload.get("total_amount") == 0 or payload.get("total_amount") is None
    
    def test_format_syrve_payload_numeric_conversion(self):
        """Test numeric value conversion in payload."""
        invoice_with_strings = {
            "supplier": "Test Supplier",
            "total_amount": "55000.0",  # String amount
            "lines": [
                {
                    "name": "Product A",
                    "qty": "2.0",  # String quantity
                    "price": "15,000.0",  # String price with comma
                    "amount": "30000"  # String amount
                }
            ]
        }
        
        payload = format_syrve_payload(invoice_with_strings)
        
        # Should convert strings to numbers
        assert isinstance(payload["total_amount"], (int, float))
        
        line = payload["lines"][0]
        assert isinstance(line["quantity"], (int, float))
        assert isinstance(line["unit_price"], (int, float))
        assert isinstance(line["total_price"], (int, float))
    
    @pytest.mark.asyncio
    async def test_handle_syrve_confirmation_success(self):
        """Test handling of successful Syrve confirmation."""
        confirmation_data = {
            "success": True,
            "syrve_id": "SYR-12345",
            "message": "Invoice processed successfully"
        }
        
        result = await handle_syrve_confirmation(
            confirmation_data,
            self.sample_message,
            self.sample_bot
        )
        
        assert result["success"] is True
        
        # Should send success message to user
        self.sample_bot.send_message.assert_called()
        call_args = self.sample_bot.send_message.call_args[1]
        assert "success" in call_args["text"].lower() or "sent" in call_args["text"].lower()
        assert "SYR-12345" in call_args["text"]
    
    @pytest.mark.asyncio
    async def test_handle_syrve_confirmation_failure(self):
        """Test handling of failed Syrve confirmation."""
        confirmation_data = {
            "success": False,
            "error": "Invalid supplier ID",
            "message": "Supplier not found in Syrve system"
        }
        
        result = await handle_syrve_confirmation(
            confirmation_data,
            self.sample_message,
            self.sample_bot
        )
        
        assert result["success"] is False
        
        # Should send error message to user
        self.sample_bot.send_message.assert_called()
        call_args = self.sample_bot.send_message.call_args[1]
        assert "error" in call_args["text"].lower() or "failed" in call_args["text"].lower()
    
    @pytest.mark.asyncio
    async def test_process_invoice_for_syrve_complete_flow(self):
        """Test complete invoice processing flow."""
        with patch('app.handlers.syrve_handler.validate_invoice_data') as mock_validate, \
             patch('app.handlers.syrve_handler.apply_business_rules') as mock_rules, \
             patch('app.handlers.syrve_handler.map_to_syrve_format') as mock_map:
            
            # Mock validation
            mock_validate.return_value = {
                "valid": True,
                "issues": [],
                "data": self.sample_invoice
            }
            
            # Mock business rules
            mock_rules.return_value = self.sample_invoice
            
            # Mock format mapping
            mock_map.return_value = {
                "supplier_id": "SUPP-001",
                "invoice_number": "INV-2025-001",
                "lines": [
                    {"product_id": "PROD-A", "quantity": 2.0, "price": 15000.0}
                ]
            }
            
            result = await process_invoice_for_syrve(self.sample_invoice)
            
            assert result["success"] is True
            assert "syrve_payload" in result
            
            # All processing steps should be called
            mock_validate.assert_called_once()
            mock_rules.assert_called_once()
            mock_map.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_process_invoice_for_syrve_validation_error(self):
        """Test invoice processing with validation errors."""
        with patch('app.handlers.syrve_handler.validate_invoice_data') as mock_validate:
            
            # Mock validation failure
            mock_validate.return_value = {
                "valid": False,
                "issues": [
                    {"type": "REQUIRED_FIELD", "message": "Missing supplier name"}
                ],
                "data": self.sample_invoice
            }
            
            result = await process_invoice_for_syrve(self.sample_invoice)
            
            assert result["success"] is False
            assert "validation_errors" in result
            assert len(result["validation_errors"]) == 1


class TestSyrveHandlerValidation:
    """Test validation logic in Syrve handler."""
    
    def test_validate_invoice_for_syrve_complete_invoice(self):
        """Test validation of complete invoice."""
        complete_invoice = {
            "supplier": "Complete Supplier Ltd",
            "invoice_number": "INV-2025-001",
            "invoice_date": date.today(),
            "lines": [
                {
                    "name": "Product A",
                    "qty": 2.0,
                    "price": 15000.0,
                    "amount": 30000.0,
                    "unit": "kg"
                }
            ],
            "total_amount": 30000.0
        }
        
        with patch('app.handlers.syrve_handler.ArithmeticValidator') as mock_arithmetic, \
             patch('app.handlers.syrve_handler.DateValidator') as mock_date, \
             patch('app.handlers.syrve_handler.SanityValidator') as mock_sanity:
            
            # Mock validators
            mock_arithmetic.return_value.validate.return_value = {
                "issues": [],
                "lines": complete_invoice["lines"]
            }
            mock_date.return_value.validate_invoice_date.return_value = {
                "valid": True,
                "issues": []
            }
            mock_sanity.return_value.validate.return_value = {
                "issues": [],
                "lines": complete_invoice["lines"]
            }
            
            result = validate_invoice_for_syrve(complete_invoice)
            
            assert result["valid"] is True
            assert len(result["issues"]) == 0
    
    def test_validate_invoice_for_syrve_missing_required_fields(self):
        """Test validation of invoice with missing required fields."""
        incomplete_invoice = {
            "lines": [
                {
                    "name": "Product A",
                    "qty": 2.0,
                    "price": 15000.0
                }
            ]
            # Missing supplier, invoice_number, date
        }
        
        result = validate_invoice_for_syrve(incomplete_invoice)
        
        assert result["valid"] is False
        assert len(result["issues"]) > 0
        
        # Should have issues for missing fields
        missing_supplier = any("supplier" in issue["message"].lower() for issue in result["issues"])
        missing_number = any("invoice" in issue["message"].lower() and "number" in issue["message"].lower() for issue in result["issues"])
        
        assert missing_supplier or missing_number
    
    def test_validate_invoice_for_syrve_arithmetic_errors(self):
        """Test validation with arithmetic errors."""
        invoice_with_errors = {
            "supplier": "Test Supplier",
            "invoice_number": "INV-001",
            "invoice_date": date.today(),
            "lines": [
                {
                    "name": "Product A",
                    "qty": 2.0,
                    "price": 15000.0,
                    "amount": 40000.0  # Arithmetic error: should be 30000
                }
            ]
        }
        
        with patch('app.handlers.syrve_handler.ArithmeticValidator') as mock_arithmetic:
            
            # Mock arithmetic validation failure
            mock_arithmetic.return_value.validate.return_value = {
                "issues": [
                    {"type": "ARITHMETIC_ERROR", "message": "Calculation error in line 1"}
                ],
                "lines": invoice_with_errors["lines"]
            }
            
            result = validate_invoice_for_syrve(invoice_with_errors)
            
            assert result["valid"] is False
            assert len(result["issues"]) >= 1
            arithmetic_errors = [issue for issue in result["issues"] if issue["type"] == "ARITHMETIC_ERROR"]
            assert len(arithmetic_errors) >= 1


class TestSyrveHandlerErrorHandling:
    """Test error handling in Syrve handler."""
    
    @pytest.mark.asyncio
    async def test_network_error_handling(self):
        """Test handling of network errors during API calls."""
        with patch('app.handlers.syrve_handler.send_to_syrve_api') as mock_send:
            
            # Mock network error
            mock_send.side_effect = ConnectionError("Network unreachable")
            
            result = await validate_and_send_to_syrve(
                {"supplier": "Test"},
                Mock(),
                Mock()
            )
            
            assert result["success"] is False
            assert "error" in result
            assert "network" in result["error"].lower() or "connection" in result["error"].lower()
    
    @pytest.mark.asyncio
    async def test_timeout_error_handling(self):
        """Test handling of timeout errors."""
        with patch('app.handlers.syrve_handler.send_to_syrve_api') as mock_send:
            
            # Mock timeout error
            mock_send.side_effect = TimeoutError("Request timed out")
            
            result = await validate_and_send_to_syrve(
                {"supplier": "Test"},
                Mock(),
                Mock()
            )
            
            assert result["success"] is False
            assert "error" in result
            assert "timeout" in result["error"].lower()
    
    @pytest.mark.asyncio
    async def test_malformed_response_handling(self):
        """Test handling of malformed API responses."""
        with patch('app.handlers.syrve_handler.send_to_syrve_api') as mock_send:
            
            # Mock malformed response
            mock_send.return_value = "not a dictionary"
            
            result = await validate_and_send_to_syrve(
                {"supplier": "Test"},
                Mock(),
                Mock()
            )
            
            assert result["success"] is False
            assert "error" in result
    
    def test_invalid_invoice_data_handling(self):
        """Test handling of invalid invoice data types."""
        invalid_data_types = [
            None,
            "not a dictionary",
            [],
            123
        ]
        
        for invalid_data in invalid_data_types:
            result = validate_invoice_for_syrve(invalid_data)
            
            assert result["valid"] is False
            assert len(result["issues"]) >= 1


class TestSyrveHandlerIntegration:
    """Integration tests for Syrve handler components."""
    
    @pytest.mark.asyncio
    async def test_end_to_end_success_flow(self):
        """Test complete end-to-end success flow."""
        invoice = {
            "supplier": "Integration Test Supplier",
            "invoice_number": "INT-001",
            "invoice_date": date.today(),
            "lines": [
                {
                    "name": "Test Product",
                    "qty": 1.0,
                    "price": 10000.0,
                    "amount": 10000.0,
                    "unit": "pcs"
                }
            ],
            "total_amount": 10000.0
        }
        
        message = Mock()
        message.from_user.id = 12345
        message.chat.id = 67890
        message.reply = AsyncMock()
        
        bot = Mock()
        bot.send_message = AsyncMock()
        
        with patch('app.handlers.syrve_handler.validate_invoice_for_syrve') as mock_validate, \
             patch('app.handlers.syrve_handler.send_to_syrve_api') as mock_send:
            
            # Mock successful validation
            mock_validate.return_value = {
                "valid": True,
                "issues": [],
                "invoice": invoice
            }
            
            # Mock successful API call
            mock_send.return_value = {
                "success": True,
                "syrve_id": "SYR-INT-001",
                "message": "Invoice processed successfully"
            }
            
            result = await validate_and_send_to_syrve(invoice, message, bot)
            
            assert result["success"] is True
            assert result["syrve_id"] == "SYR-INT-001"
            
            # Should send success confirmation to user
            bot.send_message.assert_called()
    
    @pytest.mark.asyncio
    async def test_end_to_end_validation_failure_flow(self):
        """Test complete end-to-end validation failure flow."""
        invalid_invoice = {
            "lines": [
                {
                    "name": "Invalid Product",
                    "qty": -1.0,  # Invalid quantity
                    "price": -5000.0,  # Invalid price
                    "amount": 5000.0
                }
            ]
            # Missing required fields
        }
        
        message = Mock()
        message.from_user.id = 12345
        message.chat.id = 67890
        
        bot = Mock()
        bot.send_message = AsyncMock()
        
        result = await validate_and_send_to_syrve(invalid_invoice, message, bot)
        
        assert result["success"] is False
        assert "validation_errors" in result
        
        # Should send error message to user
        bot.send_message.assert_called()
        call_args = bot.send_message.call_args[1]
        assert "error" in call_args["text"].lower() or "invalid" in call_args["text"].lower()


if __name__ == "__main__":
    pytest.main([__file__])