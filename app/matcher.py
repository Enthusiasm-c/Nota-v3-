import logging
from typing import List, Dict, Optional
try:
    # The python-Levenshtein package provides a fast C implementation
    from Levenshtein import ratio as levenshtein_ratio, distance as levenshtein_distance
    USE_LEVENSHTEIN = True
except ImportError:
    # Fall back to Python's difflib if Levenshtein package is not available
    from difflib import SequenceMatcher
    
    def levenshtein_ratio(a: str, b: str) -> float:
        """
        Fallback implementation using Python's SequenceMatcher.
        Note: This is significantly slower than python-Levenshtein for large strings.
        
        Args:
            a: First string to compare
            b: Second string to compare
            
        Returns:
            float: Similarity ratio between 0.0 and 1.0
        """
        return SequenceMatcher(None, a, b).ratio()
    
    # Stub for levenshtein_distance when Levenshtein package is not available
    def levenshtein_distance(a: str, b: str) -> int:
        """
        Fallback implementation of Levenshtein distance.
        This is a simple dynamic programming implementation.
        
        Args:
            a: First string to compare 
            b: Second string to compare
            
        Returns:
            int: Edit distance between strings
        """
        if a == b:
            return 0
        if len(a) == 0:
            return len(b)
        if len(b) == 0:
            return len(a)
            
        # Initialize matrix of size (len(a)+1, len(b)+1)
        matrix = [[0 for _ in range(len(b) + 1)] for _ in range(len(a) + 1)]
        
        # Fill the first row and column
        for i in range(len(a) + 1):
            matrix[i][0] = i
        for j in range(len(b) + 1):
            matrix[0][j] = j
            
        # Fill the rest of the matrix
        for i in range(1, len(a) + 1):
            for j in range(1, len(b) + 1):
                cost = 0 if a[i-1] == b[j-1] else 1
                matrix[i][j] = min(
                    matrix[i-1][j] + 1,      # deletion
                    matrix[i][j-1] + 1,      # insertion
                    matrix[i-1][j-1] + cost  # substitution
                )
                
        return matrix[len(a)][len(b)]
    
    USE_LEVENSHTEIN = False

from app.config import settings

logger = logging.getLogger(__name__)

def get_normalized_strings(s1: str, s2: str) -> tuple[str, str]:
    """
    Normalize strings for better comparison by removing common noise.
    
    Args:
        s1: First string to normalize
        s2: Second string to normalize
        
    Returns:
        tuple: (normalized_s1, normalized_s2)
    """
    # Handle None cases gracefully
    if s1 is None:
        s1 = ""
    if s2 is None:
        s2 = ""
        
    # Convert both strings to lowercase and strip whitespace
    s1 = s1.lower().strip()
    s2 = s2.lower().strip()
    
    # Additional normalization:
    # Remove common punctuation that doesn't affect meaning
    for char in [',', '.', '-', '_', '(', ')', '/', '\\']:
        s1 = s1.replace(char, ' ')
        s2 = s2.replace(char, ' ')
    
    # Normalize multiple spaces to single space
    s1 = ' '.join(s1.split())
    s2 = ' '.join(s2.split())
    
    return s1, s2

def calculate_string_similarity(s1: str, s2: str) -> float:
    """
    Calculate a weighted similarity score between two strings.
    Uses configurable parameters from settings.
    
    Args:
        s1: First string
        s2: Second string
        
    Returns:
        float: Similarity score between 0.0 and 1.0
    """
    # Normalize inputs
    s1, s2 = get_normalized_strings(s1, s2)
    
    # Exact match is a perfect score
    if s1 == s2:
        return 1.0
        
    # Calculate Levenshtein ratio (0.0-1.0)
    ratio = levenshtein_ratio(s1, s2)
    
    # Apply substring boost if one is contained in the other
    if s1 in s2 or s2 in s1:
        ratio = min(ratio + settings.MATCH_EXACT_BONUS, 1.0)
    
    # Apply length difference penalty (normalized by max length)
    max_len = max(len(s1), len(s2))
    if max_len > 0:  # Avoid division by zero
        len_diff_penalty = abs(len(s1) - len(s2)) / max_len
        ratio = max(ratio - (len_diff_penalty * settings.MATCH_LENGTH_PENALTY), 0.0)
        
    return ratio

def fuzzy_best(name: str, catalog: dict[str, str]) -> tuple[str, float]:
    """
    Returns the most similar name and score (0-100) using Levenshtein distance with 
    length adjustment and substring bonuses. Score capped at 100. Exact match always wins.
    
    Args:
        name: The input string to match
        catalog: Dictionary of {product_name: product_id}
    
    Returns:
        tuple: (best_match, score)
    """
    # Clean the input
    name_l = name.lower().strip()
    
    # Fast path: check for exact matches first (case-insensitive)
    for prod in catalog.keys():
        prod_l = prod.lower().strip()
        if name_l == prod_l:
            return prod, 100.0
    
    # Regular path: calculate similarity scores for all candidates
    candidates = []
    for prod in catalog.keys():
        prod_l = prod.lower().strip()
        
        # Calculate similarity with enhanced algorithm
        similarity = calculate_string_similarity(name_l, prod_l)
        
        # Convert to percentage score
        score = similarity * 100
        
        # Ensure score stays within valid range
        score = max(min(score, 100), 0)
        
        # Store candidate with score and length difference for sorting
        candidates.append((prod, score, abs(len(name_l) - len(prod_l))))
    
    # Sort by: 1) highest score, 2) smallest length difference, 3) shorter name
    candidates.sort(key=lambda t: (t[1], -t[2], len(t[0])), reverse=True)
    
    # Return the best match and its score (empty catalog edge case handled)
    if not candidates:
        return "", 0.0
        
    best, score, _ = candidates[0]
    return best, score

