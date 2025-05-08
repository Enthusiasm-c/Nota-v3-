import logging
from typing import (
    List, Dict, Optional, Tuple, Sequence, Hashable, Callable, Any, Union
)
from app.config import settings

try:
    from Levenshtein import ratio as _levenshtein_ratio
    from Levenshtein import distance as _levenshtein_distance

    def levenshtein_ratio(
        s1: Sequence[Hashable],
        s2: Sequence[Hashable],
        *,
        processor: Union[Callable[..., Sequence[Hashable]], None] = None,
        score_cutoff: Union[float, None] = None,
    ) -> float:
        return _levenshtein_ratio(s1, s2)

    def levenshtein_distance(
        s1: Sequence[Hashable],
        s2: Sequence[Hashable],
        *,
        weights: Union[tuple[int, int, int], None] = None,
        processor: Union[Callable[..., Sequence[Hashable]], None] = None,
        score_cutoff: Union[float, None] = None,
        score_hint: Union[float, None] = None,
    ) -> int:
        return _levenshtein_distance(s1, s2)

    USE_LEVENSHTEIN = True
except ImportError:
    from difflib import SequenceMatcher

    def levenshtein_ratio(
        s1: Sequence[Hashable],
        s2: Sequence[Hashable],
        *,
        processor: Union[Callable[..., Sequence[Hashable]], None] = None,
        score_cutoff: Union[float, None] = None,
    ) -> float:
        a = "".join(map(str, s1))
        b = "".join(map(str, s2))
        return SequenceMatcher(None, a, b).ratio()

    def levenshtein_distance(
        s1: Sequence[Hashable],
        s2: Sequence[Hashable],
        *,
        weights: Union[tuple[int, int, int], None] = None,
        processor: Union[Callable[..., Sequence[Hashable]], None] = None,
        score_cutoff: Union[float, None] = None,
        score_hint: Union[float, None] = None,
    ) -> int:
        a = "".join(map(str, s1))
        b = "".join(map(str, s2))
        if a == b:
            return 0
        if len(a) > 20:
            a = a[:17] + "..."
        if len(b) > 20:
            b = b[:17] + "..."
        if len(b) == 0:
            return len(a)
        if len(a) == 0:
            return len(b)
        matrix = [[0 for _ in range(len(b) + 1)] for _ in range(len(a) + 1)]
        for i in range(len(a) + 1):
            matrix[i][0] = i
        for j in range(len(b) + 1):
            matrix[0][j] = j
        for i in range(1, len(a) + 1):
            for j in range(1, len(b) + 1):
                cost = 0 if a[i - 1] == b[j - 1] else 1
                matrix[i][j] = min(
                    matrix[i - 1][j] + 1,
                    matrix[i][j - 1] + 1,
                    matrix[i - 1][j - 1] + cost,
                )
        return matrix[len(a)][len(b)]
    USE_LEVENSHTEIN = False

logger = logging.getLogger(__name__)


def get_normalized_strings(s1: str, s2: str) -> Tuple[str, str]:
    if s1 is None:
        s1 = ""
    if s2 is None:
        s2 = ""

    s1 = s1.lower().strip()
    s2 = s2.lower().strip()

    for char in [",", ".", "-", "_", "(", ")", "/", "\\"]:
        s1 = s1.replace(char, " ")
        s2 = s2.replace(char, " ")

    s1 = " ".join(s1.split())
    s2 = " ".join(s2.split())

    return s1, s2


def calculate_string_similarity(s1: str, s2: str) -> float:
    s1, s2 = get_normalized_strings(s1, s2)
    if s1 == s2:
        return 1.0

    ratio = levenshtein_ratio(s1, s2)
    if s1 in s2 or s2 in s1:
        ratio = min(ratio + settings.MATCH_EXACT_BONUS, 1.0)

    max_len = max(len(s1), len(s2))
    if max_len > 0:
        len_diff_penalty = abs(len(s1) - len(s2)) / max_len
        ratio = max(ratio - (len_diff_penalty * settings.MATCH_LENGTH_PENALTY), 0.0)

    return ratio


