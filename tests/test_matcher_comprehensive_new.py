"""
Comprehensive tests for the matcher module.
Tests product matching, fuzzy matching, and supplier mapping functionality.
"""

import pytest
from unittest.mock import Mock, patch, mock_open
import json
from app.matcher import (
    find_best_match,
    fuzzy_match_products,
    match_supplier,
    load_product_catalog,
    load_supplier_mappings,
    normalize_product_name,
    calculate_match_confidence,
    ProductMatcher,
    SupplierMatcher
)


class TestProductMatcher:
    """Test suite for ProductMatcher class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.sample_catalog = {
            "tomato": {
                "name": "Fresh Tomatoes",
                "category": "vegetables",
                "aliases": ["tomato", "tomat", "помидор"],
                "unit": "kg",
                "price_range": {"min": 8000, "max": 15000}
            },
            "chicken": {
                "name": "Chicken Meat",
                "category": "meat",
                "aliases": ["chicken", "ayam", "курица"],
                "unit": "kg", 
                "price_range": {"min": 25000, "max": 35000}
            },
            "rice": {
                "name": "White Rice",
                "category": "grains",
                "aliases": ["rice", "beras", "рис"],
                "unit": "kg",
                "price_range": {"min": 12000, "max": 18000}
            }
        }
        
        self.matcher = ProductMatcher(self.sample_catalog)
    
    def test_product_matcher_init(self):
        """Test ProductMatcher initialization."""
        matcher = ProductMatcher(self.sample_catalog)
        
        assert matcher.catalog == self.sample_catalog
        assert len(matcher.product_names) == 3
        assert "tomato" in matcher.product_names
        assert "chicken" in matcher.product_names
        assert "rice" in matcher.product_names
    
    def test_product_matcher_empty_catalog(self):
        """Test ProductMatcher with empty catalog."""
        matcher = ProductMatcher({})
        
        assert matcher.catalog == {}
        assert matcher.product_names == []
    
    def test_find_best_match_exact(self):
        """Test finding exact product matches."""
        # Exact match
        result = self.matcher.find_best_match("tomato")
        
        assert result["match_found"] is True
        assert result["product_key"] == "tomato"
        assert result["confidence"] >= 0.9
        assert result["match_type"] == "exact"
    
    def test_find_best_match_alias(self):
        """Test finding matches through aliases."""
        # Match through alias
        result = self.matcher.find_best_match("tomat")
        
        assert result["match_found"] is True
        assert result["product_key"] == "tomato"
        assert result["confidence"] >= 0.8
        assert result["match_type"] == "alias"
    
    def test_find_best_match_fuzzy(self):
        """Test fuzzy matching."""
        # Fuzzy match (typo)
        result = self.matcher.find_best_match("tomatoe")  # Extra 'e'
        
        assert result["match_found"] is True
        assert result["product_key"] == "tomato"
        assert result["confidence"] >= 0.7
        assert result["match_type"] == "fuzzy"
    
    def test_find_best_match_no_match(self):
        """Test when no match is found."""
        result = self.matcher.find_best_match("unknown_product")
        
        assert result["match_found"] is False
        assert result["product_key"] is None
        assert result["confidence"] < 0.5
    
    def test_find_best_match_case_insensitive(self):
        """Test case-insensitive matching."""
        test_cases = ["TOMATO", "Tomato", "ToMaTo", "tomato"]
        
        for test_case in test_cases:
            result = self.matcher.find_best_match(test_case)
            assert result["match_found"] is True
            assert result["product_key"] == "tomato"
    
    def test_find_best_match_with_spaces(self):
        """Test matching with extra spaces."""
        test_cases = [" tomato ", "  tomato  ", "\ttomato\n"]
        
        for test_case in test_cases:
            result = self.matcher.find_best_match(test_case)
            assert result["match_found"] is True
            assert result["product_key"] == "tomato"
    
    def test_find_best_match_partial_words(self):
        """Test matching with partial words."""
        # Test compound names
        result = self.matcher.find_best_match("fresh tomato")
        
        # Should still match tomato
        assert result["match_found"] is True
        assert result["product_key"] == "tomato"
    
    def test_fuzzy_match_products_multiple_results(self):
        """Test fuzzy matching returning multiple results."""
        # Query that might match multiple products
        results = self.matcher.fuzzy_match_products("rice", limit=3)
        
        assert len(results) >= 1
        assert all(r["confidence"] > 0 for r in results)
        
        # Results should be sorted by confidence
        confidences = [r["confidence"] for r in results]
        assert confidences == sorted(confidences, reverse=True)
    
    def test_fuzzy_match_products_empty_query(self):
        """Test fuzzy matching with empty query."""
        results = self.matcher.fuzzy_match_products("")
        
        assert len(results) == 0
    
    def test_fuzzy_match_products_limit(self):
        """Test fuzzy matching with result limit."""
        results = self.matcher.fuzzy_match_products("rice", limit=1)
        
        assert len(results) <= 1
    
    def test_normalize_product_name(self):
        """Test product name normalization."""
        test_cases = [
            ("  Tomato  ", "tomato"),
            ("CHICKEN MEAT", "chicken meat"),
            ("Rice-White", "rice white"),
            ("Product_123", "product 123"),
            ("Ürün Adı", "ürün adı"),  # Unicode
        ]
        
        for input_name, expected in test_cases:
            result = normalize_product_name(input_name)
            assert result == expected
    
    def test_calculate_match_confidence_exact(self):
        """Test confidence calculation for exact matches."""
        confidence = calculate_match_confidence("tomato", "tomato", "exact")
        
        assert confidence >= 0.95
        assert confidence <= 1.0
    
    def test_calculate_match_confidence_fuzzy(self):
        """Test confidence calculation for fuzzy matches."""
        # Similar strings
        confidence_high = calculate_match_confidence("tomato", "tomatoe", "fuzzy")
        confidence_low = calculate_match_confidence("tomato", "potato", "fuzzy")
        
        assert confidence_high > confidence_low
        assert 0.5 <= confidence_high <= 0.95
        assert 0.0 <= confidence_low <= 0.8
    
    def test_match_with_price_validation(self):
        """Test product matching with price validation."""
        # Match with price in expected range
        result = self.matcher.find_best_match_with_price("tomato", 12000)
        
        assert result["match_found"] is True
        assert result["price_valid"] is True
        
        # Match with price out of range
        result = self.matcher.find_best_match_with_price("tomato", 50000)
        
        assert result["match_found"] is True
        assert result["price_valid"] is False
        assert "price_warning" in result
    
    def test_match_batch_products(self):
        """Test batch product matching."""
        product_list = [
            {"name": "tomato", "price": 12000},
            {"name": "chickn", "price": 30000},  # Typo
            {"name": "unknown_item", "price": 5000}
        ]
        
        results = self.matcher.match_batch(product_list)
        
        assert len(results) == 3
        assert results[0]["match_found"] is True  # tomato
        assert results[1]["match_found"] is True  # chicken (corrected)
        assert results[2]["match_found"] is False  # unknown


class TestSupplierMatcher:
    """Test suite for SupplierMatcher class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.sample_mappings = {
            "test_supplier_ltd": {
                "canonical_name": "Test Supplier Ltd",
                "aliases": ["test supplier", "test supp", "тест поставщик"],
                "category": "wholesale",
                "confidence": 0.95
            },
            "fresh_market": {
                "canonical_name": "Fresh Market Indonesia",
                "aliases": ["fresh market", "fm", "фреш маркет"],
                "category": "retail",
                "confidence": 0.90
            }
        }
        
        self.matcher = SupplierMatcher(self.sample_mappings)
    
    def test_supplier_matcher_init(self):
        """Test SupplierMatcher initialization."""
        matcher = SupplierMatcher(self.sample_mappings)
        
        assert matcher.mappings == self.sample_mappings
        assert len(matcher.supplier_names) == 2
    
    def test_match_supplier_exact(self):
        """Test exact supplier matching."""
        result = self.matcher.match_supplier("test_supplier_ltd")
        
        assert result["match_found"] is True
        assert result["canonical_name"] == "Test Supplier Ltd"
        assert result["confidence"] >= 0.9
    
    def test_match_supplier_alias(self):
        """Test supplier matching through aliases."""
        result = self.matcher.match_supplier("test supplier")
        
        assert result["match_found"] is True
        assert result["canonical_name"] == "Test Supplier Ltd"
        assert result["confidence"] >= 0.8
    
    def test_match_supplier_fuzzy(self):
        """Test fuzzy supplier matching."""
        result = self.matcher.match_supplier("test suppliers ltd")  # Plural
        
        assert result["match_found"] is True
        assert result["canonical_name"] == "Test Supplier Ltd"
        assert result["confidence"] >= 0.7
    
    def test_match_supplier_no_match(self):
        """Test when no supplier match is found."""
        result = self.matcher.match_supplier("unknown supplier")
        
        assert result["match_found"] is False
        assert result["canonical_name"] is None
    
    def test_match_supplier_case_insensitive(self):
        """Test case-insensitive supplier matching."""
        test_cases = ["FRESH MARKET", "Fresh Market", "fresh market"]
        
        for test_case in test_cases:
            result = self.matcher.match_supplier(test_case)
            assert result["match_found"] is True
            assert result["canonical_name"] == "Fresh Market Indonesia"


