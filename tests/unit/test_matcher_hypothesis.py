"""
Property-based tests for the matcher module using Hypothesis.

These tests verify matcher functionality with a wide range of inputs
including edge cases and corner cases.
"""
import pytest
from hypothesis import given, settings, strategies as st, example, assume, HealthCheck
from typing import Dict, List, Optional

from app.matcher import (
    normalize_product_name,
    calculate_string_similarity,
    fuzzy_find,
    fuzzy_best,
    match_supplier,
    match_positions
)

# Define strategies for testing
# For product names - generate regular strings, special chars, single letter words, etc.
product_names = st.one_of(
    st.text(min_size=1, max_size=50),  # Regular strings
    st.lists(st.text(min_size=1, max_size=10), min_size=1, max_size=5).map(" ".join),  # Multi-word strings
    st.sampled_from([
        "a", "b", "c",  # Single letter words
        "an", "to", "of",  # Common short words
        "a a", "a b", "c d",  # Combinations of short words
        "potato potatoes",  # Singular/plural in same string
        "tomato, tomatoes",  # With punctuation
        "bean/beans",  # With slash
        " extra spaces  ",  # Extra whitespace
        "Mixed CASE text",  # Mixed case
        "chick peas",  # Known variant
        "green-beans",  # Hyphenated
        "10K rice",  # With numbers
    ])
)

# Strategy for generating supplier dictionaries
supplier_dict = st.fixed_dictionaries({
    "name": st.text(min_size=1, max_size=30),
    "id": st.one_of(st.integers(min_value=1, max_value=1000), st.uuids().map(str)),
    "code": st.text(min_size=1, max_size=10).map(lambda s: s.upper())
})

# Strategy for generating product dictionaries
product_dict = st.fixed_dictionaries({
    "name": product_names,
    "id": st.one_of(st.integers(min_value=1, max_value=1000), st.uuids().map(str))
})

# Strategy for generating invoice line items
line_item_dict = st.fixed_dictionaries({
    "name": product_names,
    "qty": st.one_of(st.integers(min_value=1, max_value=100), st.floats(min_value=0.1, max_value=100.0)),
    "unit": st.sampled_from(["pcs", "kg", "g", "box", "set", "carton", "bag", "each", "unit"]),
    "price": st.floats(min_value=0.01, max_value=1000.0),
    "amount": st.floats(min_value=0.01, max_value=10000.0)
})


@given(name=product_names)
@settings(max_examples=100)
def test_normalize_product_name_properties(name):
    """Test that normalize_product_name has expected properties."""
    result = normalize_product_name(name)
    
    # Result should always be a string
    assert isinstance(result, str)
    
    # Function should be idempotent
    assert normalize_product_name(result) == result
    
    # Normalization should lowercase
    assert result == result.lower()
    
    # Normalization should strip whitespace
    assert result == result.strip()
    
    # Known plural forms should be converted to singular
    if "tomatoes" in name.lower():
        assert "tomato" in result
    
    # Known variants should be normalized
    if "chickpeas" in name.lower() or "chick peas" in name.lower():
        assert "chickpea" in result or "chickpeas" in result


@given(s1=st.text(min_size=1, max_size=20, alphabet='abcdefghijklmnopqrstuvwxyz'),
       s2=st.text(min_size=1, max_size=20, alphabet='abcdefghijklmnopqrstuvwxyz'))
@settings(max_examples=50, suppress_health_check=[HealthCheck.filter_too_much])
def test_calculate_string_similarity_properties(s1, s2):
    """Test that calculate_string_similarity has expected properties."""
    # Using Latin lowercase alphabet only which simplifies case conversion tests
    
    similarity = calculate_string_similarity(s1, s2)
    
    # Similarity should be between 0 and 1
    assert 0 <= similarity <= 1
    
    # Similarity should be symmetric
    assert calculate_string_similarity(s1, s2) == calculate_string_similarity(s2, s1)
    
    # Identical non-empty strings should have similarity 1.0
    assert calculate_string_similarity(s1, s1) == 1.0
    assert calculate_string_similarity(s2, s2) == 1.0
    
    # Test empty string handling separately
    if s1:
        assert calculate_string_similarity("", s1) == 0.0
        assert calculate_string_similarity(s1, "") == 0.0
    
    # Case insensitivity for ASCII characters
    lower_sim = calculate_string_similarity(s1.lower(), s2)
    upper_sim = calculate_string_similarity(s1.upper(), s2)
    # For ASCII characters, case shouldn't matter much
    assert abs(lower_sim - upper_sim) < 0.1


