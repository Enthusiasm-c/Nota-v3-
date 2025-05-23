"""Tests for app/models.py"""

import pytest
from datetime import date
from pydantic import ValidationError

from app.models import Product, Position, ParsedData


class TestProduct:
    """Test Product model"""
    
    def test_create_product_with_all_fields(self):
        """Test creating product with all fields"""
        product = Product(
            id="123",
            code="ABC123",
            name="Test Product",
            alias="test-prod",
            unit="kg",
            price_hint=99.99
        )
        assert product.id == "123"
        assert product.code == "ABC123"
        assert product.name == "Test Product"
        assert product.alias == "test-prod"
        assert product.unit == "kg"
        assert product.price_hint == 99.99
    
    def test_create_product_without_price_hint(self):
        """Test creating product without optional price_hint"""
        product = Product(
            id="123",
            code="ABC123",
            name="Test Product",
            alias="test-prod",
            unit="kg"
        )
        assert product.price_hint is None
    
    def test_product_missing_required_field(self):
        """Test that missing required fields raise ValidationError"""
        with pytest.raises(ValidationError) as exc_info:
            Product(
                id="123",
                code="ABC123",
                # Missing name
                alias="test-prod",
                unit="kg"
            )
        assert "name" in str(exc_info.value)
    
    def test_product_json_serialization(self):
        """Test product JSON serialization"""
        product = Product(
            id="123",
            code="ABC123",
            name="Test Product",
            alias="test-prod",
            unit="kg",
            price_hint=99.99
        )
        json_data = product.model_dump()
        assert json_data["id"] == "123"
        assert json_data["price_hint"] == 99.99


class TestPosition:
    """Test Position model"""
    
    def test_create_position_minimal(self):
        """Test creating position with minimal required fields"""
        position = Position(
            name="Test Item",
            qty=10.5
        )
        assert position.name == "Test Item"
        assert position.qty == 10.5
        assert position.unit is None
        assert position.price is None
        assert position.price_per_unit is None
        assert position.total_price is None
    
    def test_create_position_full(self):
        """Test creating position with all fields"""
        position = Position(
            name="Test Item",
            qty=10,
            unit="kg",
            price=100,
            price_per_unit=10,
            total_price=100
        )
        assert position.name == "Test Item"
        assert position.qty == 10
        assert position.unit == "kg"
        assert position.price == 100
        assert position.price_per_unit == 10
        assert position.total_price == 100
    
    def test_position_qty_types(self):
        """Test position accepts different numeric types for qty"""
        # Float
        pos1 = Position(name="Item", qty=10.5)
        assert pos1.qty == 10.5
        
        # Int
        pos2 = Position(name="Item", qty=10)
        assert pos2.qty == 10.0
        
        # String that can be converted
        pos3 = Position(name="Item", qty="10.5")
        assert pos3.qty == 10.5
    
    def test_position_missing_required_fields(self):
        """Test that missing required fields raise ValidationError"""
        # Missing name
        with pytest.raises(ValidationError) as exc_info:
            Position(qty=10)
        assert "name" in str(exc_info.value)
        
        # Missing qty
        with pytest.raises(ValidationError) as exc_info:
            Position(name="Item")
        assert "qty" in str(exc_info.value)
    
    def test_position_price_fields_independence(self):
        """Test that price fields are independent"""
        # Can have price without price_per_unit
        pos1 = Position(name="Item", qty=10, price=100)
        assert pos1.price == 100
        assert pos1.price_per_unit is None
        
        # Can have price_per_unit without price
        pos2 = Position(name="Item", qty=10, price_per_unit=10)
        assert pos2.price is None
        assert pos2.price_per_unit == 10
        
        # Can have total_price without other prices
        pos3 = Position(name="Item", qty=10, total_price=100)
        assert pos3.price is None
        assert pos3.price_per_unit is None
        assert pos3.total_price == 100