class TestMatcherUtilities:
    """Test utility functions in matcher module."""
    
    def test_load_product_catalog_valid_file(self):
        """Test loading valid product catalog."""
        sample_catalog_json = json.dumps({
            "tomato": {
                "name": "Fresh Tomatoes",
                "category": "vegetables"
            }
        })
        
        with patch("builtins.open", mock_open(read_data=sample_catalog_json)):
            with patch("os.path.exists", return_value=True):
                catalog = load_product_catalog("fake_path.json")
                
                assert "tomato" in catalog
                assert catalog["tomato"]["name"] == "Fresh Tomatoes"
    
    def test_load_product_catalog_missing_file(self):
        """Test loading product catalog when file doesn't exist."""
        with patch("os.path.exists", return_value=False):
            catalog = load_product_catalog("nonexistent_path.json")
            
            assert catalog == {}
    
    def test_load_product_catalog_invalid_json(self):
        """Test loading product catalog with invalid JSON."""
        invalid_json = "{ invalid json content"
        
        with patch("builtins.open", mock_open(read_data=invalid_json)):
            with patch("os.path.exists", return_value=True):
                catalog = load_product_catalog("fake_path.json")
                
                assert catalog == {}
    
    def test_load_supplier_mappings_valid_file(self):
        """Test loading valid supplier mappings."""
        sample_mappings_json = json.dumps({
            "test_supplier": {
                "canonical_name": "Test Supplier Ltd"
            }
        })
        
        with patch("builtins.open", mock_open(read_data=sample_mappings_json)):
            with patch("os.path.exists", return_value=True):
                mappings = load_supplier_mappings("fake_path.json")
                
                assert "test_supplier" in mappings
                assert mappings["test_supplier"]["canonical_name"] == "Test Supplier Ltd"
    
    def test_load_supplier_mappings_missing_file(self):
        """Test loading supplier mappings when file doesn't exist."""
        with patch("os.path.exists", return_value=False):
            mappings = load_supplier_mappings("nonexistent_path.json")
            
            assert mappings == {}
    
    def test_normalize_product_name_edge_cases(self):
        """Test product name normalization edge cases."""
        edge_cases = [
            ("", ""),
            ("   ", ""),
            ("123", "123"),
            ("!@#$%", ""),
            ("Ñoño", "ñoño"),  # Spanish characters
            ("Café", "café"),  # Accented characters
        ]
        
        for input_name, expected in edge_cases:
            result = normalize_product_name(input_name)
            assert result == expected
    
    def test_calculate_match_confidence_edge_cases(self):
        """Test confidence calculation edge cases."""
        # Empty strings
        confidence = calculate_match_confidence("", "", "exact")
        assert confidence == 0.0
        
        # Very different strings
        confidence = calculate_match_confidence("apple", "zebra", "fuzzy")
        assert confidence < 0.3
        
        # Identical strings
        confidence = calculate_match_confidence("test", "test", "exact")
        assert confidence == 1.0


