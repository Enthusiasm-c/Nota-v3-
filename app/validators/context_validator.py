"""
Context-aware price validation for Indonesian restaurant supplies.

This module provides validation based on typical price ranges for different
categories of products in the Indonesian market, helping to catch OCR errors
that result in unrealistic prices.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ContextAwarePriceValidator:
    """
    Validates prices based on product category and typical Indonesian market prices.
    
    Uses fuzzy matching to categorize products and validate their prices against
    realistic ranges for restaurant supplies in Indonesia.
    """

    def __init__(self):
        """Initialize the context-aware price validator."""
        # Price ranges in Indonesian Rupiah per common units
        self.price_ranges = {
            # Fresh vegetables (per kg)
            "vegetables": {
                "unit": "kg",
                "min_price": 3_000,
                "max_price": 50_000,
                "typical_min": 8_000,
                "typical_max": 35_000,
                "products": [
                    "tomato", "potato", "carrot", "onion", "cucumber", "zucchini",
                    "eggplant", "spinach", "broccoli", "paprika", "lettuce", "romaine",
                    "kale", "cabbage", "mushroom", "radish", "garlic", "ginger",
                    "chili", "bell pepper", "corn", "beans"
                ]
            },
            
            # Fresh fruits (per kg)
            "fruits": {
                "unit": "kg", 
                "min_price": 5_000,
                "max_price": 80_000,
                "typical_min": 12_000,
                "typical_max": 60_000,
                "products": [
                    "apple", "orange", "banana", "grape", "strawberry", "mango",
                    "pineapple", "lemon", "lime", "watermelon", "dragon fruit",
                    "papaya", "avocado", "coconut"
                ]
            },
            
            # Meat and poultry (per kg)
            "meat": {
                "unit": "kg",
                "min_price": 25_000,
                "max_price": 200_000,
                "typical_min": 40_000,
                "typical_max": 150_000,
                "products": [
                    "beef", "chicken", "pork", "lamb", "sausage", "bacon", "ham",
                    "tenderloin", "breast", "thigh", "wing", "ground beef"
                ]
            },
            
            # Seafood (per kg)
            "seafood": {
                "unit": "kg",
                "min_price": 20_000,
                "max_price": 300_000,
                "typical_min": 35_000,
                "typical_max": 200_000,
                "products": [
                    "fish", "salmon", "tuna", "shrimp", "prawn", "crab", "lobster",
                    "mussel", "oyster", "squid", "octopus", "mackerel"
                ]
            },
            
            # Dairy products (per piece/package)
            "dairy": {
                "unit": "pcs",
                "min_price": 5_000,
                "max_price": 100_000,
                "typical_min": 8_000,
                "typical_max": 75_000,
                "products": [
                    "milk", "cheese", "yogurt", "butter", "cream", "mascarpone",
                    "ricotta", "mozzarella", "emmental", "cheddar", "feta"
                ]
            },
            
            # Beverages (per bottle/can)
            "beverages": {
                "unit": "pcs",
                "min_price": 2_000,
                "max_price": 50_000,
                "typical_min": 3_000,
                "typical_max": 25_000,
                "products": [
                    "water", "juice", "soda", "tea", "coffee", "cola", "beer",
                    "wine", "sprite", "fanta"
                ]
            },
            
            # Spices and seasonings (per pack/gram)
            "spices": {
                "unit": "g",
                "min_price": 50,
                "max_price": 500,
                "typical_min": 100,
                "typical_max": 350,
                "products": [
                    "salt", "pepper", "cumin", "paprika", "oregano", "basil",
                    "thyme", "cinnamon", "turmeric", "coriander"
                ]
            },
            
            # Grains and staples (per kg)
            "grains": {
                "unit": "kg",
                "min_price": 8_000,
                "max_price": 50_000,
                "typical_min": 12_000,
                "typical_max": 35_000,
                "products": [
                    "rice", "pasta", "noodle", "flour", "oat", "quinoa",
                    "buckwheat", "bread", "cereal"
                ]
            },
            
            # Oils and sauces (per bottle)
            "oils_sauces": {
                "unit": "btl",
                "min_price": 8_000,
                "max_price": 80_000,
                "typical_min": 15_000,
                "typical_max": 60_000,
                "products": [
                    "olive oil", "sunflower oil", "vegetable oil", "sesame oil",
                    "ketchup", "mayonnaise", "mustard", "soy sauce", "vinegar",
                    "worcestershire", "hot sauce"
                ]
            }
        }

    def categorize_product(self, product_name: str) -> Optional[str]:
        """
        Categorize a product based on its name.
        
        Args:
            product_name: Name of the product
            
        Returns:
            Category name if found, None otherwise
        """
        if not product_name:
            return None
            
        product_lower = product_name.lower().strip()
        
        # Check each category for matches
        for category, info in self.price_ranges.items():
            for known_product in info["products"]:
                if known_product.lower() in product_lower or product_lower in known_product.lower():
                    return category
                    
        # Additional fuzzy matching for common variations
        for category, info in self.price_ranges.items():
            for known_product in info["products"]:
                # Simple fuzzy matching - check if words overlap
                product_words = set(product_lower.split())
                known_words = set(known_product.lower().split())
                
                # If more than half the words match, consider it a match
                if product_words and known_words:
                    overlap = len(product_words.intersection(known_words))
                    min_words = min(len(product_words), len(known_words))
                    if overlap / min_words >= 0.6:
                        return category
        
        return None

    def validate_price(self, product_name: str, price: float, 
                      unit: str = None, quantity: float = 1.0) -> Dict[str, Any]:
        """
        Validate price for a product based on its category and typical market prices.
        
        Args:
            product_name: Name of the product
            price: Unit price in IDR
            unit: Unit of measurement (kg, pcs, etc.)
            quantity: Quantity (for calculating total price validation)
            
        Returns:
            Dictionary with validation results
        """
        result = {
            "valid": True,
            "warnings": [],
            "category": None,
            "suggested_price_range": None,
            "confidence": "unknown"
        }
        
        if not product_name or not price or price <= 0:
            return result
        
        # Categorize the product
        category = self.categorize_product(product_name)
        result["category"] = category
        
        if not category:
            # Unknown product - apply general validation
            if price < 1_000:
                result["warnings"].append(
                    f"Very low price {price:,.0f} IDR - possible OCR error"
                )
                result["confidence"] = "low"
            elif price > 500_000:
                result["warnings"].append(
                    f"Very high price {price:,.0f} IDR - verify correctness"
                )
                result["confidence"] = "low"
            else:
                result["confidence"] = "medium"
            return result
        
        # Get price range for the category
        price_info = self.price_ranges[category]
        result["suggested_price_range"] = {
            "min": price_info["typical_min"],
            "max": price_info["typical_max"],
            "unit": price_info["unit"]
        }
        
        # Normalize price to expected unit if necessary
        normalized_price = self._normalize_price_to_unit(price, unit, price_info["unit"])
        
        # Validate against category ranges
        if normalized_price < price_info["min_price"]:
            result["warnings"].append(
                f"Unusually low price for {category}: {normalized_price:,.0f} IDR/{price_info['unit']} "
                f"(expected: {price_info['typical_min']:,.0f}-{price_info['typical_max']:,.0f})"
            )
            result["confidence"] = "low"
            result["valid"] = False
            
        elif normalized_price > price_info["max_price"]:
            result["warnings"].append(
                f"Unusually high price for {category}: {normalized_price:,.0f} IDR/{price_info['unit']} "
                f"(expected: {price_info['typical_min']:,.0f}-{price_info['typical_max']:,.0f})"
            )
            result["confidence"] = "low"
            result["valid"] = False
            
        elif (normalized_price < price_info["typical_min"] or 
              normalized_price > price_info["typical_max"]):
            result["warnings"].append(
                f"Price outside typical range for {category}: {normalized_price:,.0f} IDR/{price_info['unit']} "
                f"(typical: {price_info['typical_min']:,.0f}-{price_info['typical_max']:,.0f})"
            )
            result["confidence"] = "medium"
            
        else:
            result["confidence"] = "high"
        
        return result

    def _normalize_price_to_unit(self, price: float, actual_unit: str, 
                                expected_unit: str) -> float:
        """
        Normalize price to the expected unit for comparison.
        
        Args:
            price: Original price
            actual_unit: Actual unit from OCR
            expected_unit: Expected unit for the category
            
        Returns:
            Price normalized to expected unit
        """
        if not actual_unit or actual_unit.lower() == expected_unit.lower():
            return price
        
        # Unit conversion factors
        conversions = {
            ("g", "kg"): 1000,  # 1 kg = 1000 g
            ("kg", "g"): 0.001,
            ("ml", "l"): 1000,  # 1 l = 1000 ml
            ("l", "ml"): 0.001,
        }
        
        conversion_key = (actual_unit.lower(), expected_unit.lower())
        if conversion_key in conversions:
            return price * conversions[conversion_key]
        
        # If no conversion available, return original price
        return price

    def validate_invoice_context(self, positions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Validate entire invoice for contextual consistency.
        
        Args:
            positions: List of invoice positions
            
        Returns:
            Dictionary with overall validation results
        """
        result = {
            "overall_valid": True,
            "total_warnings": 0,
            "category_distribution": {},
            "price_confidence": "unknown",
            "suggested_fixes": []
        }
        
        if not positions:
            return result
        
        high_confidence_count = 0
        medium_confidence_count = 0
        low_confidence_count = 0
        category_counts = {}
        
        # Validate each position
        for i, pos in enumerate(positions):
            product_name = pos.get("name", "")
            price = pos.get("price", 0)
            unit = pos.get("unit", "")
            qty = pos.get("qty", 1)
            
            if not price:
                continue
                
            validation = self.validate_price(product_name, price, unit, qty)
            
            # Count confidence levels
            if validation["confidence"] == "high":
                high_confidence_count += 1
            elif validation["confidence"] == "medium":
                medium_confidence_count += 1
            else:
                low_confidence_count += 1
            
            # Count categories
            if validation["category"]:
                category_counts[validation["category"]] = category_counts.get(validation["category"], 0) + 1
            
            # Collect warnings
            if validation["warnings"]:
                result["total_warnings"] += len(validation["warnings"])
                if not validation["valid"]:
                    result["overall_valid"] = False
                    result["suggested_fixes"].append({
                        "position": i + 1,
                        "product": product_name,
                        "issue": validation["warnings"][0],
                        "suggested_range": validation.get("suggested_price_range")
                    })
        
        # Determine overall confidence
        total_positions = len(positions)
        if high_confidence_count / total_positions >= 0.7:
            result["price_confidence"] = "high"
        elif (high_confidence_count + medium_confidence_count) / total_positions >= 0.5:
            result["price_confidence"] = "medium"
        else:
            result["price_confidence"] = "low"
        
        result["category_distribution"] = category_counts
        
        # Add recommendations based on validation results
        if result["total_warnings"] > 0:
            result["recommendations"] = self._generate_recommendations(result)
        
        return result

    def _generate_recommendations(self, validation_result: Dict[str, Any]) -> List[str]:
        """
        Generate recommendations based on validation results.
        
        Args:
            validation_result: Results from validate_invoice_context
            
        Returns:
            List of recommendation strings
        """
        recommendations = []
        
        if validation_result["price_confidence"] == "low":
            recommendations.append(
                "Low price confidence detected. Review OCR results carefully for number recognition errors."
            )
        
        if validation_result["total_warnings"] > 3:
            recommendations.append(
                "Multiple price warnings detected. Consider re-scanning the image or manually verifying prices."
            )
        
        if validation_result["suggested_fixes"]:
            recommendations.append(
                f"Review {len(validation_result['suggested_fixes'])} positions with price anomalies."
            )
        
        return recommendations


