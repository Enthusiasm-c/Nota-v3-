"""Tests for app/converters.py"""

from unittest.mock import MagicMock, Mock

import pytest

from app.converters import parsed_to_dict
from app.models import ParsedData, Position


class TestParsedToDict:
    """Test parsed_to_dict function."""

    def test_parsed_to_dict_with_pydantic_model(self):
        """Test converting Pydantic model to dict."""
        # Create a ParsedData instance
        data = ParsedData(
            supplier="Test Supplier",
            date="2024-01-15",
            positions=[Position(name="Apple", qty=10, unit="kg", price=50.0)],
            total_price=500.0,
        )

        result = parsed_to_dict(data)

        assert isinstance(result, dict)
        assert result["supplier"] == "Test Supplier"
        assert result["total_price"] == 500.0
        assert len(result["positions"]) == 1
        assert result["positions"][0]["name"] == "Apple"

    def test_parsed_to_dict_with_dict_input(self):
        """Test that dict input is returned as-is."""
        input_dict = {"supplier": "Test Supplier", "total_price": 100.0, "positions": []}

        result = parsed_to_dict(input_dict)

        assert result is input_dict  # Should return the same object
        assert result["supplier"] == "Test Supplier"
        assert result["total_price"] == 100.0

    def test_parsed_to_dict_with_mock_model(self):
        """Test with mock object that has model_dump method."""
        mock_model = MagicMock()
        mock_model.model_dump.return_value = {"key": "value", "number": 42}

        result = parsed_to_dict(mock_model)

        assert result == {"key": "value", "number": 42}
        mock_model.model_dump.assert_called_once()

    def test_parsed_to_dict_with_invalid_input(self):
        """Test that invalid input raises TypeError."""
        with pytest.raises(TypeError) as exc_info:
            parsed_to_dict("invalid string")

        assert "Cannot convert object of type" in str(exc_info.value)
        assert "str" in str(exc_info.value)

    def test_parsed_to_dict_with_none(self):
        """Test that None input raises TypeError."""
        with pytest.raises(TypeError) as exc_info:
            parsed_to_dict(None)

        assert "Cannot convert object of type" in str(exc_info.value)
        assert "NoneType" in str(exc_info.value)

    def test_parsed_to_dict_with_number(self):
        """Test that number input raises TypeError."""
        with pytest.raises(TypeError) as exc_info:
            parsed_to_dict(123)

        assert "Cannot convert object of type" in str(exc_info.value)
        assert "int" in str(exc_info.value)

    def test_parsed_to_dict_with_list(self):
        """Test that list input raises TypeError."""
        with pytest.raises(TypeError) as exc_info:
            parsed_to_dict([1, 2, 3])

        assert "Cannot convert object of type" in str(exc_info.value)
        assert "list" in str(exc_info.value)

    def test_parsed_to_dict_preserves_nested_structure(self):
        """Test that nested structure is preserved."""
        nested_dict = {
            "top_level": "value",
            "nested": {"inner": "data", "list": [1, 2, 3]},
            "positions": [{"name": "item1", "qty": 5}, {"name": "item2", "qty": 10}],
        }

        result = parsed_to_dict(nested_dict)

        assert result is nested_dict
        assert result["nested"]["inner"] == "data"
        assert result["nested"]["list"] == [1, 2, 3]
        assert len(result["positions"]) == 2


class TestConvertersIntegration:
    """Integration tests for converters module."""

    def test_real_world_usage_with_parsed_data(self):
        """Test with realistic ParsedData scenario."""
        # Create realistic invoice data
        positions = [
            Position(name="Apples", qty=5, unit="kg", price=10.0, total_price=50.0),
            Position(name="Oranges", qty=3, unit="kg", price=8.0, total_price=24.0),
            Position(name="Bananas", qty=2, unit="kg", price=6.0, total_price=12.0),
        ]

        parsed_data = ParsedData(
            supplier="Fresh Fruits Ltd",
            date="2024-01-15",
            positions=positions,
            total_price=86.0,
            supplier_status="verified",
        )

        result = parsed_to_dict(parsed_data)

        # Verify the structure
        assert isinstance(result, dict)
        assert result["supplier"] == "Fresh Fruits Ltd"
        assert result["total_price"] == 86.0
        assert len(result["positions"]) == 3

        # Verify positions are properly converted
        apple_position = result["positions"][0]
        assert apple_position["name"] == "Apples"
        assert apple_position["qty"] == 5
        assert apple_position["unit"] == "kg"
        assert apple_position["total_price"] == 50.0

    def test_empty_parsed_data(self):
        """Test with empty ParsedData."""
        empty_data = ParsedData()

        result = parsed_to_dict(empty_data)

        assert isinstance(result, dict)
        assert result["supplier"] is None
        assert result["date"] is None
        assert result["positions"] == []
        assert result["total_price"] is None
        assert result is test_dict
        assert result == {"key": "value", "nested": {"inner": 42}}

    def test_convert_empty_dict(self):
        """Test converting empty dict"""
        result = parsed_to_dict({})
        assert result == {}

    def test_convert_unsupported_type_raises_error(self):
        """Test that unsupported types raise TypeError"""
        # Test with various unsupported types
        unsupported_objects = ["string", 123, 45.67, ["list"], ("tuple",), {1, 2, 3}, None]  # set

        for obj in unsupported_objects:
            with pytest.raises(TypeError) as exc_info:
                parsed_to_dict(obj)

            assert f"Cannot convert object of type {type(obj)} to dict" in str(exc_info.value)

    def test_convert_object_without_model_dump(self):
        """Test converting object that doesn't have model_dump method"""

        class CustomObject:
            def __init__(self):
                self.field = "value"

        obj = CustomObject()

        with pytest.raises(TypeError) as exc_info:
            parsed_to_dict(obj)

        assert "Cannot convert object of type" in str(exc_info.value)
        assert "CustomObject" in str(exc_info.value)

    def test_convert_nested_pydantic_models(self):
        """Test converting Pydantic model with nested models"""
        # Create nested mock models
        inner_model = Mock()
        inner_model.model_dump = Mock(return_value={"inner_field": "inner_value"})

        outer_model = Mock()
        outer_model.model_dump = Mock(
            return_value={"outer_field": "outer_value", "nested": inner_model.model_dump()}
        )

        result = parsed_to_dict(outer_model)

        assert result == {"outer_field": "outer_value", "nested": {"inner_field": "inner_value"}}

    def test_convert_preserves_complex_dict_structure(self):
        """Test that complex dict structures are preserved"""
        complex_dict = {
            "positions": [
                {"name": "Item 1", "qty": 10, "price": 100},
                {"name": "Item 2", "qty": 5, "price": 50},
            ],
            "metadata": {"created": "2024-01-15", "version": 1, "tags": ["urgent", "verified"]},
            "total": 150,
            "is_valid": True,
            "notes": None,
        }

        result = parsed_to_dict(complex_dict)

        assert result == complex_dict
        # Ensure it's the same object (not a copy)
        assert result is complex_dict

    def test_convert_model_dump_failure(self):
        """Test handling when model_dump raises an exception"""
        mock_model = Mock()
        mock_model.model_dump = Mock(side_effect=Exception("Model dump failed"))

        # Should propagate the exception
        with pytest.raises(Exception) as exc_info:
            parsed_to_dict(mock_model)

        assert "Model dump failed" in str(exc_info.value)