class TestMatcherIntegration:
    """Integration tests for matcher components."""
    
    def setup_method(self):
        """Set up integration test fixtures."""
        self.sample_invoice_data = {
            "supplier": "test supplier",
            "lines": [
                {"name": "tomat", "qty": 2, "price": 12000},
                {"name": "chickn", "qty": 1, "price": 30000},
                {"name": "unknown_product", "qty": 1, "price": 5000}
            ]
        }
    
    def test_match_complete_invoice(self):
        """Test matching a complete invoice."""
        with patch('app.matcher.load_product_catalog') as mock_load_products, \
             patch('app.matcher.load_supplier_mappings') as mock_load_suppliers:
            
            # Mock catalog and mappings
            mock_load_products.return_value = {
                "tomato": {"name": "Fresh Tomatoes", "aliases": ["tomat"]},
                "chicken": {"name": "Chicken Meat", "aliases": ["chickn"]}
            }
            
            mock_load_suppliers.return_value = {
                "test_supplier": {"canonical_name": "Test Supplier Ltd"}
            }
            
            # Process invoice
            product_matcher = ProductMatcher(mock_load_products.return_value)
            supplier_matcher = SupplierMatcher(mock_load_suppliers.return_value)
            
            # Match supplier
            supplier_result = supplier_matcher.match_supplier(self.sample_invoice_data["supplier"])
            assert supplier_result["match_found"] is True
            
            # Match products
            matched_lines = []
            for line in self.sample_invoice_data["lines"]:
                match_result = product_matcher.find_best_match(line["name"])
                line_with_match = line.copy()
                line_with_match["match_result"] = match_result
                matched_lines.append(line_with_match)
            
            # Verify results
            assert matched_lines[0]["match_result"]["match_found"] is True  # tomato
            assert matched_lines[1]["match_result"]["match_found"] is True  # chicken
            assert matched_lines[2]["match_result"]["match_found"] is False  # unknown
    
    def test_batch_processing_performance(self):
        """Test performance of batch processing."""
        # Create large product list
        large_product_list = [
            {"name": f"product_{i}", "price": 1000 + i}
            for i in range(100)
        ]
        
        catalog = {
            f"product_{i}": {"name": f"Product {i}", "category": "test"}
            for i in range(0, 100, 10)  # Every 10th product exists in catalog
        }
        
        matcher = ProductMatcher(catalog)
        
        # Should complete in reasonable time
        import time
        start_time = time.time()
        
        results = matcher.match_batch(large_product_list)
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        # Should process 100 items in under 1 second
        assert processing_time < 1.0
        assert len(results) == 100
    
    def test_multilingual_matching(self):
        """Test matching across multiple languages."""
        multilingual_catalog = {
            "tomato": {
                "name": "Tomato",
                "aliases": ["tomato", "tomat", "помидор", "ντομάτα", "टमाटर"]
            },
            "chicken": {
                "name": "Chicken",
                "aliases": ["chicken", "ayam", "курица", "κοτόπουλο", "मुर्गी"]
            }
        }
        
        matcher = ProductMatcher(multilingual_catalog)
        
        # Test different language matches
        test_cases = [
            ("помидор", "tomato"),  # Russian
            ("ayam", "chicken"),     # Indonesian
            ("टमाटर", "tomato"),      # Hindi
        ]
        
        for query, expected_key in test_cases:
            result = matcher.find_best_match(query)
            assert result["match_found"] is True
            assert result["product_key"] == expected_key


