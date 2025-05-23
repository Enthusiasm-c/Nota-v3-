"""Tests for app/matcher.py module"""

import pytest
from unittest.mock import Mock, patch
from app.matcher import (
    match_positions,
    find_best_match,
    normalize_name,
    normalize_unit,
    calculate_similarity,
    fuzzy_match_product,
    get_unit_variants,
    check_unit_compatibility
)
from app.models import Product, Position


class TestNormalizationFunctions:
    """Test name and unit normalization functions"""
    
    def test_normalize_name_basic(self):
        """Test basic name normalization"""
        assert normalize_name("Product Name") == "product name"
        assert normalize_name("PRODUCT NAME") == "product name"
        assert normalize_name("  Product  Name  ") == "product name"
    
    def test_normalize_name_special_chars(self):
        """Test name normalization with special characters"""
        assert normalize_name("Product-Name") == "product name"
        assert normalize_name("Product.Name") == "product name"
        assert normalize_name("Product/Name") == "product name"
        assert normalize_name("Product_Name") == "product name"
    
    def test_normalize_name_numbers(self):
        """Test name normalization with numbers"""
        assert normalize_name("Product 123") == "product 123"
        assert normalize_name("123 Product") == "123 product"
    
    def test_normalize_unit_basic(self):
        """Test basic unit normalization"""
        assert normalize_unit("KG") == "kg"
        assert normalize_unit("kg") == "kg"
        assert normalize_unit("Kg") == "kg"
        assert normalize_unit("  kg  ") == "kg"
    
    def test_normalize_unit_variants(self):
        """Test unit normalization with variants"""
        assert normalize_unit("kilogram") == "kg"
        assert normalize_unit("piece") == "pcs"
        assert normalize_unit("pieces") == "pcs"
        assert normalize_unit("штука") == "pcs"
        assert normalize_unit("шт") == "pcs"
    
    def test_normalize_unit_unknown(self):
        """Test unit normalization with unknown units"""
        assert normalize_unit("unknown_unit") == "unknown_unit"
        assert normalize_unit("") == ""


class TestUnitFunctions:
    """Test unit-related functions"""
    
    def test_get_unit_variants(self):
        """Test getting unit variants"""
        kg_variants = get_unit_variants("kg")
        assert "kg" in kg_variants
        assert "kilogram" in kg_variants
        assert "кг" in kg_variants
        
        pcs_variants = get_unit_variants("pcs")
        assert "pcs" in pcs_variants
        assert "piece" in pcs_variants
        assert "шт" in pcs_variants
    
    def test_get_unit_variants_unknown(self):
        """Test getting variants for unknown unit"""
        variants = get_unit_variants("unknown")
        assert variants == {"unknown"}
    
    def test_check_unit_compatibility_same(self):
        """Test unit compatibility for same units"""
        assert check_unit_compatibility("kg", "kg") is True
        assert check_unit_compatibility("pcs", "pcs") is True
    
    def test_check_unit_compatibility_variants(self):
        """Test unit compatibility for unit variants"""
        assert check_unit_compatibility("kg", "kilogram") is True
        assert check_unit_compatibility("pcs", "piece") is True
        assert check_unit_compatibility("шт", "pcs") is True
    
    def test_check_unit_compatibility_different(self):
        """Test unit compatibility for different units"""
        assert check_unit_compatibility("kg", "pcs") is False
        assert check_unit_compatibility("l", "kg") is False


