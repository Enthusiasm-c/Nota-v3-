"""Tests for weight conversion functionality"""

import pytest
from app.utils.data_utils import convert_weight_to_kg, should_convert_to_kg


class TestShouldConvertToKg:
    """Test should_convert_to_kg function"""
    
    def test_grams_conversion_threshold(self):
        """Test grams conversion based on quantity"""
        # Should convert when >= 1000g
        assert should_convert_to_kg(1000, "g") is True
        assert should_convert_to_kg(1500, "g") is True
        assert should_convert_to_kg(10000, "g") is True
        
        # Should not convert when < 1000g
        assert should_convert_to_kg(999, "g") is False
        assert should_convert_to_kg(500, "g") is False
        assert should_convert_to_kg(100, "g") is False
    
    def test_different_gram_notations(self):
        """Test different gram notations"""
        for unit in ["g", "gr", "gm", "gram", "grams", "gramme", "grammes", "г", "гр"]:
            assert should_convert_to_kg(1000, unit) is True
            assert should_convert_to_kg(999, unit) is False
    
    def test_always_convert_units(self):
        """Test units that should always be converted"""
        # Tons
        for unit in ["t", "ton", "tonne", "т"]:
            assert should_convert_to_kg(0.5, unit) is True
            assert should_convert_to_kg(1, unit) is True
            assert should_convert_to_kg(10, unit) is True
        
        # Pounds
        for unit in ["lb", "lbs", "pound", "pounds"]:
            assert should_convert_to_kg(1, unit) is True
            assert should_convert_to_kg(10, unit) is True
        
        # Ounces
        for unit in ["oz", "ounce", "ounces"]:
            assert should_convert_to_kg(1, unit) is True
            assert should_convert_to_kg(16, unit) is True
    
    def test_milligrams_threshold(self):
        """Test milligrams conversion threshold"""
        # Should convert when >= 1,000,000 mg (1 kg)
        assert should_convert_to_kg(1_000_000, "mg") is True
        assert should_convert_to_kg(2_000_000, "mg") is True
        
        # Should not convert when < 1,000,000 mg
        assert should_convert_to_kg(999_999, "mg") is False
        assert should_convert_to_kg(500_000, "mg") is False
    
    def test_kilograms_no_conversion(self):
        """Test that kilograms are not converted"""
        for unit in ["kg", "kgs", "kilogram", "kilograms", "кг"]:
            assert should_convert_to_kg(1, unit) is False
            assert should_convert_to_kg(1000, unit) is False
    
    def test_unknown_units(self):
        """Test unknown units are not converted"""
        assert should_convert_to_kg(1000, "pcs") is False
        assert should_convert_to_kg(1000, "l") is False
        assert should_convert_to_kg(1000, "ml") is False