def fuzzy_best(name: str, catalog: dict[str, str]) -> tuple[str, float]:
    name_l = name.lower().strip()

    for prod in catalog.keys():
        prod_l = prod.lower().strip()
        if name_l == prod_l:
            return prod, 100.0

    candidates = []
    for prod in catalog.keys():
        prod_l = prod.lower().strip()
        similarity = calculate_string_similarity(name_l, prod_l)
        score = similarity * 100
        score = max(min(score, 100), 0)
        candidates.append((prod, score, abs(len(name_l) - len(prod_l))))

    candidates.sort(key=lambda t: (t[1], -t[2], len(t[0])), reverse=True)

    if not candidates:
        return "", 0.0

    best, score, _ = candidates[0]
    return best, score


def fuzzy_find(query: str, products: List[Dict], thresh: float = 0.75) -> List[Dict]:
    """
    Find products with similar names using fuzzy matching.
    
    Args:
        query: The search query (product name)
        products: List of product dictionaries
        thresh: Similarity threshold (0.0-1.0)
        
    Returns:
        List of matching products with similarity >= threshold
    """
    if not query or not products:
        return []
    
    query = query.lower().strip()
    matches = []
    
    for product in products:
        if isinstance(product, dict):
            name = product.get("name", "")
            product_id = product.get("id", "")
        else:
            name = getattr(product, "name", "")
            product_id = getattr(product, "id", "")
            
        if not name:
            continue
            
        similarity = calculate_string_similarity(query, name)
        if similarity >= thresh:
            matches.append({
                "name": name,
                "id": product_id,
                "score": similarity
            })
    
    # Sort by similarity score (highest first)
    matches.sort(key=lambda x: x["score"], reverse=True)
    
    return matches


def match_positions(
    positions: List[Dict],
    products: List[Dict],
    threshold: Optional[float] = None,
    return_suggestions: bool = False,
) -> List[Dict]:
    if threshold is None:
        threshold = settings.MATCH_THRESHOLD

    results = []

    for pos in positions:
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
        best_score: float = -1.0
        status = "unknown"
        fuzzy_scores = []

        for product in products:
            if isinstance(product, dict):
                compare_val = product.get("name", "")
            else:
                compare_val = getattr(product, "name", "")

            normalized_name = name.lower().strip()
            normalized_compare = compare_val.lower().strip()
            similarity = calculate_string_similarity(
                normalized_name, normalized_compare
            )
            score = similarity
            fuzzy_scores.append((score, product))

            if score > best_score:
                best_score = score
                best_match = product

        if best_score >= threshold:
            status = "ok"
        else:
            status = "unknown"

        total = None
        price = None
        if isinstance(pos, dict):
            total = pos.get("total")
            price = pos.get("price")
        else:
            total = getattr(pos, "total", None)
            price = getattr(pos, "price", None)

        # Привести qty, total, price к float если возможно
        try:
            qty_f = float(qty)
        except Exception:
            qty_f = None
        try:
            total_f = float(total)
        except Exception:
            total_f = None
        try:
            price_f = float(price)
        except Exception:
            price_f = None

        # price = total/qty если price нет, но есть total и qty
        if price_f is None and total_f is not None and qty_f not in (None, 0):
            price_f = total_f / qty_f
        # line_total = price*qty если line_total нет, но есть price и qty
        line_total_f = None
        if price_f is not None and qty_f not in (None, 0):
            line_total_f = price_f * qty_f
        elif total_f is not None:
            line_total_f = total_f

        result = {
            "name": name,
            "qty": qty,
            "unit": unit,
            "status": status,
            "score": best_score if best_score else None,
            "price": price_f,
            "line_total": line_total_f,
        }

        if (
            return_suggestions
            and status == "unknown"
        ):
            fuzzy_scores.sort(
                reverse=True, key=lambda x: x[0]
            )
            result["suggestions"] = [
                p
                for s, p in fuzzy_scores[:5]
                if s > settings.MATCH_MIN_SCORE
            ]

        results.append(result)

    return results
