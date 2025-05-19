import logging
from typing import (
    List, Dict, Optional, Tuple, Sequence, Hashable, Callable, Union, Any
)
from app.config import settings
from rapidfuzz import fuzz, process
from functools import lru_cache
from app.utils.string_cache import get_string_similarity_cached, set_string_similarity_cached
from rapidfuzz.distance import Levenshtein

# Инициализация логгера
logger = logging.getLogger(__name__)

# Словарь синонимов и вариантов написания
PRODUCT_VARIANTS = {
    "romaine": ["romana", "romaine lettuce"],
    "chickpeas": ["chick peas", "chickpea", "chick pea"],
    "green bean": ["green beans"],
    "english spinach": ["english spinach"],
    "tomato": ["tomatoes"],
    "eggplant": ["aubergine"],
    "watermelon": ["water melon"],
    "chili": ["chilli"],
    "mango": ["mangoes"]
}

# Словарь для приведения форм единственного/множественного числа
SINGULAR_PLURAL_FORMS = [
    ("beans", "bean"),
    ("peas", "pea"),
    ("tomatoes", "tomato"),
    ("potatoes", "potato"),
    ("carrots", "carrot"),
    ("apples", "apple"),
    ("oranges", "orange"),
    ("mangoes", "mango"),
    ("lemons", "lemon"),
    ("limes", "lime")
]

def normalize_product_name(name):
    """
    Нормализует название продукта, приводя множественные формы к единственным
    и обрабатывая известные варианты написания.
    """
    if not name:
        return ""
    
    name = name.lower().strip()
    
    # Проверяем в словаре синонимов
    for base_name, variants in PRODUCT_VARIANTS.items():
        if name in variants or name == base_name:
            return base_name
    
    # Обрабатываем множественные/единственные формы
    for plural, singular in SINGULAR_PLURAL_FORMS:
        if name.endswith(plural):
            return name[:-len(plural)] + singular
        
    return name

def get_normalized_strings(s1: str, s2: str) -> Tuple[str, str]:
    """
    Нормализует две строки для сравнения.
    """
    if not s1 or not s2:
        return "", ""

    s1 = s1.lower().strip()
    s2 = s2.lower().strip()

    return s1, s2

def levenshtein_ratio(s1: str, s2: str) -> float:
    """
    Вычисляет нормализованное расстояние Левенштейна между строками.
    
    Args:
        s1: Первая строка
        s2: Вторая строка
        
    Returns:
        Значение сходства от 0 до 1
    """
    return fuzz.ratio(s1, s2) / 100.0

def levenshtein_distance(s1: str, s2: str) -> int:
    """
    Вычисляет расстояние Левенштейна между строками.
    
    Args:
        s1: Первая строка
        s2: Вторая строка
        
    Returns:
        Расстояние Левенштейна (количество операций редактирования)
    """
    return Levenshtein.distance(s1, s2)

def calculate_string_similarity(s1: str, s2: str) -> float:
    """
    Вычисляет сходство между строками с использованием кеша.
    
    Args:
        s1: Первая строка
        s2: Вторая строка
        
    Returns:
        Значение сходства от 0 до 1
    """
    # Проверяем кеш
    cached = get_string_similarity_cached(s1, s2)
    if cached is not None:
        return cached
        
    # Вычисляем сходство
    similarity = fuzz.ratio(s1, s2) / 100.0
    
    # Сохраняем в кеш
    set_string_similarity_cached(s1, s2, similarity)
    
    return similarity

def fuzzy_find(query: str, products: List[Dict], thresh: float = 0.75) -> List[Dict]:
    """
    Оптимизированный поиск продуктов с использованием rapidfuzz.
    
    Args:
        query: Поисковый запрос
        products: Список продуктов
        thresh: Порог сходства
        
    Returns:
        Список совпадающих продуктов
    """
    if not query or not products:
        return []
    
    query = query.lower().strip()
    
    # Создаем список названий для быстрого поиска
    names = []
    name_to_product = {}
    
    for product in products:
        if isinstance(product, dict):
            name = product.get("name", "")
            product_id = product.get("id", "")
        else:
            name = getattr(product, "name", "")
            product_id = getattr(product, "id", "")
            
        if name:
            normalized = normalize_product_name(name.lower().strip())
            names.append(normalized)
            name_to_product[normalized] = {"name": name, "id": product_id}
    
    # Используем process.extract для эффективного поиска
    matches = process.extract(
        normalize_product_name(query),
        names,
        scorer=fuzz.ratio,
        score_cutoff=int(thresh * 100)
    )
    
    results = []
    for name, score, _ in matches:
        product_data = name_to_product[name]
        results.append({
            "name": product_data["name"],
            "id": product_data["id"],
            "score": score / 100.0
        })

    return results

