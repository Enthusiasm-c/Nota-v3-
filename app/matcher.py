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


def match_positions(positions: List[Dict], products: List[Dict], threshold: Optional[float] = None) -> List[Dict]:
    if threshold is None:
        threshold = settings.MATCH_THRESHOLD
    results = []
    for pos in positions:
        name = pos.get("name", "")
        qty = pos.get("qty", "")
        unit = pos.get("unit", "")
        best_match = None
        best_score = 0
        matched_product = None
        status = "unknown"
        for product in products:
            alias = product.get("alias", "")
            if name.lower().strip() == alias.lower().strip():
                matched_product = product
                best_score = 1.0
                status = "ok"
                break
            score = levenshtein_ratio(name.lower().strip(), alias.lower().strip())
            if score > best_score:
                best_score = score
                best_match = product
        if status != "ok" and best_score >= threshold:
            matched_product = best_match
            status = "ok"
        elif status != "ok":
            status = "unknown"
        logger.debug(f"Match: {name} → {getattr(matched_product, 'alias', None)}; score={best_score:.2f}")
        results.append({
            "name": name,
            "qty": qty,
            "unit": unit,
            "status": status,
            "product_id": matched_product.get("id") if matched_product else None,
            "score": best_score if best_score else None
        })
    return results