class TestParsedData:
    """Test ParsedData model"""
    
    def test_create_parsed_data_empty(self):
        """Test creating ParsedData with defaults"""
        data = ParsedData()
        assert data.supplier is None
        assert data.date is None
        assert data.positions == []
        assert data.price is None
        assert data.price_per_unit is None
        assert data.total_price is None
        assert data.supplier_status is None
    
    def test_create_parsed_data_full(self):
        """Test creating ParsedData with all fields"""
        positions = [
            Position(name="Item 1", qty=10, unit="kg"),
            Position(name="Item 2", qty=5, unit="pcs")
        ]
        data = ParsedData(
            supplier="Test Supplier",
            date=date(2024, 1, 15),
            positions=positions,
            price=500,
            price_per_unit=50,
            total_price=500,
            supplier_status="verified"
        )
        assert data.supplier == "Test Supplier"
        assert data.date == date(2024, 1, 15)
        assert len(data.positions) == 2
        assert data.positions[0].name == "Item 1"
        assert data.supplier_status == "verified"
    
    def test_parse_iso_date_validator(self):
        """Test parse_iso date validator"""
        # ISO string format
        data1 = ParsedData(date="2024-01-15")
        assert data1.date == date(2024, 1, 15)
        
        # Date object passes through
        data2 = ParsedData(date=date(2024, 1, 15))
        assert data2.date == date(2024, 1, 15)
        
        # None/empty returns None
        data3 = ParsedData(date=None)
        assert data3.date is None
        
        data4 = ParsedData(date="")
        assert data4.date is None
    
    def test_parse_iso_invalid_format(self):
        """Test parse_iso with invalid date format"""
        with pytest.raises(ValidationError) as exc_info:
            ParsedData(date="15/01/2024")  # Wrong format
        assert "Invalid date format" in str(exc_info.value)
        assert "Expected ISO format" in str(exc_info.value)
        
        with pytest.raises(ValidationError) as exc_info:
            ParsedData(date="2024-13-01")  # Invalid month
        assert "Invalid date format" in str(exc_info.value)
    
    def test_validate_positions_empty(self):
        """Test validate_positions with empty list"""
        data = ParsedData(positions=[])
        assert data.positions == []
    
    def test_validate_positions_with_dict_input(self):
        """Test positions can be created from dict"""
        data = ParsedData(positions=[
            {"name": "Item 1", "qty": 10},
            {"name": "Item 2", "qty": 5, "unit": "kg"}
        ])
        assert len(data.positions) == 2
        assert isinstance(data.positions[0], Position)
        assert data.positions[0].name == "Item 1"
        assert data.positions[0].qty == 10
        assert data.positions[1].unit == "kg"
    
    def test_validate_positions_missing_fields(self):
        """Test validate_positions checks for required fields"""
        # This should work because Pydantic validates Position creation
        with pytest.raises(ValidationError) as exc_info:
            ParsedData(positions=[
                {"name": "Item 1"}  # Missing qty
            ])
        assert "qty" in str(exc_info.value)
        
        with pytest.raises(ValidationError) as exc_info:
            ParsedData(positions=[
                {"qty": 10}  # Missing name
            ])
        assert "name" in str(exc_info.value)
    
    def test_parsed_data_json_serialization(self):
        """Test ParsedData JSON serialization"""
        data = ParsedData(
            supplier="Test",
            date="2024-01-15",
            positions=[
                Position(name="Item", qty=10, price=100)
            ],
            total_price=100
        )
        
        json_data = data.model_dump()
        assert json_data["supplier"] == "Test"
        assert json_data["date"] == date(2024, 1, 15)
        assert len(json_data["positions"]) == 1
        assert json_data["positions"][0]["name"] == "Item"
        assert json_data["total_price"] == 100
    
    def test_parsed_data_with_mixed_position_types(self):
        """Test ParsedData with positions having different optional fields"""
        positions = [
            Position(name="Item 1", qty=10),  # Minimal
            Position(name="Item 2", qty=5, unit="kg", price=50),  # With some fields
            Position(name="Item 3", qty=2, unit="pcs", price=20, price_per_unit=10, total_price=20)  # Full
        ]
        data = ParsedData(positions=positions)
        
        assert len(data.positions) == 3
        # First position has only required fields
        assert data.positions[0].unit is None
        assert data.positions[0].price is None
        # Second position has some optional fields
        assert data.positions[1].unit == "kg"
        assert data.positions[1].price == 50
        assert data.positions[1].price_per_unit is None
        # Third position has all fields
        assert data.positions[2].unit == "pcs"
        assert data.positions[2].price == 20
        assert data.positions[2].price_per_unit == 10
        assert data.positions[2].total_price == 20


class TestModelIntegration:
    """Integration tests for models working together"""
    
    def test_create_invoice_data_structure(self):
        """Test creating a complete invoice data structure"""
        # Create positions
        positions = [
            Position(name="Apples", qty=10, unit="kg", price_per_unit=5, total_price=50),
            Position(name="Oranges", qty=20, unit="kg", price_per_unit=3, total_price=60),
            Position(name="Bananas", qty=15, unit="kg", price_per_unit=4, total_price=60)
        ]
        
        # Create parsed data
        invoice = ParsedData(
            supplier="Fresh Fruits Co.",
            date="2024-01-15",
            positions=positions,
            total_price=170,
            supplier_status="verified"
        )
        
        # Verify structure
        assert invoice.supplier == "Fresh Fruits Co."
        assert invoice.date == date(2024, 1, 15)
        assert len(invoice.positions) == 3
        assert sum(pos.total_price for pos in invoice.positions if pos.total_price) == 170
        assert invoice.total_price == 170
    
    def test_model_validation_cascade(self):
        """Test that validation errors cascade properly"""
        # Invalid position should cause ParsedData validation to fail
        with pytest.raises(ValidationError) as exc_info:
            ParsedData(
                supplier="Test",
                positions=[
                    {"name": "Valid Item", "qty": 10},
                    {"name": "Invalid Item", "qty": "not-a-number"}  # Invalid qty
                ]
            )
        assert "qty" in str(exc_info.value)