def match_positions(positions: List[Dict], products: List[Dict], threshold: Optional[float] = None, return_suggestions: bool = False) -> List[Dict]:
    # Debug logging
    # debug_mode = True  # Отключено для production-логов
    if threshold is None:
        threshold = settings.MATCH_THRESHOLD
        
    # Normal operation for production code
    results = []
    used_ids = set()
    for pos in positions:
        # Support both dict and pydantic Position
        name = getattr(pos, "name", None)
        if name is None and isinstance(pos, dict):
            name = pos.get("name", "")
        qty = getattr(pos, "qty", None)
        if qty is None and isinstance(pos, dict):
            qty = pos.get("qty", "")
        unit = getattr(pos, "unit", None)
        if unit is None and isinstance(pos, dict):
            unit = pos.get("unit", "")
        best_match = None
        best_score = 0
        matched_product = None
        status = "unknown"
        fuzzy_scores = []
        for product in products:
            # Support both Product model and dict for backward compatibility
            if isinstance(product, dict):
                pid = product.get("id")
                if "alias" in product:
                    alias = product["alias"]
                    # Если alias пустой — не участвует ни в каком сопоставлении
                    if not alias or str(alias).strip() == "":
                        continue
                    compare_val = alias
                else:
                    compare_val = product.get("name", "")
                product_name = product.get("name", "")
            else:
                pid = getattr(product, "id", None)
                if hasattr(product, "alias"):
                    alias = getattr(product, "alias", None)
                    if not alias or str(alias).strip() == "":
                        continue
                    compare_val = alias
                else:
                    compare_val = getattr(product, "name", "")
                product_name = getattr(product, "name", "")
                
            if pid in used_ids:
                continue
                
            # Use enhanced similarity calculation with our helper function
            normalized_name = name.lower().strip()
            normalized_compare = compare_val.lower().strip()
            similarity = calculate_string_similarity(normalized_name, normalized_compare)
            score = similarity
            
            fuzzy_scores.append((score, product))
            if score > best_score:
                best_score = score
                best_match = product
        # Determine match status and canonical name
        canonical_name = name
        matched_product = None
        status = "unknown"
        
        if best_match is not None:
            # Get properties from best match
            if isinstance(best_match, dict):
                alias_val = best_match.get("alias", "")
                product_name = best_match.get("name", "")
            else:
                alias_val = getattr(best_match, "alias", "")
                product_name = getattr(best_match, "name", "")
                
            # Normalize all strings for comparison
            name_l = name.strip().lower()
            alias_l = alias_val.strip().lower() if alias_val else ""
            product_name_l = product_name.strip().lower() if product_name else ""
            
            # Get threshold value for similarity comparison
            threshold_value = settings.MATCH_THRESHOLD
            
            # Exact match first (case insensitive)
            if name_l and alias_l and name_l == alias_l:
                matched_product = best_match
                status = "ok"
                canonical_name = product_name  # Use product name as canonical name
            elif name_l and product_name_l and name_l == product_name_l:
                matched_product = best_match
                status = "ok"
                canonical_name = product_name
            # Use threshold-based matching when exact match fails
            elif best_score >= threshold_value * 100:
                matched_product = best_match
                status = "ok"  # Change this to match test expectations
                canonical_name = product_name  # Use product name for properly matched items
            else:
                matched_product = None
                status = "unknown"
                canonical_name = name
        # Все остальные случаи: matched_product=None, status='unknown', canonical_name=name
        # Post-check: unit_group
        if matched_product is not None:
            if isinstance(matched_product, dict):
                prod_unit_group = matched_product.get("unit_group")
            else:
                prod_unit_group = getattr(matched_product, "unit_group", None)
            pos_unit = unit
            # 1. Если unit==pcs и unit_group продукта kg/g → unit_mismatch
            if pos_unit == "pcs" and prod_unit_group in ("kg", "g"):
                status = "unit_mismatch"
            # 2. Если совпало только по имени, но unit_group разные → unit_mismatch
            elif prod_unit_group and pos_unit and prod_unit_group != pos_unit:
                # (unit_group и unit не совпадают)
                status = "unit_mismatch"
        logger.debug(f"Match: {name} → {getattr(matched_product, 'alias', None) if matched_product is not None and not isinstance(matched_product, dict) else (matched_product.get('alias') if matched_product else None)}; status={status}")
        # Корректно определяем result_id
        if matched_product is not None:
            if isinstance(matched_product, dict):
                result_id = matched_product.get("id")
            else:
                result_id = getattr(matched_product, "id", None)
        else:
            result_id = None
        result = {
            "name": canonical_name,
            "qty": qty,
            "unit": unit,
            "status": status,
            "product_id": result_id,
            "score": best_score if best_score else None,
        }
        if return_suggestions and status == "unknown":
            # Top-5 fuzzy suggestions for unknown
            fuzzy_scores.sort(reverse=True, key=lambda x: x[0])
            result["suggestions"] = [p for s, p in fuzzy_scores[:5] if s > settings.MATCH_MIN_SCORE]
        results.append(result)
    return results
