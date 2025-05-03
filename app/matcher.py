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

def fuzzy_best(name: str, catalog: dict[str, str]) -> tuple[str, float]:
    """Возвращает наиболее похожее имя и score (0-100) по Левенштейну с учетом длины и подстрок. Score capped at 100. Exact match always wins."""
    name_l = name.lower().strip()
    for prod in catalog.keys():
        prod_l = prod.lower().strip()
        if name_l == prod_l:
            return prod, 100.0
    candidates = []
    for prod in catalog.keys():
        prod_l = prod.lower().strip()
        score = levenshtein_ratio(name_l, prod_l) * 100
        if name_l in prod_l or prod_l in name_l:
            score = min(score + 5, 100)
        score -= abs(len(name_l) - len(prod_l))
        score = max(min(score, 100), 0)
        candidates.append((prod, score, abs(len(name_l) - len(prod_l))))
    candidates.sort(key=lambda t: (t[1], -t[2], len(t[0])), reverse=True)
    best, score, _ = candidates[0]
    return best, score

def match_positions(positions: List[Dict], products: List[Dict], threshold: Optional[float] = None, return_suggestions: bool = False) -> List[Dict]:
    # Debug logging
    # debug_mode = True  # Отключено для production-логов
    if threshold is None:
        threshold = settings.MATCH_THRESHOLD
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
            else:
                pid = getattr(product, "id", None)
                if hasattr(product, "alias"):
                    alias = getattr(product, "alias", None)
                    if not alias or str(alias).strip() == "":
                        continue
                    compare_val = alias
                else:
                    compare_val = getattr(product, "name", "")
            if pid in used_ids:
                continue
            score = levenshtein_ratio(name.lower().strip(), compare_val.lower().strip())
            fuzzy_scores.append((score, product))
            if score > best_score:
                best_score = score
                best_match = product
        # Строгое совпадение: статус 'ok' только если name_l == alias_l или name_l == product_name_l
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
            # Строгое сравнение только по нижнему регистру
            # Сравнение name_l с alias_l (оба в нижнем регистре)
            print(f"DEBUG: Comparing name_l='{name_l}' with alias_l='{alias_l}' (alias_val='{alias_val}')")
            if name_l and alias_l and name_l == alias_l:
                matched_product = best_match
                status = "ok"
                canonical_name = name  # canonical_name — исходный name позиции
            elif name_l and product_name_l and name_l == product_name_l:
                matched_product = best_match
                status = "ok"
                canonical_name = product_name
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
            result["suggestions"] = [p for s, p in fuzzy_scores[:5] if s > 0.5]
        results.append(result)
    return results
