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

    # Проверка на совпадение отдельных слов
    words1 = s1.split()
    words2 = s2.split()
    
    # Если одинаковое количество слов, анализируем каждое слово
    if len(words1) == len(words2):
        word_matches = sum(1 for w1, w2 in zip(words1, words2) if w1 == w2)
        # Если большинство слов совпадают, но не все, увеличиваем вес для проверки
        if word_matches > 0 and word_matches == len(words1) - 1:
            # Находим несовпадающее слово и проверяем, не слишком ли оно похоже
            non_matching_idx = [i for i, (w1, w2) in enumerate(zip(words1, words2)) if w1 != w2][0]
            word1 = words1[non_matching_idx]
            word2 = words2[non_matching_idx]
            
            # Проверка по списку известных похожих слов
            for sim_pair in getattr(settings, 'SIMILAR_WORD_PAIRS', []):
                if (word1, word2) == sim_pair or (word2, word1) == sim_pair:
                    logger.warning(f"Обнаружена известная проблемная пара слов: '{word1}' и '{word2}' в '{s1}' и '{s2}'")
                    # Уменьшаем коэффициент сходства для известных проблемных пар
                    return 0.7  # Достаточно для "partial", но не для "ok"
            
            # Особая проверка для других похожих слов
            if levenshtein_ratio(word1, word2) > 0.7:
                logger.warning(f"Обнаружены похожие, но разные слова: '{word1}' и '{word2}' в '{s1}' и '{s2}'")
    
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


def match_supplier(supplier_name: str, suppliers: List[Dict], threshold: float = 0.9) -> Dict:
    """
    Match supplier name with supplier database using fuzzy matching.
    
    Args:
        supplier_name: Supplier name from the invoice
        suppliers: List of supplier dictionaries from the database
        threshold: Similarity threshold (default 0.9 = 90%)
        
    Returns:
        Dictionary with matched supplier data or original name if no match found
    """
    if not supplier_name or not suppliers:
        return {"name": supplier_name, "id": None, "status": "unknown"}
    
    normalized_name = supplier_name.lower().strip()
    best_match = None
    best_score = -1.0
    
    for supplier in suppliers:
        if isinstance(supplier, dict):
            name = supplier.get("name", "")
            supplier_id = supplier.get("id", "")
            code = supplier.get("code", "")
        else:
            name = getattr(supplier, "name", "")
            supplier_id = getattr(supplier, "id", "")
            code = getattr(supplier, "code", "")
            
        if not name:
            continue
            
        # Check for exact match first (case insensitive)
        if normalized_name == name.lower().strip():
            return {
                "name": name,  # Use the name from the database
                "id": supplier_id,
                "code": code,
                "status": "ok",
                "score": 1.0
            }
            
        # Calculate similarity for fuzzy matching
        similarity = calculate_string_similarity(normalized_name, name.lower().strip())
        if similarity > best_score:
            best_score = similarity
            best_match = supplier
    
    # Check if best match passes the threshold
    if best_match and best_score >= threshold:
        return {
            "name": best_match.get("name", best_match["name"] if isinstance(best_match, dict) else getattr(best_match, "name")),
            "id": best_match.get("id", best_match["id"] if isinstance(best_match, dict) else getattr(best_match, "id")),
            "code": best_match.get("code", best_match["code"] if isinstance(best_match, dict) else getattr(best_match, "code", "")),
            "status": "ok",
            "score": best_score
        }
    
    # No match found above threshold
    return {
        "name": supplier_name,  # Keep the original name
        "id": None,
        "status": "unknown",
        "score": best_score if best_score > -1 else None
    }


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
        has_similar_words = False  # Флаг для отметки похожих слов
        has_color_descriptor = False  # Флаг для цветовых модификаторов

        # Проверка на цветовые модификаторы (green, red, yellow, etc.)
        normalized_name = name.lower().strip()
        color_prefixes = ["green", "red", "yellow", "black", "white", "blue", "purple", "brown"]
        base_name = None
        
        # Проверяем, начинается ли название с цветового префикса
        for color in color_prefixes:
            if normalized_name.startswith(color + " "):
                base_name = normalized_name[len(color) + 1:]
                has_color_descriptor = True
                logger.info(f"Обнаружен цветовой дескриптор '{color}' в названии '{normalized_name}', базовое название: '{base_name}'")
                break

        for product in products:
            if isinstance(product, dict):
                compare_val = product.get("name", "")
            else:
                compare_val = getattr(product, "name", "")

            normalized_compare = compare_val.lower().strip()
            
            # Проверка для базового названия (без цвета) если применимо
            base_similarity = 0.0
            if has_color_descriptor and base_name:
                base_similarity = calculate_string_similarity(base_name, normalized_compare)
                if base_similarity > 0.9:  # Высокий порог для базового имени
                    logger.info(f"Базовое название '{base_name}' очень похоже на '{normalized_compare}' (score: {base_similarity})")
            
            # Проверка на похожие слова
            words1 = normalized_name.split()
            words2 = normalized_compare.split()
            
            # Если одинаковая структура, но возможно есть похожие слова
            if len(words1) == len(words2) and len(words1) > 1:
                word_matches = sum(1 for w1, w2 in zip(words1, words2) if w1 == w2)
                # Если большинство слов совпадают, но не все, проверяем похожие слова
                if word_matches > 0 and word_matches == len(words1) - 1:
                    # Находим несовпадающие слова
                    non_matching = [(i, w1, w2) for i, (w1, w2) in enumerate(zip(words1, words2)) if w1 != w2]
                    for idx, word1, word2 in non_matching:
                        # Специальная проверка для часто путаемых слов
                        if (word1 in ['rice', 'milk'] and word2 in ['rice', 'milk']) or \
                           (len(word1) > 2 and len(word2) > 2 and levenshtein_ratio(word1, word2) > 0.7):
                            logger.warning(f"Похожие слова в '{normalized_name}' и '{normalized_compare}': '{word1}' и '{word2}'")
                            has_similar_words = True
            
            similarity = calculate_string_similarity(
                normalized_name, normalized_compare
            )
            
            # Если есть цветовой дескриптор и нашлось высокое совпадение с базовым именем,
            # используем его как запасной вариант
            score = similarity
            if has_color_descriptor and base_similarity > 0.9 and base_similarity > similarity:
                logger.info(f"Использую базовое сравнение для '{normalized_name}': {base_similarity}")
                score = base_similarity * 0.95  # Чуть ниже порога для обозначения как partial
                has_similar_words = True
                
            fuzzy_scores.append((score, product))

            if score > best_score:
                best_score = score
                best_match = product

        # Определяем статус с учетом похожих слов и цветовых дескрипторов
        if best_score >= threshold:
            if has_similar_words or has_color_descriptor:
                status = "partial"  # Если похожие слова или цвета, то частичное совпадение
            else:
                status = "ok"       # Иначе полное совпадение
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