class TestSimilarityCalculation:
    """Test similarity calculation"""
    
    def test_calculate_similarity_identical(self):
        """Test similarity for identical strings"""
        assert calculate_similarity("product", "product") == 1.0
        assert calculate_similarity("test", "test") == 1.0
    
    def test_calculate_similarity_different(self):
        """Test similarity for different strings"""
        sim = calculate_similarity("product", "item")
        assert 0 <= sim <= 1
        assert sim < 0.5  # Should be low for unrelated words
    
    def test_calculate_similarity_partial(self):
        """Test similarity for partial matches"""
        sim = calculate_similarity("product a", "product b")
        assert sim > 0.5  # Should be high for similar strings
    
    def test_calculate_similarity_empty(self):
        """Test similarity with empty strings"""
        assert calculate_similarity("", "") == 1.0
        assert calculate_similarity("test", "") == 0.0
        assert calculate_similarity("", "test") == 0.0


class TestFuzzyMatchProduct:
    """Test fuzzy product matching"""
    
    def test_fuzzy_match_exact(self):
        """Test fuzzy match with exact name"""
        products = [
            Product(id="1", code="A", name="Apple", alias="apple", unit="kg"),
            Product(id="2", code="B", name="Banana", alias="banana", unit="kg")
        ]
        
        match, score = fuzzy_match_product("Apple", products)
        assert match is not None
        assert match.name == "Apple"
        assert score > 0.9
    
    def test_fuzzy_match_alias(self):
        """Test fuzzy match with alias"""
        products = [
            Product(id="1", code="A", name="Product A", alias="prod-a", unit="kg"),
            Product(id="2", code="B", name="Product B", alias="prod-b", unit="kg")
        ]
        
        match, score = fuzzy_match_product("prod-a", products)
        assert match is not None
        assert match.alias == "prod-a"
        assert score > 0.9
    
    def test_fuzzy_match_partial(self):
        """Test fuzzy match with partial name"""
        products = [
            Product(id="1", code="A", name="Green Apple", alias="apple", unit="kg"),
            Product(id="2", code="B", name="Yellow Banana", alias="banana", unit="kg")
        ]
        
        match, score = fuzzy_match_product("Apple", products)
        assert match is not None
        assert "Apple" in match.name
        assert score > 0.5
    
    def test_fuzzy_match_no_match(self):
        """Test fuzzy match with no good match"""
        products = [
            Product(id="1", code="A", name="Apple", alias="apple", unit="kg"),
            Product(id="2", code="B", name="Banana", alias="banana", unit="kg")
        ]
        
        match, score = fuzzy_match_product("Orange", products, threshold=0.8)
        assert match is None
        assert score < 0.8
    
    def test_fuzzy_match_empty_products(self):
        """Test fuzzy match with empty product list"""
        match, score = fuzzy_match_product("Test", [])
        assert match is None
        assert score == 0.0


class TestFindBestMatch:
    """Test find_best_match function"""
    
    def test_find_best_match_exact(self):
        """Test finding best match with exact match"""
        position = {"name": "Apple", "unit": "kg"}
        products = [
            Product(id="1", code="A", name="Apple", alias="apple", unit="kg"),
            Product(id="2", code="B", name="Banana", alias="banana", unit="kg")
        ]
        
        result = find_best_match(position, products)
        
        assert result["matched_product"] is not None
        assert result["matched_product"].name == "Apple"
        assert result["confidence"] > 0.9
        assert result["status"] == "ok"
    
    def test_find_best_match_unit_mismatch(self):
        """Test finding match with unit mismatch"""
        position = {"name": "Apple", "unit": "pcs"}
        products = [
            Product(id="1", code="A", name="Apple", alias="apple", unit="kg")
        ]
        
        result = find_best_match(position, products)
        
        assert result["matched_product"] is not None
        assert result["status"] == "unit_mismatch"
        assert result["confidence"] > 0.8
    
    def test_find_best_match_no_match(self):
        """Test finding no match"""
        position = {"name": "Orange", "unit": "kg"}
        products = [
            Product(id="1", code="A", name="Apple", alias="apple", unit="kg"),
            Product(id="2", code="B", name="Banana", alias="banana", unit="kg")
        ]
        
        result = find_best_match(position, products, threshold=0.8)
        
        assert result["matched_product"] is None
        assert result["status"] == "unknown"
        assert result["confidence"] < 0.8
    
    def test_find_best_match_with_price_hint(self):
        """Test finding match considers price hint"""
        position = {"name": "Apple", "unit": "kg", "price": 100}
        products = [
            Product(id="1", code="A", name="Apple", alias="apple", unit="kg", price_hint=95),
            Product(id="2", code="B", name="Apple Premium", alias="apple-p", unit="kg", price_hint=150)
        ]
        
        result = find_best_match(position, products)
        
        # Should prefer the one with closer price
        assert result["matched_product"].id == "1"


