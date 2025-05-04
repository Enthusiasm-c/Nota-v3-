import logging
from typing import List, Dict, Optional, Tuple

try:
    from Levenshtein import ratio as levenshtein_ratio, \
    distance as levenshtein_distance
    USE_LEVENSHTEIN = True
except ImportError:
    from difflib import SequenceMatcher

    def levenshtein_ratio(a: str, b: str) -> float:
        return SequenceMatcher(None, a, b).ratio()

    def levenshtein_distance(a: str, b: str) -> int:
        if a == b:
            return 0
        if len(a) == 0:
            return len(b)
        if len(b) == 0:
            return len(a)

        matrix = [[0 for _ in range(len(b) + 1)] for _ in range(len(a) + 1)]

        for i in range(len(a) + 1):
            matrix[i][0] = i
        for j in range(len(b) + 1):
            matrix[0][j] = j

        for i in range(1, len(a) + 1):
            for j in range(1, len(b) + 1):
                cost = 0 if a[i - 1] == b[j - 1] else 1
                matrix[i][j] = min(
                    matrix[i - 1][j] + 1,  # deletion
                    matrix[i][j - 1] + 1,  # insertion
                    matrix[i - 1][j - 1] + cost  # substitution
                )

        return matrix[len(a)][len(b)]

    USE_LEVENSHTEIN = False

from app.config import settings

logger = logging.getLogger(__name__)



def get_normalized_strings(s1: str, s2: str) -> Tuple[str, str]:
    if s1 is None:
        s1 = ""
    if s2 is None:
        s2 = ""

    s1 = s1.lower().strip()
    s2 = s2.lower().strip()

    for char in [',', '.', '-', '_', '(', ')', '/', '\\']:
        s1 = s1.replace(char, ' ')
        s2 = s2.replace(char, ' ')

    s1 = ' '.join(s1.split())
    s2 = ' '.join(s2.split())

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

    candidates.sort(
        key=lambda t: (t[1], -t[2], len(t[0])), reverse=True
    )

    if not candidates:
        return "", 0.0

    best, score, _ = candidates[0]
    return best, score



def match_positions(
    positions: List[Dict],
    products: List[Dict],
    threshold: Optional[float] = None,
    return_suggestions: bool = False
) -> List[Dict]:
    if threshold is None:
        threshold = settings.MATCH_THRESHOLD

    results = []
    used_ids = set()

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
        best_score = 0
        matched_product = None
        status = "unknown"
        fuzzy_scores = []

        for product in products:
            if isinstance(product, dict):
                pid = product.get("id")
                if "alias" in product:
                    alias = product["alias"]
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

        canonical_name = name
        matched_product = None
        status = "unknown"

        if best_match is not None:
            if isinstance(best_match, dict):
                alias_val = best_match.get("alias", "")
                product_name = best_match.get("name", "")
            else:
                alias_val = getattr(best_match, "alias", "")
                product_name = getattr(best_match, "name", "")

            name_l = name.strip().lower()
            alias_l = alias_val.strip().lower() if alias_val else ""
            product_name_l = product_name.strip().lower() if product_name else ""

            threshold_value = settings.MATCH_THRESHOLD

            if (
                name_l and alias_l and name_l == alias_l
            ):
                matched_product = best_match
                status = "ok"
                canonical_name = product_name
            elif (
                name_l and product_name_l and name_l == product_name_l
            ):
                matched_product = best_match
                status = "ok"
                canonical_name = product_name
            elif best_score >= threshold_value * 100:
                matched_product = best_match
                status = "ok"
                canonical_name = product_name
            else:
                matched_product = None
                status = "unknown"
                canonical_name = name

        if matched_product is not None:
            if isinstance(matched_product, dict):
                prod_unit_group = matched_product.get("unit_group")
            else:
                prod_unit_group = getattr(matched_product, "unit_group", None)

            pos_unit = unit

            if pos_unit == "pcs" and prod_unit_group in ("kg", "g"):
                status = "unit_mismatch"
            elif prod_unit_group and pos_unit and prod_unit_group != pos_unit:
                status = "unit_mismatch"

        logger.debug(
            f"Match: {name}  {getattr(matched_product, 'alias', None) if matched_product is not None and not isinstance(matched_product, dict) else (matched_product.get('alias') if matched_product else None)}; "
            f"status={status}"
        )

        if matched_product is not None:
            if isinstance(matched_product, dict):
                result_id = matched_product.get("id")
            else:
                result_id = getattr(matched_product, "id", None)
        else:
            result_id = None

        total = None
        price = None
        if isinstance(pos, dict):
            total = pos.get("total")
            price = pos.get("price")
        else:
            total = getattr(pos, "total", None)
            price = getattr(pos, "price", None)

        computed_price = None
        computed_line_total = None
        try:
            if qty is not None and total is not None:
                q = float(qty)
                t = float(total)
                if q != 0:
                    computed_price = t / q
                    computed_line_total = t
                else:
                    computed_price = None
                    computed_line_total = None
            elif price is not None and qty is not None:
                q = float(qty)
                p = float(price)
                computed_price = p
                computed_line_total = p * q
            else:
                computed_price = None
                computed_line_total = None
        except Exception:
            computed_price = None
            computed_line_total = None

        result = {
            "name": canonical_name,
            "qty": qty,
            "unit": unit,
            "status": status,
            "product_id": result_id,
            "score": best_score if best_score else None,
            "price": computed_price,
            "line_total": computed_line_total,
        }

        if return_suggestions and status == "unknown":
            fuzzy_scores.sort(reverse=True, key=lambda x: x[0])
            result["suggestions"] = [p for s, p in fuzzy_scores[:5] if s > settings.MATCH_MIN_SCORE]

        results.append(result)

    return results