def fuzzy_best(name: str, catalog: dict[str, str]) -> tuple[str, float]:
    """
    Находит наилучшее совпадение в каталоге.
    
    Args:
        name: Название для поиска
        catalog: Словарь названий продуктов
        
    Returns:
        Кортеж (название продукта, оценка сходства)
    """
    name_l = name.lower().strip()

    # Проверяем точное совпадение
    for prod in catalog.keys():
        prod_l = prod.lower().strip()
        if name_l == prod_l:
            return prod, 100.0

    # Ищем наилучшее совпадение
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
    positions: List[Dict[str, Any]],
    products: List[Dict[str, Any]],
    threshold: Optional[float] = None,
    return_suggestions: bool = False,
) -> List[Dict[str, Any]]:
    """
    Сопоставляет позиции с продуктами из базы данных.
    
    Args:
        positions: Список позиций для сопоставления
        products: Список продуктов из базы данных
        threshold: Порог схожести для сопоставления
        return_suggestions: Возвращать ли предложения при отсутствии точного совпадения
        
    Returns:
        Список сопоставленных позиций с дополнительной информацией
    """
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
        has_similar_words = False
        has_color_descriptor = False

        normalized_name = name.lower().strip() if name else ""
        color_prefixes = ["green", "red", "yellow", "black", "white", "blue", "purple", "brown"]
        base_name = None
        
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
            
            base_similarity = 0.0
            if has_color_descriptor and base_name:
                base_similarity = calculate_string_similarity(base_name, normalized_compare)
                if base_similarity > 0.9:
                    logger.info(f"Базовое название '{base_name}' очень похоже на '{normalized_compare}' (score: {base_similarity})")
            
            words1 = normalized_name.split()
            words2 = normalized_compare.split()
            
            if len(words1) == len(words2) and len(words1) > 1:
                word_matches = sum(1 for w1, w2 in zip(words1, words2) if w1 == w2)
                if word_matches > 0 and word_matches == len(words1) - 1:
                    non_matching = [(i, w1, w2) for i, (w1, w2) in enumerate(zip(words1, words2)) if w1 != w2]
                    for idx, word1, word2 in non_matching:
                        if (word1 in ['rice', 'milk'] and word2 in ['rice', 'milk']) or \
                           (len(word1) > 2 and len(word2) > 2 and levenshtein_ratio(word1, word2) > 0.7):
                            logger.warning(f"Похожие слова в '{normalized_name}' и '{normalized_compare}': '{word1}' и '{word2}'")
                            has_similar_words = True
            
            similarity = calculate_string_similarity(
                normalized_name, normalized_compare
            )
            
            score = similarity
            if has_color_descriptor and base_similarity > 0.9 and base_similarity > similarity:
                logger.info(f"Использую базовое сравнение для '{normalized_name}': {base_similarity}")
                score = base_similarity * 0.95
                has_similar_words = True
                
            fuzzy_scores.append((score, product))

            if score > best_score:
                best_score = score
                best_match = product

        if best_score >= threshold:
            if has_similar_words or has_color_descriptor:
                status = "partial"
            else:
                status = "ok"
        else:
            status = "unknown"

        total: Optional[Union[float, str]] = None
        price: Optional[Union[float, str]] = None
        if isinstance(pos, dict):
            total = pos.get("total")
            price = pos.get("price")
        else:
            total = getattr(pos, "total", None)
            price = getattr(pos, "price", None)

        # Приводим значения к float
        qty_f: Optional[float] = None
        total_f: Optional[float] = None
        price_f: Optional[float] = None
        
        try:
            if qty is not None:
                qty_f = float(qty)
        except (ValueError, TypeError):
            pass
            
        try:
            if total is not None:
                total_f = float(total)
        except (ValueError, TypeError):
            pass
            
        try:
            if price is not None:
                price_f = float(price)
        except (ValueError, TypeError):
            pass

        # Вычисляем price и line_total только если есть необходимые значения
        if price_f is None and total_f is not None and qty_f is not None and qty_f != 0:
            price_f = total_f / qty_f
            
        line_total_f: Optional[float] = None
        if price_f is not None and qty_f is not None and qty_f != 0:
            line_total_f = price_f * qty_f
        elif total_f is not None:
            line_total_f = total_f

        result: Dict[str, Any] = {
            "name": name,
            "qty": qty,
            "unit": unit,
            "status": status,
            "score": best_score if best_score > -1 else None,
            "price": price_f,
            "line_total": line_total_f,
        }

        if best_match and (status == "ok" or status == "partial"):
            if isinstance(best_match, dict):
                matched_name = best_match.get("name", "")
            else:
                matched_name = getattr(best_match, "name", "")
            result["matched_name"] = matched_name

        if return_suggestions and status == "unknown":
            fuzzy_scores.sort(reverse=True, key=lambda x: x[0])
            result["suggestions"] = [
                p
                for s, p in fuzzy_scores[:5]
                if s > settings.MATCH_MIN_SCORE
            ]

        results.append(result)

    return results