@given(s1=st.text(min_size=1, max_size=30), 
       s2=st.text(min_size=1, max_size=30))
@settings(max_examples=50)
def test_string_similarity_edge_cases(s1, s2):
    """Test edge cases for string similarity calculation."""
    # Test with special characters
    special_s1 = f"!@#${s1}%^&*"
    special_s2 = f"!@#${s2}%^&*"
    
    # Special characters should affect similarity
    similarity_normal = calculate_string_similarity(s1, s2)
    similarity_special = calculate_string_similarity(special_s1, special_s2)
    
    # If original strings are the same, similarity with special chars should still be high
    if s1 == s2:
        assert similarity_special > 0.7
    
    # Test with whitespace variations
    padded_s1 = f"  {s1}  "
    padded_s2 = f"  {s2}  "
    
    # Whitespace should be normalized, so similarity should be the same
    assert calculate_string_similarity(s1, s2) == calculate_string_similarity(padded_s1, padded_s2)


@given(query=product_names, 
       products=st.lists(product_dict, min_size=1, max_size=30))
@settings(max_examples=50)
def test_fuzzy_find_properties(query, products):
    """Test that fuzzy_find has expected properties."""
    results = fuzzy_find(query, products)
    
    # Results should be a list
    assert isinstance(results, list)
    
    # Each result should have name, id, and score
    for result in results:
        assert isinstance(result, dict)
        assert "name" in result
        assert "id" in result
        assert "score" in result
        
        # Score should be between 0 and 1
        assert 0 <= result["score"] <= 1
    
    # Results should be in descending order of score
    for i in range(1, len(results)):
        assert results[i-1]["score"] >= results[i]["score"]
    
    # Empty query or products should return empty list
    assert fuzzy_find("", products) == []
    assert fuzzy_find(query, []) == []


@given(catalog=st.dictionaries(
           keys=st.text(min_size=1, max_size=30),
           values=st.text(min_size=1, max_size=30),
           min_size=1, max_size=1000),
       name=product_names)
@settings(max_examples=30)
def test_fuzzy_best_with_large_catalog(catalog, name):
    """Test fuzzy_best with a large catalog (up to 1000 items)."""
    best, score = fuzzy_best(name, catalog)
    
    # Result should be a tuple of (string, float)
    assert isinstance(best, str)
    assert isinstance(score, float)
    
    # Score should be between 0 and 100
    assert 0 <= score <= 100
    
    # If name exactly matches an entry in catalog, score should be 100
    if name in catalog:
        assert score == 100
        
    # If we got a match with score > 0, it should be a key in the catalog
    if score > 0 and best:
        assert best in catalog
        
    # Test with exact match in the catalog
    if catalog:
        exact_key = next(iter(catalog.keys()))
        exact_match, exact_score = fuzzy_best(exact_key, catalog)
        assert exact_match == exact_key
        assert exact_score == 100


@given(supplier_name=st.text(min_size=1, max_size=30), 
       suppliers=st.lists(supplier_dict, min_size=1, max_size=10))
@settings(max_examples=50)
def test_match_supplier_properties(supplier_name, suppliers):
    """Test that match_supplier has expected properties."""
    result = match_supplier(supplier_name, suppliers)
    
    # Result should be a dictionary
    assert isinstance(result, dict)
    
    # Result should have required keys
    assert "name" in result
    assert "id" in result
    assert "status" in result
    
    # Status should be one of "ok" or "unknown"
    assert result["status"] in ["ok", "unknown"]
    
    # If status is "ok", id should not be None and score should be >= threshold
    if result["status"] == "ok":
        assert result["id"] is not None
        assert result.get("score", 0) >= 0.9
    
    # If supplier name exactly matches a supplier, status should be "ok"
    for supplier in suppliers:
        if supplier_name.lower() == supplier["name"].lower():
            assert result["status"] == "ok"
            assert result["id"] == supplier["id"]
            break


