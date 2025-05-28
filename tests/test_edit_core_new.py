"""
Comprehensive tests for the edit_core handler module.
Tests invoice editing functionality and user interaction handling.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from datetime import date
from app.handlers.edit_core import (
    handle_edit_request,
    process_field_edit,
    apply_edit_changes,
    validate_edit_input,
    format_edit_response
)


class TestEditCore:
    """Test suite for edit core functionality."""
    
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
        self.sample_message.text = "edit supplier Test New Supplier"
        self.sample_message.reply = AsyncMock()
        
        self.sample_bot = Mock()
        self.sample_bot.send_message = AsyncMock()
        self.sample_bot.edit_message_text = AsyncMock()
    
    @pytest.mark.asyncio
    async def test_handle_edit_request_supplier(self):
        """Test handling of supplier edit request."""
        edit_command = "edit supplier New Supplier Name"
        
        with patch('app.handlers.edit_core.get_current_invoice') as mock_get, \
             patch('app.handlers.edit_core.save_invoice') as mock_save:
            
            mock_get.return_value = self.sample_invoice
            
            result = await handle_edit_request(
                edit_command,
                self.sample_message,
                self.sample_bot
            )
            
            assert result["success"] is True
            assert result["field"] == "supplier"
            assert result["old_value"] == "Test Supplier Ltd"
            assert result["new_value"] == "New Supplier Name"
            
            # Should save the updated invoice
            mock_save.assert_called_once()
            saved_invoice = mock_save.call_args[0][0]
            assert saved_invoice["supplier"] == "New Supplier Name"
    
    @pytest.mark.asyncio
    async def test_handle_edit_request_line_item(self):
        """Test handling of line item edit request."""
        edit_command = "edit line 1 qty 3.0"
        
        with patch('app.handlers.edit_core.get_current_invoice') as mock_get, \
             patch('app.handlers.edit_core.save_invoice') as mock_save:
            
            mock_get.return_value = self.sample_invoice
            
            result = await handle_edit_request(
                edit_command,
                self.sample_message,
                self.sample_bot
            )
            
            assert result["success"] is True
            assert result["field"] == "qty"
            assert result["line_index"] == 0  # 1-based to 0-based conversion
            assert result["old_value"] == 2.0
            assert result["new_value"] == 3.0
            
            # Should save the updated invoice
            mock_save.assert_called_once()
            saved_invoice = mock_save.call_args[0][0]
            assert saved_invoice["lines"][0]["qty"] == 3.0
    
    @pytest.mark.asyncio
    async def test_handle_edit_request_price(self):
        """Test handling of price edit request."""
        edit_command = "edit line 1 price 20000"
        
        with patch('app.handlers.edit_core.get_current_invoice') as mock_get, \
             patch('app.handlers.edit_core.save_invoice') as mock_save, \
             patch('app.handlers.edit_core.recalculate_amounts') as mock_recalc:
            
            mock_get.return_value = self.sample_invoice
            mock_recalc.return_value = self.sample_invoice  # Return modified invoice
            
            result = await handle_edit_request(
                edit_command,
                self.sample_message,
                self.sample_bot
            )
            
            assert result["success"] is True
            assert result["field"] == "price"
            assert result["old_value"] == 15000.0
            assert result["new_value"] == 20000.0
            
            # Should trigger recalculation
            mock_recalc.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_handle_edit_request_invalid_command(self):
        """Test handling of invalid edit command."""
        invalid_commands = [
            "edit",  # Missing parameters
            "edit invalid_field value",  # Invalid field
            "edit line 999 qty 1.0",  # Line doesn't exist
            "edit line abc qty 1.0",  # Invalid line number
        ]
        
        for invalid_command in invalid_commands:
            result = await handle_edit_request(
                invalid_command,
                self.sample_message,
                self.sample_bot
            )
            
            assert result["success"] is False, f"Command '{invalid_command}' should be invalid"
            assert "error" in result
    
    def test_process_field_edit_supplier(self):
        """Test processing supplier field edit."""
        result = process_field_edit(
            self.sample_invoice,
            "supplier",
            "New Supplier Name"
        )
        
        assert result["success"] is True
        assert result["old_value"] == "Test Supplier Ltd"
        assert result["new_value"] == "New Supplier Name"
        assert result["invoice"]["supplier"] == "New Supplier Name"
    
    def test_process_field_edit_invoice_number(self):
        """Test processing invoice number field edit."""
        result = process_field_edit(
            self.sample_invoice,
            "invoice_number",
            "INV-2025-NEW"
        )
        
        assert result["success"] is True
        assert result["old_value"] == "INV-2025-001"
        assert result["new_value"] == "INV-2025-NEW"
        assert result["invoice"]["invoice_number"] == "INV-2025-NEW"
    
    def test_process_field_edit_date(self):
        """Test processing date field edit."""
        result = process_field_edit(
            self.sample_invoice,
            "date",
            "2025-06-01"
        )
        
        assert result["success"] is True
        assert result["new_value"] == date(2025, 6, 1)
        assert result["invoice"]["invoice_date"] == date(2025, 6, 1)
    
    def test_process_field_edit_line_quantity(self):
        """Test processing line quantity edit."""
        result = process_field_edit(
            self.sample_invoice,
            "qty",
            "3.5",
            line_index=0
        )
        
        assert result["success"] is True
        assert result["old_value"] == 2.0
        assert result["new_value"] == 3.5
        assert result["invoice"]["lines"][0]["qty"] == 3.5
    
    def test_process_field_edit_line_price(self):
        """Test processing line price edit."""
        result = process_field_edit(
            self.sample_invoice,
            "price",
            "18000.50",
            line_index=1
        )
        
        assert result["success"] is True
        assert result["old_value"] == 25000.0
        assert result["new_value"] == 18000.50
        assert result["invoice"]["lines"][1]["price"] == 18000.50
    
    def test_process_field_edit_line_name(self):
        """Test processing line name edit."""
        result = process_field_edit(
            self.sample_invoice,
            "name",
            "New Product Name",
            line_index=0
        )
        
        assert result["success"] is True
        assert result["old_value"] == "Product A"
        assert result["new_value"] == "New Product Name"
        assert result["invoice"]["lines"][0]["name"] == "New Product Name"
    
    def test_process_field_edit_invalid_field(self):
        """Test processing invalid field edit."""
        result = process_field_edit(
            self.sample_invoice,
            "invalid_field",
            "some value"
        )
        
        assert result["success"] is False
        assert "error" in result
        assert "invalid field" in result["error"].lower()
    
    def test_process_field_edit_invalid_line_index(self):
        """Test processing edit with invalid line index."""
        result = process_field_edit(
            self.sample_invoice,
            "qty",
            "2.0",
            line_index=999  # Line doesn't exist
        )
        
        assert result["success"] is False
        assert "error" in result
        assert "line" in result["error"].lower()
    
    def test_validate_edit_input_numeric_fields(self):
        """Test validation of numeric field inputs."""
        # Valid numeric inputs
        valid_cases = [
            ("qty", "2.5", 2.5),
            ("price", "15000", 15000.0),
            ("amount", "30000.50", 30000.50),
            ("qty", "1", 1.0),
        ]
        
        for field, input_value, expected in valid_cases:
            result = validate_edit_input(field, input_value)
            assert result["valid"] is True, f"Field '{field}' with value '{input_value}' should be valid"
            assert result["converted_value"] == expected
        
        # Invalid numeric inputs
        invalid_cases = [
            ("qty", "invalid"),
            ("price", "not_a_number"),
            ("amount", ""),
            ("qty", "-1.0"),  # Negative quantity
            ("price", "-5000"),  # Negative price
        ]
        
        for field, input_value in invalid_cases:
            result = validate_edit_input(field, input_value)
            assert result["valid"] is False, f"Field '{field}' with value '{input_value}' should be invalid"
    
    def test_validate_edit_input_text_fields(self):
        """Test validation of text field inputs."""
        # Valid text inputs
        valid_cases = [
            ("supplier", "Valid Supplier Name"),
            ("invoice_number", "INV-2025-001"),
            ("name", "Product Name"),
            ("unit", "kg"),
        ]
        
        for field, input_value in valid_cases:
            result = validate_edit_input(field, input_value)
            assert result["valid"] is True, f"Field '{field}' with value '{input_value}' should be valid"
            assert result["converted_value"] == input_value
        
        # Invalid text inputs
        invalid_cases = [
            ("supplier", ""),  # Empty supplier
            ("invoice_number", ""),  # Empty invoice number
            ("name", ""),  # Empty product name
            ("supplier", "A"),  # Too short
        ]
        
        for field, input_value in invalid_cases:
            result = validate_edit_input(field, input_value)
            assert result["valid"] is False, f"Field '{field}' with value '{input_value}' should be invalid"
    
    def test_validate_edit_input_date_fields(self):
        """Test validation of date field inputs."""
        # Valid date inputs
        valid_cases = [
            ("date", "2025-05-28", date(2025, 5, 28)),
            ("invoice_date", "28/05/2025", date(2025, 5, 28)),
            ("date", "28.05.2025", date(2025, 5, 28)),
        ]
        
        for field, input_value, expected in valid_cases:
            result = validate_edit_input(field, input_value)
            assert result["valid"] is True, f"Field '{field}' with value '{input_value}' should be valid"
            assert result["converted_value"] == expected
        
        # Invalid date inputs
        invalid_cases = [
            ("date", "invalid-date"),
            ("invoice_date", "2025-13-01"),  # Invalid month
            ("date", "32/01/2025"),  # Invalid day
            ("date", ""),  # Empty date
        ]
        
        for field, input_value in invalid_cases:
            result = validate_edit_input(field, input_value)
            assert result["valid"] is False, f"Field '{field}' with value '{input_value}' should be invalid"
    
    def test_apply_edit_changes_with_recalculation(self):
        """Test applying edit changes that require recalculation."""
        changes = {
            "field": "qty",
            "line_index": 0,
            "old_value": 2.0,
            "new_value": 3.0
        }
        
        result = apply_edit_changes(self.sample_invoice, changes)
        
        assert result["success"] is True
        assert result["invoice"]["lines"][0]["qty"] == 3.0
        
        # Should recalculate amount (qty * price)
        expected_amount = 3.0 * 15000.0
        assert result["invoice"]["lines"][0]["amount"] == expected_amount
        
        # Should recalculate total
        expected_total = expected_amount + 25000.0  # Second line unchanged
        assert result["invoice"]["total_amount"] == expected_total
    
    def test_apply_edit_changes_without_recalculation(self):
        """Test applying edit changes that don't require recalculation."""
        changes = {
            "field": "supplier",
            "old_value": "Test Supplier Ltd",
            "new_value": "New Supplier Name"
        }
        
        result = apply_edit_changes(self.sample_invoice, changes)
        
        assert result["success"] is True
        assert result["invoice"]["supplier"] == "New Supplier Name"
        
        # Amounts should remain unchanged
        assert result["invoice"]["lines"][0]["amount"] == 30000.0
        assert result["invoice"]["total_amount"] == 55000.0
    
    def test_format_edit_response_success(self):
        """Test formatting successful edit response."""
        edit_result = {
            "success": True,
            "field": "supplier",
            "old_value": "Old Supplier",
            "new_value": "New Supplier"
        }
        
        response = format_edit_response(edit_result)
        
        assert "✅" in response or "success" in response.lower()
        assert "supplier" in response.lower()
        assert "Old Supplier" in response
        assert "New Supplier" in response
    
    def test_format_edit_response_error(self):
        """Test formatting error edit response."""
        edit_result = {
            "success": False,
            "error": "Invalid field specified"
        }
        
        response = format_edit_response(edit_result)
        
        assert "❌" in response or "error" in response.lower()
        assert "Invalid field specified" in response
    
    def test_format_edit_response_line_edit(self):
        """Test formatting line edit response."""
        edit_result = {
            "success": True,
            "field": "qty",
            "line_index": 0,
            "line_name": "Product A",
            "old_value": 2.0,
            "new_value": 3.0,
            "recalculated": True,
            "new_amount": 45000.0
        }
        
        response = format_edit_response(edit_result)
        
        assert "Product A" in response
        assert "qty" in response.lower() or "quantity" in response.lower()
        assert "2.0" in response
        assert "3.0" in response
        assert "45000" in response or "45,000" in response


