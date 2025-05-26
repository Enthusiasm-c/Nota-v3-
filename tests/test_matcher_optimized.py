"""Tests for optimized app/matcher.py module"""

import pytest
from unittest.mock import Mock, patch

from app.matcher import (
    match_positions,
    async_match_positions,
    calculate_string_similarity,
    fuzzy_find,
    get_best_match,
    normalize_product_name
)
from app.models import Product, Position


class TestCalculateStringSimilarity:
    """Test string similarity calculation with caching"""
    
    def test_exact_match(self):
        """Test exact string match returns 1.0"""
        assert calculate_string_similarity("apple", "apple") == 1.0
        assert calculate_string_similarity("Apple", "apple") == 1.0  # Case insensitive
    
    def test_none_values(self):
        """Test None values return 0.0"""
        assert calculate_string_similarity(None, "apple") == 0.0
        assert calculate_string_similarity("apple", None) == 0.0
        assert calculate_string_similarity(None, None) == 0.0
    
    def test_similar_strings(self):
        """Test similar strings return high scores"""
        score = calculate_string_similarity("apple", "apples")
        assert 0.8 < score < 1.0
        
        score = calculate_string_similarity("tomato", "tomate")
        assert 0.8 < score < 1.0
    
    def test_different_strings(self):
        """Test different strings return low scores"""
        score = calculate_string_similarity("apple", "orange")
        assert score < 0.5
    
    @patch('app.matcher.get_string_similarity_cached')
    @patch('app.matcher.set_string_similarity_cached')
    def test_caching(self, mock_set_cache, mock_get_cache):
        """Test that caching is used"""
        mock_get_cache.return_value = None  # Cache miss
        
        result = calculate_string_similarity("test", "text")
        
        # Should check cache
        mock_get_cache.assert_called_once()
        # Should set cache
        mock_set_cache.assert_called_once()


class TestFuzzyFind:
    """Test fuzzy find functionality"""
    
    def test_empty_inputs(self):
        """Test empty query or items returns empty list"""
        assert fuzzy_find("", [{"name": "apple"}]) == []
        assert fuzzy_find("apple", []) == []
        assert fuzzy_find("", []) == []
    
    def test_find_exact_match(self):
        """Test finding exact matches"""
        items = [
            {"id": "1", "name": "apple"},
            {"id": "2", "name": "orange"},
            {"id": "3", "name": "banana"}
        ]
        
        results = fuzzy_find("apple", items)
        assert len(results) == 1
        assert results[0]["id"] == "1"
        assert results[0]["score"] == 1.0
    
    def test_find_similar_matches(self):
        """Test finding similar matches"""
        items = [
            {"id": "1", "name": "apple"},
            {"id": "2", "name": "apples"},
            {"id": "3", "name": "application"},
            {"id": "4", "name": "orange"}
        ]
        
        results = fuzzy_find("apple", items, threshold=0.7)
        assert len(results) >= 2
        # Results should be sorted by score
        assert results[0]["score"] >= results[1]["score"]
    
    def test_threshold_filtering(self):
        """Test threshold filters results"""
        items = [
            {"id": "1", "name": "apple"},
            {"id": "2", "name": "completely different"}
        ]
        
        results = fuzzy_find("apple", items, threshold=0.9)
        assert len(results) == 1
        assert results[0]["id"] == "1"
    
    def test_limit_results(self):
        """Test limit parameter"""
        items = [{"id": str(i), "name": f"item{i}"} for i in range(10)]
        
        results = fuzzy_find("item", items, threshold=0.5, limit=3)
        assert len(results) <= 3
    
    def test_with_product_objects(self):
        """Test with Product model objects"""
        products = [
            Product(id="1", code="APP", name="Apple", alias="apple", unit="kg"),
            Product(id="2", code="ORG", name="Orange", alias="orange", unit="kg")
        ]
        
        results = fuzzy_find("appl", products, threshold=0.7)
        assert len(results) > 0
        assert "id" in results[0]
        assert "name" in results[0]


class TestMatchPositions:
    """Test position matching functionality"""
    
    def test_empty_positions(self):
        """Test with empty positions list"""
        results = match_positions([], [])
        assert results == []
    
    def test_match_found(self):
        """Test successful matching"""
        positions = [
            {"name": "Apple", "qty": 10, "price": 5.0},
            {"name": "Orange", "qty": 5, "price": 3.0}
        ]
        products = [
            {"id": "1", "name": "Apple"},
            {"id": "2", "name": "Orange"}
        ]
        
        results = match_positions(positions, products)
        
        assert len(results) == 2
        assert results[0]["status"] == "ok"
        assert results[0]["id"] == "1"
        assert results[0]["matched_name"] == "Apple"
        assert results[1]["status"] == "ok"
        assert results[1]["id"] == "2"
    
    def test_no_match(self):
        """Test when no match is found"""
        positions = [{"name": "Unknown Item", "qty": 1}]
        products = [{"id": "1", "name": "Apple"}]
        
        results = match_positions(positions, products, threshold=0.9)
        
        assert len(results) == 1
        assert results[0]["status"] == "unknown"
        assert results[0]["id"] == ""
        assert results[0]["matched_name"] is None
    
    def test_empty_name(self):
        """Test position with empty name"""
        positions = [{"name": "", "qty": 1}]
        products = [{"id": "1", "name": "Apple"}]
        
        results = match_positions(positions, products)
        
        assert len(results) == 1
        assert results[0]["status"] == "unknown"
        assert results[0]["score"] == 0.0


class TestAsyncMatchPositions:
    """Test async match positions"""
    
    @pytest.mark.asyncio
    async def test_async_delegates_to_sync(self):
        """Test that async version delegates to sync version"""
        positions = [{"name": "Apple", "qty": 10}]
        products = [{"id": "1", "name": "Apple"}]
        
        results = await async_match_positions(positions, products)
        
        assert len(results) == 1
        assert results[0]["status"] == "ok"
        assert results[0]["id"] == "1"
    
    @pytest.mark.asyncio
    async def test_with_position_objects(self):
        """Test with Position model objects"""
        positions = [
            Position(name="Apple", qty=10, price=5.0)
        ]
        products = [
            Product(id="1", code="APP", name="Apple", alias="apple", unit="kg")
        ]
        
        results = await async_match_positions(positions, products)
        
        assert len(results) == 1
        assert results[0]["name"] == "Apple"
        assert results[0]["status"] == "ok"


class TestHelperFunctions:
    """Test helper functions"""
    
    def test_normalize_product_name(self):
        """Test product name normalization"""
        assert normalize_product_name("  Apple  ") == "apple"
        assert normalize_product_name("ORANGE") == "orange"
        assert normalize_product_name("...Banana...") == "banana"
        assert normalize_product_name("") == ""
        assert normalize_product_name(None) == ""
    
    def test_get_best_match(self):
        """Test getting best match"""
        items = [
            {"id": "1", "name": "apple"},
            {"id": "2", "name": "apricot"},
            {"id": "3", "name": "orange"}
        ]
        
        # Should find apple
        match = get_best_match("appl", items)
        assert match is not None
        assert match["id"] == "1"
        
        # Should not find match with high threshold
        match = get_best_match("xyz", items, threshold=0.9)
        assert match is None