class TestMatcherErrorHandling:
    """Test error handling in matcher components."""
    
    def test_handle_corrupted_catalog_data(self):
        """Test handling of corrupted catalog data."""
        corrupted_catalogs = [
            None,
            {"invalid": "structure"},
            {"product1": None},
            {"product2": {"invalid": "no_name_field"}},
            {"product3": {"name": None}},
        ]
        
        for catalog in corrupted_catalogs:
            try:
                matcher = ProductMatcher(catalog)
                result = matcher.find_best_match("test")
                
                # Should handle gracefully
                assert "match_found" in result
                assert isinstance(result["match_found"], bool)
            except Exception as e:
                # If exception occurs, should be handled gracefully
                assert "catalog" in str(e).lower() or "invalid" in str(e).lower()
    
    def test_handle_extreme_input_values(self):
        """Test handling of extreme input values."""
        catalog = {"normal_product": {"name": "Normal Product"}}
        matcher = ProductMatcher(catalog)
        
        extreme_inputs = [
            "",  # Empty string
            " " * 1000,  # Very long spaces
            "a" * 1000,  # Very long string
            "спецсимволы!@#$%^&*()",  # Special characters
            "🍎🍌🍇",  # Emoji
            "\n\t\r",  # Control characters
        ]
        
        for extreme_input in extreme_inputs:
            result = matcher.find_best_match(extreme_input)
            
            # Should handle without crashing
            assert "match_found" in result
            assert isinstance(result["match_found"], bool)
    
    def test_handle_memory_efficient_processing(self):
        """Test memory-efficient processing of large datasets."""
        # Create very large catalog
        large_catalog = {
            f"product_{i:06d}": {
                "name": f"Product {i}",
                "category": "test",
                "aliases": [f"prod_{i}", f"item_{i}"]
            }
            for i in range(1000)  # 1000 products
        }
        
        matcher = ProductMatcher(large_catalog)
        
        # Should handle without memory issues
        result = matcher.find_best_match("product_000500")
        assert result["match_found"] is True
        
        # Test batch processing
        test_queries = [f"product_{i:06d}" for i in range(0, 100, 10)]
        batch_results = []
        
        for query in test_queries:
            result = matcher.find_best_match(query)
            batch_results.append(result)
        
        assert len(batch_results) == 10
        assert all(r["match_found"] for r in batch_results)


if __name__ == "__main__":
    pytest.main([__file__])