class TestEditCoreValidation:
    """Test validation logic in edit core."""
    
    def test_validate_edit_permissions(self):
        """Test edit permission validation."""
        # Test with authorized user
        authorized_user_id = 12345
        result = validate_edit_permissions(authorized_user_id)
        assert result["authorized"] is True
        
        # Test with unauthorized user
        unauthorized_user_id = 99999
        result = validate_edit_permissions(unauthorized_user_id)
        assert result["authorized"] is False
    
    def test_validate_invoice_state(self):
        """Test invoice state validation for editing."""
        # Test with editable invoice
        editable_invoice = self.sample_invoice.copy()
        result = validate_invoice_state(editable_invoice)
        assert result["editable"] is True
        
        # Test with already processed invoice
        processed_invoice = self.sample_invoice.copy()
        processed_invoice["status"] = "sent_to_syrve"
        result = validate_invoice_state(processed_invoice)
        assert result["editable"] is False
    
    def test_validate_field_dependencies(self):
        """Test validation of field dependencies."""
        # Test quantity change (should trigger amount recalculation)
        result = validate_field_dependencies("qty", 3.0, self.sample_invoice, line_index=0)
        assert result["requires_recalculation"] is True
        assert "amount" in result["affected_fields"]
        
        # Test price change (should trigger amount recalculation)
        result = validate_field_dependencies("price", 20000.0, self.sample_invoice, line_index=0)
        assert result["requires_recalculation"] is True
        assert "amount" in result["affected_fields"]
        
        # Test supplier change (should not trigger recalculation)
        result = validate_field_dependencies("supplier", "New Supplier", self.sample_invoice)
        assert result["requires_recalculation"] is False