def validate_prices_with_context(invoice_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convenience function to validate invoice prices with context awareness.
    
    Args:
        invoice_data: Invoice data dictionary
        
    Returns:
        Enhanced invoice data with context validation results
    """
    validator = ContextAwarePriceValidator()
    
    # Get positions from various possible formats
    positions = invoice_data.get("positions", invoice_data.get("lines", []))
    
    if not positions:
        return invoice_data
    
    # Validate individual positions
    validated_positions = []
    for pos in positions:
        validated_pos = pos.copy()
        
        # Run context validation
        context_validation = validator.validate_price(
            product_name=pos.get("name", ""),
            price=pos.get("price", 0),
            unit=pos.get("unit", ""),
            quantity=pos.get("qty", 1)
        )
        
        # Add context validation results
        validated_pos["context_validation"] = context_validation
        if context_validation["warnings"]:
            existing_warnings = validated_pos.get("validation_warnings", [])
            existing_warnings.extend(context_validation["warnings"])
            validated_pos["validation_warnings"] = existing_warnings
        
        validated_positions.append(validated_pos)
    
    # Validate overall invoice context
    invoice_context_validation = validator.validate_invoice_context(validated_positions)
    
    # Update invoice data
    result = invoice_data.copy()
    result["positions"] = validated_positions
    result["context_validation"] = invoice_context_validation
    
    # Update overall validation status if context validation failed
    if not invoice_context_validation["overall_valid"]:
        result["validation_passed"] = False
        
        # Add context warnings to overall issues
        existing_issues = result.get("validation_warnings", [])
        if invoice_context_validation.get("recommendations"):
            existing_issues.extend(invoice_context_validation["recommendations"])
        result["validation_warnings"] = existing_issues
    
    return result