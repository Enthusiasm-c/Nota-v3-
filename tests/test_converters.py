"""Tests for app/converters.py"""

import pytest
from unittest.mock import Mock

from app.converters import parsed_to_dict


class TestParsedToDict:
    """Test parsed_to_dict converter function"""
    
    def test_convert_pydantic_model(self):
        """Test converting Pydantic model with model_dump method"""
        # Create mock Pydantic model
        mock_model = Mock()
        mock_model.model_dump = Mock(return_value={"field": "value", "number": 123})
        
        result = parsed_to_dict(mock_model)
        
        assert result == {"field": "value", "number": 123}
        mock_model.model_dump.assert_called_once()
    
    def test_convert_dict_passthrough(self):
        """Test that dict is returned as-is"""
        test_dict = {"key": "value", "nested": {"inner": 42}}
        
        result = parsed_to_dict(test_dict)
        
        assert result is test_dict
        assert result == {"key": "value", "nested": {"inner": 42}}
    
    def test_convert_empty_dict(self):
        """Test converting empty dict"""
        result = parsed_to_dict({})
        assert result == {}
    
    def test_convert_unsupported_type_raises_error(self):
        """Test that unsupported types raise TypeError"""
        # Test with various unsupported types
        unsupported_objects = [
            "string",
            123,
            45.67,
            ["list"],
            ("tuple",),
            {1, 2, 3},  # set
            None
        ]
        
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
        outer_model.model_dump = Mock(return_value={
            "outer_field": "outer_value",
            "nested": inner_model.model_dump()
        })
        
        result = parsed_to_dict(outer_model)
        
        assert result == {
            "outer_field": "outer_value",
            "nested": {"inner_field": "inner_value"}
        }
    
    def test_convert_preserves_complex_dict_structure(self):
        """Test that complex dict structures are preserved"""
        complex_dict = {
            "positions": [
                {"name": "Item 1", "qty": 10, "price": 100},
                {"name": "Item 2", "qty": 5, "price": 50}
            ],
            "metadata": {
                "created": "2024-01-15",
                "version": 1,
                "tags": ["urgent", "verified"]
            },
            "total": 150,
            "is_valid": True,
            "notes": None
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