class TestEditCoreErrorHandling:
    """Test error handling in edit core."""
    
    @pytest.mark.asyncio
    async def test_handle_concurrent_edits(self):
        """Test handling of concurrent edit attempts."""
        with patch('app.handlers.edit_core.is_invoice_locked') as mock_locked:
            
            # Mock invoice being locked by another user
            mock_locked.return_value = {
                "locked": True,
                "locked_by": "another_user",
                "locked_since": "2025-05-28T10:00:00"
            }
            
            result = await handle_edit_request(
                "edit supplier New Name",
                self.sample_message,
                self.sample_bot
            )
            
            assert result["success"] is False
            assert "locked" in result["error"].lower() or "editing" in result["error"].lower()
    
    @pytest.mark.asyncio
    async def test_handle_missing_invoice(self):
        """Test handling when no invoice is available for editing."""
        with patch('app.handlers.edit_core.get_current_invoice') as mock_get:
            
            mock_get.return_value = None
            
            result = await handle_edit_request(
                "edit supplier New Name",
                self.sample_message,
                self.sample_bot
            )
            
            assert result["success"] is False
            assert "invoice" in result["error"].lower()
    
    def test_handle_invalid_data_types(self):
        """Test handling of invalid data types in edits."""
        invalid_invoices = [
            None,
            "not a dictionary",
            [],
            {"lines": "not a list"}
        ]
        
        for invalid_invoice in invalid_invoices:
            result = process_field_edit(invalid_invoice, "supplier", "New Name")
            assert result["success"] is False
            assert "error" in result
    
    def test_handle_corrupted_line_data(self):
        """Test handling of corrupted line data."""
        corrupted_invoice = {
            "supplier": "Test Supplier",
            "lines": [
                None,  # Corrupted line
                {"name": "Valid Product", "qty": 1.0},  # Valid line
                "not a dictionary"  # Corrupted line
            ]
        }
        
        result = process_field_edit(
            corrupted_invoice,
            "qty",
            "2.0",
            line_index=1  # Edit the valid line
        )
        
        # Should handle gracefully and edit the valid line
        assert result["success"] is True