@given(positions=st.lists(line_item_dict, min_size=1, max_size=5),
       products=st.lists(product_dict, min_size=1, max_size=10),
       threshold=st.floats(min_value=0.5, max_value=0.95))
@settings(max_examples=30)
def test_match_positions_properties(positions, products, threshold):
    """Test that match_positions has expected properties."""
    results = match_positions(positions, products, threshold)
    
    # Results should be a list of the same length as positions
    assert isinstance(results, list)
    assert len(results) == len(positions)
    
    # Each result should have required keys
    for result in results:
        assert isinstance(result, dict)
        assert "name" in result
        assert "qty" in result
        assert "unit" in result
        assert "status" in result
        
        # Status should be one of "ok", "partial", or "unknown"
        assert result["status"] in ["ok", "partial", "unknown"]
        
        # If status is "ok" or "partial", score should be >= threshold
        if result["status"] in ["ok", "partial"]:
            assert result.get("score", 0) >= threshold
            assert "matched_name" in result
    
    # Test with suggestions enabled
    results_with_suggestions = match_positions(positions, products, threshold, return_suggestions=True)
    
    # Unknown items should have suggestions if enabled
    for result in results_with_suggestions:
        if result["status"] == "unknown":
            assert "suggestions" in result


@given(s1=st.text(min_size=1, max_size=1, alphabet=st.characters(blacklist_categories=('Cs',))),  # Single character strings
       s2=st.text(min_size=1, max_size=1, alphabet=st.characters(blacklist_categories=('Cs',))))  # Single character strings
@settings(max_examples=30)
def test_similarity_with_single_char_words(s1, s2):
    """Test that similarity calculation works properly with single character words."""
    # Skip whitespace characters which can have unexpected similarity
    assume(not s1.isspace() and not s2.isspace())
    
    similarity = calculate_string_similarity(s1, s2)
    
    # Similarity should be between 0 and 1
    assert 0 <= similarity <= 1
    
    # Identical characters should have similarity 1.0
    if s1 == s2:
        assert similarity == 1.0
    elif s1.isalnum() and s2.isalnum():
        # For alphanumeric characters, different chars should have lower similarity
        # Note: Some fuzzy matching algorithms might still find similarity between certain chars
        assert similarity < 0.9


# Examples that test specific edge cases
@example(name1="tomatoes", name2="tomato")
@example(name1="beans", name2="bean")
@example(name1="chick peas", name2="chickpeas")
@example(name1="green bean", name2="green beans")
@example(name1="eggplant", name2="aubergine")
@given(name1=product_names, name2=product_names)
@settings(max_examples=30)
def test_known_product_variants(name1, name2):
    """Test that known product variants have high similarity."""
    # Skip examples where either name is empty
    assume(name1 and name2)
    
    similarity = calculate_string_similarity(name1, name2)
    
    # Check specific cases
    if (name1.lower() == "tomatoes" and name2.lower() == "tomato") or \
       (name1.lower() == "tomato" and name2.lower() == "tomatoes"):
        assert similarity >= 0.9
        
    if (name1.lower() == "beans" and name2.lower() == "bean") or \
       (name1.lower() == "bean" and name2.lower() == "beans"):
        assert similarity >= 0.9
        
    if (name1.lower() == "chick peas" and name2.lower() == "chickpeas") or \
       (name1.lower() == "chickpeas" and name2.lower() == "chick peas"):
        assert similarity >= 0.9
        
    if (name1.lower() == "green bean" and name2.lower() == "green beans") or \
       (name1.lower() == "green beans" and name2.lower() == "green bean"):
        assert similarity >= 0.9
        
    if (name1.lower() == "eggplant" and name2.lower() == "aubergine") or \
       (name1.lower() == "aubergine" and name2.lower() == "eggplant"):
        assert similarity >= 0.9