import logging
from typing import List, Dict, Optional
try:
    from Levenshtein import ratio as levenshtein_ratio
except ImportError:
    from difflib import SequenceMatcher
    def levenshtein_ratio(a, b):
        return SequenceMatcher(None, a, b).ratio()

from app.config import settings

logger = logging.getLogger(__name__)


def match_positions(positions: List[Dict], products: List[Dict], threshold: Optional[float] = None, return_suggestions: bool = False) -> List[Dict]:
    if threshold is None:
        threshold = settings.MATCH_THRESHOLD
    results = []
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
            alias = product.get("alias", product.get("name", ""))
            if name.lower().strip() == alias.lower().strip():
                matched_product = product
                best_score = 1.0
                status = "ok"
                break
            score = levenshtein_ratio(name.lower().strip(), alias.lower().strip())
            fuzzy_scores.append((score, product))
            if score > best_score:
                best_score = score
                best_match = product
        # Fuzzy-rename rule: if Levenshtein score >= 0.98, set parsed.name = product.alias and status = 'ok'
        # This rule is strict and does not allow near-duplicates
        canonical_name = name
        if best_match is not None and best_score >= 0.98:
            matched_product = best_match
            status = "ok"
            canonical_name = best_match.get("alias", best_match.get("name", name))
        # If not matched by 0.98 rule, but still above threshold, use regular logic
        elif best_match is not None and best_score >= threshold:
            matched_product = best_match
            status = "ok"
            canonical_name = best_match.get("alias", best_match.get("name", name))
        logger.debug(f"Match: {name} → {getattr(matched_product, 'alias', None)}; score={best_score:.2f}")
        result = {
            "name": canonical_name,
            "qty": qty,
            "unit": unit,
            "status": status,
            "product_id": matched_product.get("id") if matched_product else None,
            "score": best_score if best_score else None,
            "canonical_name": canonical_name
        }
        if return_suggestions and status == "unknown":

            # Top-5 fuzzy suggestions for unknown
            fuzzy_scores.sort(reverse=True, key=lambda x: x[0])
            result["suggestions"] = [p for s, p in fuzzy_scores[:5] if s > 0.5]
        results.append(result)
    return results
