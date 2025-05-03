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
    debug_mode = True  # Включаем режим отладки
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
            if name.lower().strip() == compare_val.lower().strip():
                matched_product = product
                best_score = 1.0
                status = "ok"
                break
            score = levenshtein_ratio(name.lower().strip(), compare_val.lower().strip())
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
            if isinstance(best_match, dict):
                canonical_name = best_match.get("alias", best_match.get("name", name))
                if matched_product and matched_product.get("id"):
                    used_ids.add(matched_product.get("id"))
            else:
                canonical_name = getattr(best_match, "alias", getattr(best_match, "name", name))
                if matched_product and getattr(matched_product, "id", None):
                    used_ids.add(getattr(matched_product, "id", None))
        # If not matched by 0.98 rule, but still above threshold, use regular logic
        elif best_match is not None and best_score >= threshold:
            matched_product = best_match
            status = "ok"
            if isinstance(best_match, dict):
                canonical_name = best_match.get("alias", best_match.get("name", name))
                if matched_product and matched_product.get("id"):
                    used_ids.add(matched_product.get("id"))
            else:
                canonical_name = getattr(best_match, "alias", getattr(best_match, "name", name))
                if matched_product and getattr(matched_product, "id", None):
                    used_ids.add(getattr(matched_product, "id", None))
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
        # NEW: fuzzy rescue
        if status == "unknown":
            # Гибрид: если хотя бы у одного продукта есть alias — fuzzy rescue только по alias, иначе по name
            # Проверяем, есть ли хотя бы один НЕПУСТОЙ alias (не None и не пустая строка)
            def is_nonempty_alias(val):
                return val is not None and str(val).strip() != ""
            has_any_nonempty_alias = any(
                is_nonempty_alias(p.get("alias") if isinstance(p, dict) else getattr(p, "alias", None))
                for p in products
            )
            def get_catalog_entry(p):
                if isinstance(p, dict):
                    if "alias" in p:
                        alias = p["alias"]
                        # Если alias не пустой — добавить по alias
                        if has_any_nonempty_alias:
                            if alias and str(alias).strip() != "":
                                return alias, p.get("id")
                        # alias пустой — не добавлять никуда
                        return None, None
                    else:
                        # Нет поля alias — разрешить fuzzy rescue по name, если нет ни одного с непустым alias
                        name = p.get("name")
                        if not has_any_nonempty_alias and name:
                            return name, p.get("id")
                else:
                    if hasattr(p, "alias"):
                        alias = getattr(p, "alias", None)
                        # Если alias не пустой — добавить по alias
                        if has_any_nonempty_alias:
                            if alias and str(alias).strip() != "":
                                return alias, getattr(p, "id", None)
                        # alias пустой — не добавлять никуда
                        return None, None
                    else:
                        # Нет атрибута alias — разрешить fuzzy rescue по name, если нет ни одного с непустым alias
                        name = getattr(p, "name", None)
                        if not has_any_nonempty_alias and name:
                            return name, getattr(p, "id", None)
                return None, None
            # Каталог: либо только alias (если есть хотя бы один НЕПУСТОЙ), либо только name (если все alias пустые)
            catalog = {key: pid for key, pid in (get_catalog_entry(p) for p in products) if key}
            if not catalog:
                # Каталог пуст — rescue невозможен
                status = "unknown"
                result_id = None
                canonical_name = name
                best_score = 0
                result = {
                    "name": canonical_name,
                    "qty": qty,
                    "unit": unit,
                    "status": status,
                    "product_id": result_id,
                    "score": best_score if best_score else None,
                }
                results.append(result)
                continue
            # Track already used product ids
            used_ids = set(r.get("product_id") for r in results if r.get("status") == "ok")
            # Get all candidates sorted by fuzzy_best logic
            candidates = []
            name_l = name.lower().strip()
            for prod, pid in catalog.items():
                prod_l = prod.lower().strip()
                if name_l == prod_l:
                    score = 100.0
                else:
                    score = levenshtein_ratio(name_l, prod_l) * 100
                    if name_l in prod_l or prod_l in name_l:
                        score = min(score + 5, 100)
                    score -= abs(len(name_l) - len(prod_l))
                    score = max(min(score, 100), 0)
                candidates.append((prod, pid, score, abs(len(name_l) - len(prod_l)), len(prod)))
            candidates.sort(key=lambda t: (t[2], -t[3], t[4]), reverse=True)
            best = None
            sc = 0
            for prod, pid, score, _, _ in candidates:
                if pid not in used_ids:
                    best = prod
                    sc = score
                    break
            if best is not None and sc >= getattr(settings, "FUZZY_PROMPT_THRESHOLD", 90):
                canonical_name = best
                # Only consider products with a non-empty alias for fuzzy rescue
                def alias_of(p):
                    return getattr(p, "alias", None) if not isinstance(p, dict) else p.get("alias")
                matched_product = next((p for p in products if alias_of(p) and str(alias_of(p)).strip() != "" and alias_of(p) == best), None)
                if matched_product:
                    status = "ok"
                    result_id = getattr(matched_product, "id", None) if not isinstance(matched_product, dict) else matched_product.get("id")
                    if result_id:
                        used_ids.add(result_id)
                else:
                    # If not a real alias, do not rescue
                    result_id = None
                    status = "unknown"
                best_score = sc / 100.0
            else:
                if matched_product is not None:
                    if isinstance(matched_product, dict):
                        result_id = matched_product.get("id")
                    else:
                        result_id = getattr(matched_product, "id", None)
                else:
                    result_id = None
        else:
            if matched_product is not None:
                if isinstance(matched_product, dict):
                    result_id = matched_product.get("id")
                else:
                    result_id = getattr(matched_product, "id", None)
            else:
                result_id = None
        logger.debug(f"Match: {name} → {getattr(matched_product, 'alias', None) if matched_product is not None and not isinstance(matched_product, dict) else (matched_product.get('alias') if matched_product else None)}; score={best_score:.2f}; status={status}")
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
    # Fallback: жадное назначение для оставшихся позиций
    # Fallback: greedy assignment for remaining positions, support Product model
    def get_id(p):
        return p.get("id") if isinstance(p, dict) else getattr(p, "id", None)
    def get_alias_name(p):
        return p.get("alias", p.get("name", "")) if isinstance(p, dict) else getattr(p, "alias", getattr(p, "name", ""))
    unused_products = [p for p in products if get_id(p) not in used_ids]
    unknown_indices = [i for i, r in enumerate(results) if r["status"] == "unknown"]
    for idx, product in zip(unknown_indices, unused_products):
        name = results[idx]["name"]
        prod_name = get_alias_name(product)
        score = levenshtein_ratio(name.lower().strip(), prod_name.lower().strip())
        if score >= 0.5:
            results[idx]["name"] = prod_name
            results[idx]["status"] = "ok"
            results[idx]["product_id"] = get_id(product)
            results[idx]["score"] = score
            used_ids.add(get_id(product))
        # иначе статус и поля остаются прежними (unknown)
    return results