class TestMatchPositions:
    """Test match_positions function"""
    
    def test_match_positions_all_matched(self):
        """Test matching all positions successfully"""
        positions = [
            {"name": "Apple", "unit": "kg", "qty": 10, "price": 100},
            {"name": "Banana", "unit": "kg", "qty": 5, "price": 50}
        ]
        products = [
            Product(id="1", code="A", name="Apple", alias="apple", unit="kg"),
            Product(id="2", code="B", name="Banana", alias="banana", unit="kg")
        ]
        
        results = match_positions(positions, products)
        
        assert len(results) == 2
        assert all(r["status"] == "ok" for r in results)
        assert results[0]["matched_name"] == "Apple"
        assert results[1]["matched_name"] == "Banana"
    
    def test_match_positions_partial_match(self):
        """Test matching with some unknown positions"""
        positions = [
            {"name": "Apple", "unit": "kg", "qty": 10},
            {"name": "Unknown Item", "unit": "pcs", "qty": 1}
        ]
        products = [
            Product(id="1", code="A", name="Apple", alias="apple", unit="kg")
        ]
        
        results = match_positions(positions, products)
        
        assert len(results) == 2
        assert results[0]["status"] == "ok"
        assert results[1]["status"] == "unknown"
    
    def test_match_positions_empty_positions(self):
        """Test matching with empty positions"""
        results = match_positions([], [])
        assert results == []
    
    def test_match_positions_preserves_original_data(self):
        """Test that original position data is preserved"""
        positions = [
            {"name": "Apple", "unit": "kg", "qty": 10, "price": 100, "custom_field": "test"}
        ]
        products = [
            Product(id="1", code="A", name="Apple", alias="apple", unit="kg")
        ]
        
        results = match_positions(positions, products)
        
        assert results[0]["qty"] == 10
        assert results[0]["price"] == 100
        assert results[0]["custom_field"] == "test"
    
    @patch('app.matcher.logger')
    def test_match_positions_logs_results(self, mock_logger):
        """Test that matching results are logged"""
        positions = [{"name": "Test", "unit": "kg"}]
        products = []
        
        match_positions(positions, products)
        
        # Verify logging was called
        assert mock_logger.info.called


class TestMatcherIntegration:
    """Integration tests for matcher module"""
    
    def test_real_world_matching(self):
        """Test with real-world like data"""
        positions = [
            {"name": "Томаты св.", "unit": "кг", "qty": 5.5, "price": 120},
            {"name": "Огурцы", "unit": "кг", "qty": 3, "price": 80},
            {"name": "Картофель", "unit": "кг", "qty": 10, "price": 30}
        ]
        
        products = [
            Product(id="1", code="TOM", name="Томаты свежие", alias="томаты", unit="кг", price_hint=110),
            Product(id="2", code="CUC", name="Огурцы свежие", alias="огурцы", unit="кг", price_hint=75),
            Product(id="3", code="POT", name="Картофель", alias="картошка", unit="кг", price_hint=28)
        ]
        
        results = match_positions(positions, products)
        
        # All should match
        assert all(r["status"] == "ok" for r in results)
        
        # Check specific matches
        assert results[0]["matched_name"] == "Томаты свежие"
        assert results[1]["matched_name"] == "Огурцы свежие"
        assert results[2]["matched_name"] == "Картофель"