class TestEditCoreIntegration:
    """Integration tests for edit core functionality."""
    
    @pytest.mark.asyncio
    async def test_complete_edit_workflow(self):
        """Test complete edit workflow from command to response."""
        with patch('app.handlers.edit_core.get_current_invoice') as mock_get, \
             patch('app.handlers.edit_core.save_invoice') as mock_save, \
             patch('app.handlers.edit_core.log_edit_action') as mock_log:
            
            mock_get.return_value = self.sample_invoice
            
            # Simulate complete edit workflow
            edit_command = "edit line 1 qty 4.0"
            
            result = await handle_edit_request(
                edit_command,
                self.sample_message,
                self.sample_bot
            )
            
            # Should complete successfully
            assert result["success"] is True
            
            # Should save the edited invoice
            mock_save.assert_called_once()
            
            # Should log the edit action
            mock_log.assert_called_once()
            
            # Should send confirmation to user
            self.sample_bot.send_message.assert_called()
    
    @pytest.mark.asyncio
    async def test_edit_with_validation_integration(self):
        """Test edit integration with validation systems."""
        with patch('app.handlers.edit_core.get_current_invoice') as mock_get, \
             patch('app.handlers.edit_core.validate_edited_invoice') as mock_validate:
            
            mock_get.return_value = self.sample_invoice
            
            # Mock validation results
            mock_validate.return_value = {
                "valid": True,
                "warnings": ["Price seems high for this product type"],
                "issues": []
            }
            
            result = await handle_edit_request(
                "edit line 1 price 50000",
                self.sample_message,
                self.sample_bot
            )
            
            assert result["success"] is True
            
            # Should include validation warnings in response
            if "warnings" in result:
                assert len(result["warnings"]) > 0


if __name__ == "__main__":
    pytest.main([__file__])