class TestConvertWeightToKg:
    """Test convert_weight_to_kg function"""
    
    def test_grams_to_kg(self):
        """Test converting grams to kilograms"""
        qty, unit, price = convert_weight_to_kg(1000, "g", 10.0)
        assert qty == 1.0
        assert unit == "kg"
        assert price == 10000.0  # Price per kg
        
        qty, unit, price = convert_weight_to_kg(2500, "g", 5.0)
        assert qty == 2.5
        assert unit == "kg"
        assert price == 5000.0
    
    def test_various_gram_notations(self):
        """Test different gram notations convert correctly"""
        for gram_unit in ["g", "gr", "gm", "gram", "grams", "г", "гр"]:
            qty, unit, price = convert_weight_to_kg(3000, gram_unit, 1.0)
            assert qty == 3.0
            assert unit == "kg"
            assert price == 1000.0
    
    def test_tons_to_kg(self):
        """Test converting tons to kilograms"""
        qty, unit, price = convert_weight_to_kg(1, "t", 1000000.0)
        assert qty == 1000
        assert unit == "kg"
        assert price == 1000.0  # Price per kg
        
        qty, unit, price = convert_weight_to_kg(0.5, "ton", 500.0)
        assert qty == 500
        assert unit == "kg"
        assert price == 0.5  # Price per kg
    
    def test_pounds_to_kg(self):
        """Test converting pounds to kilograms"""
        qty, unit, price = convert_weight_to_kg(2.20462, "lb", 1.0)
        assert abs(qty - 1.0) < 0.001  # Approximately 1 kg
        assert unit == "kg"
        assert abs(price - 2.20462) < 0.001
    
    def test_ounces_to_kg(self):
        """Test converting ounces to kilograms"""
        qty, unit, price = convert_weight_to_kg(35.274, "oz", 1.0)
        assert abs(qty - 1.0) < 0.001  # Approximately 1 kg
        assert unit == "kg"
    
    def test_milligrams_to_kg(self):
        """Test converting milligrams to kilograms"""
        qty, unit, price = convert_weight_to_kg(1_500_000, "mg", 0.001)
        assert qty == 1.5
        assert unit == "kg"
        assert abs(price - 1000.0) < 0.01  # Price per kg with floating point tolerance
    
    def test_no_price_conversion(self):
        """Test conversion without price"""
        qty, unit, price = convert_weight_to_kg(2000, "g", None)
        assert qty == 2.0
        assert unit == "kg"
        assert price is None
    
    def test_kg_no_conversion(self):
        """Test that kg is not converted"""
        qty, unit, price = convert_weight_to_kg(5, "kg", 100.0)
        assert qty == 5
        assert unit == "kg"
        assert price == 100.0
    
    def test_unknown_unit_no_conversion(self):
        """Test unknown units are not converted"""
        qty, unit, price = convert_weight_to_kg(100, "pcs", 10.0)
        assert qty == 100
        assert unit == "pcs"
        assert price == 10.0
    
    def test_case_insensitive(self):
        """Test case insensitive unit recognition"""
        # Uppercase
        qty, unit, price = convert_weight_to_kg(1000, "G", 1.0)
        assert qty == 1.0
        assert unit == "kg"
        
        # Mixed case
        qty, unit, price = convert_weight_to_kg(1000, "Gram", 1.0)
        assert qty == 1.0
        assert unit == "kg"


class TestIntegrationWithPostprocessing:
    """Test integration with postprocessing module"""
    
    def test_postprocess_converts_grams(self):
        """Test that postprocessing converts grams correctly"""
        from app.models import ParsedData, Position
        from app.postprocessing import postprocess_parsed_data
        
        # Create test data with grams
        parsed = ParsedData(
            supplier="Test Supplier",
            date="2024-01-15",
            positions=[
                Position(name="Sugar", qty=2000, unit="g", price=0.05, total_price=100),
                Position(name="Salt", qty=500, unit="g", price=0.02, total_price=10),
                Position(name="Flour", qty=5000, unit="gr", price=0.03, total_price=150),
            ],
            total_price=260
        )
        
        # Process
        result = postprocess_parsed_data(parsed, "test-001")
        
        # Check conversions
        # Sugar: 2000g -> 2kg
        assert result.positions[0].qty == 2.0
        assert result.positions[0].unit == "kg"
        assert result.positions[0].price == 50.0  # 0.05 * 1000
        
        # Salt: 500g -> not converted (less than 1000g)
        assert result.positions[1].qty == 500
        assert result.positions[1].unit == "g"
        assert result.positions[1].price == 0.02
        
        # Flour: 5000g -> 5kg
        assert result.positions[2].qty == 5.0
        assert result.positions[2].unit == "kg"
        assert result.positions[2].price == 30.0  # 0.03 * 1000
    
    def test_postprocess_various_units(self):
        """Test postprocessing with various weight units"""
        from app.models import ParsedData, Position
        from app.postprocessing import postprocess_parsed_data
        
        parsed = ParsedData(
            supplier="Test Supplier",
            positions=[
                Position(name="Heavy item", qty=0.5, unit="t", price=2000),  # 0.5 tons
                Position(name="Imported item", qty=10, unit="lb", price=5),  # 10 pounds
                Position(name="Small item", qty=100, unit="oz", price=0.5),  # 100 ounces
            ]
        )
        
        result = postprocess_parsed_data(parsed, "test-002")
        
        # Check all converted to kg
        assert result.positions[0].unit == "kg"
        assert result.positions[0].qty == 500  # 0.5 tons = 500 kg
        
        assert result.positions[1].unit == "kg"
        assert abs(result.positions[1].qty - 4.53592) < 0.001  # 10 lb ≈ 4.536 kg
        
        assert result.positions[2].unit == "kg"
        assert abs(result.positions[2].qty - 2.83495) < 0.001  # 100 oz ≈ 2.835 kg