import logging
from typing import Any, Dict, List, Optional, Union

from app.models import Position, Product

logger = logging.getLogger(__name__)


def calculate_string_similarity(s1: Optional[str], s2: Optional[str], **kwargs) -> float:
    """Вычисляет схожесть строк."""
    if s1 is None or s2 is None:
        return 0.0
    if s1 == s2:
        return 1.0
    from rapidfuzz import fuzz

    return fuzz.ratio(s1, s2) / 100


async def async_match_positions(
    items: List[Union[Dict[str, Any], Position]],
    reference_items: List[Union[Dict[str, Any], Product]],
    threshold: float = 0.8,
    key: str = "name",
) -> List[Dict[str, Any]]:
    """ИСПРАВЛЕННАЯ функция async_match_positions - правильно добавляет поле id."""
    results = []
    reference_dict = {}
    reference_names = []

    for ref_item in reference_items:
        if isinstance(ref_item, dict):
            ref_name = ref_item.get(key, "").lower().strip()
            reference_dict[ref_name] = ref_item
        else:
            ref_name = getattr(ref_item, key, "").lower().strip()
            reference_dict[ref_name] = {
                "id": getattr(ref_item, "id", ""),
                "name": getattr(ref_item, "name", ""),
            }
        if ref_name:
            reference_names.append(ref_name)

    for item in items:
        if isinstance(item, dict):
            item_name = item.get(key, "").lower().strip()
            item_data = item.copy()
        else:
            item_name = getattr(item, key, "").lower().strip()
            item_data = {"name": getattr(item, "name", "")}

        if not item_name:
            results.append({"status": "unknown", "score": 0.0, "id": ""})
            continue

        best_score = 0.0
        best_match_name = None
        for ref_name in reference_names:
            score = calculate_string_similarity(item_name, ref_name)
            if score > best_score:
                best_score = score
                best_match_name = ref_name

        if best_match_name and best_score >= threshold:
            ref_data = reference_dict[best_match_name]
            result = item_data.copy()
            result.update(ref_data)
            result["status"] = "ok"
            result["score"] = best_score
            result["matched_name"] = best_match_name
            result["id"] = ref_data.get("id", "")  # ДОБАВЛЯЕМ ID!
            results.append(result)
        else:
            result = item_data.copy()
            result["status"] = "unknown"
            result["score"] = best_score
            result["id"] = ""
            results.append(result)

    return results


def match_positions(
    positions: List[Dict[str, Any]],
    products: List[Union[Product, Dict[str, Any]]],
    threshold: float = 0.7,
) -> List[Dict[str, Any]]:
    """ИСПРАВЛЕННАЯ функция match_positions - добавляет поле id."""
    results = []

    for position in positions:
        position_name = position.get("name", "")

        if not position_name:
            result = position.copy()
            result["status"] = "unknown"
            result["score"] = 0.0
            result["id"] = ""
            results.append(result)
            continue

        best_match = None
        best_score = 0.0

        for product in products:
            if isinstance(product, dict):
                product_name = product.get("name", "")
            else:
                product_name = getattr(product, "name", "")

            if not product_name:
                continue

            score = calculate_string_similarity(position_name, product_name)

            if score > best_score:
                best_score = score
                best_match = product

        result = position.copy()
        result["score"] = best_score

        if best_match and best_score >= threshold:
            result["status"] = "ok"

            if isinstance(best_match, dict):
                matched_name = best_match.get("name", "")
                matched_id = best_match.get("id", "")
            else:
                matched_name = getattr(best_match, "name", "")
                matched_id = getattr(best_match, "id", "")

            result["matched_name"] = matched_name
            result["matched_product"] = best_match
            result["id"] = matched_id  # ДОБАВЛЯЕМ ID!
        else:
            result["status"] = "unknown"
            result["matched_name"] = None
            result["matched_product"] = None
            result["id"] = ""

        results.append(result)

    return results
