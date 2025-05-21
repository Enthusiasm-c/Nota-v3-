"""
Оптимизированная версия модуля сопоставления названий продуктов.
Включает кеширование, асинхронные операции и улучшенные алгоритмы.
"""
import logging
import asyncio
import time
from typing import List, Dict, Optional
from functools import lru_cache
import re

from rapidfuzz import fuzz
from app.config import settings
from app.utils.string_cache import get_string_similarity_cached, set_string_similarity_cached, cached_string_similarity

logger = logging.getLogger(__name__)

# Расширенный словарь синонимов и вариантов написания
PRODUCT_VARIANTS = {
    "romaine": ["romana", "romaine lettuce", "romaine salad"],
    "chickpeas": ["chick peas", "chickpea", "chick pea", "garbanzo", "garbanzo beans"],
    "green bean": ["green beans", "french beans", "string beans"],
    "english spinach": ["english spinach", "spinach", "baby spinach"],
    "tomato": ["tomatoes", "cherry tomato", "cherry tomatoes", "roma tomato", "roma tomatoes"],
    "eggplant": ["aubergine", "eggplants", "purple eggplant"],
    "watermelon": ["water melon", "watermelons", "seedless watermelon"],
    "chili": ["chilli", "chilies", "chillies", "red chili", "green chili"],
    "mango": ["mangoes", "champagne mango", "ataulfo mango"],
    "lettuce": ["iceberg", "iceberg lettuce", "lettuce heads"],
    "potato": ["potatoes", "white potato", "russet potato"],
    "onion": ["onions", "white onion", "red onion", "yellow onion"]
}

# Шаблон для поиска единиц измерения
UNIT_PATTERN = re.compile(r'(\d+(?:\.\d+)?)\s*((?:kg|g|l|ml|oz|lb|pcs|pack|box|ctn|each|unit|bunch)s?)', re.IGNORECASE)

# Кеш для сохранения предварительно вычисленных результатов сопоставления
_position_match_cache = {}

@lru_cache(maxsize=1000)
def normalize_product_name(name: str) -> str:
    """
    Улучшенная нормализация названия продукта с кешированием.
    
    Args:
        name: Исходное название продукта
        
    Returns:
        Нормализованное название
    """
    if not name:
        return ""
    
    # Приводим к нижнему регистру и удаляем лишние пробелы
    name = name.lower().strip()
    
    # Удаляем слова-филлеры, которые не меняют смысл
    fillers = ["fresh", "organic", "premium", "quality", "natural", "extra"]
    for filler in fillers:
        if name.startswith(filler + " "):
            name = name[len(filler)+1:]
        name = name.replace(" " + filler + " ", " ")
        if name.endswith(" " + filler):
            name = name[:-len(filler)-1]
    
    # Проверяем в словаре синонимов
    for base_name, variants in PRODUCT_VARIANTS.items():
        if name in variants or name == base_name:
            return base_name
    
    # Обрабатываем множественные/единственные формы
    if name.endswith("es"):
        singular = name[:-2]
        if singular + "es" == name:
            return singular
    elif name.endswith("s"):
        singular = name[:-1]
        if singular + "s" == name:
            return singular
    
    # Удаляем цифры и единицы измерения в конце названия
    match = UNIT_PATTERN.search(name)
    if match:
        quantity, unit = match.groups()
        name = name.replace(match.group(0), "").strip()
    
    return name

@cached_string_similarity
def calculate_string_similarity(s1: str, s2: str) -> float:
    """
    Улучшенная версия расчета сходства строк с кешированием.
    
    Args:
        s1, s2: Строки для сравнения
        
    Returns:
        Оценка сходства в диапазоне 0.0-1.0
    """
    # Проверяем кеш через глобальный кеш
    cached = get_string_similarity_cached(s1, s2)
    if cached is not None:
        return cached
    
    # Если обе строки пустые или равны друг другу, это считается полным совпадением
    if (not s1 and not s2) or s1 == s2:
        return 1.0
    # Если только одна строка пустая, совпадения нет
    elif not s1 or not s2:
        return 0.0
    
    # Нормализация
    s1 = s1.lower().strip()
    s2 = s2.lower().strip()
    
    # Точное совпадение
    if s1 == s2:
        return 1.0

    # Нормализация названий продуктов
    s1_norm = normalize_product_name(s1)
    s2_norm = normalize_product_name(s2)
    
    if s1_norm == s2_norm:
        result = 0.95
        set_string_similarity_cached(s1, s2, result)
        return result
    
    # Используем алгоритм ratio из rapidfuzz
    ratio_score = fuzz.ratio(s1_norm, s2_norm) / 100.0
    
    # Используем частичное соответствие для более длинных строк
    partial_score = fuzz.partial_ratio(s1_norm, s2_norm) / 100.0
    
    # Используем сравнение по токенам для многословных названий
    token_score = fuzz.token_sort_ratio(s1_norm, s2_norm) / 100.0
    
    # Взвешенное среднее всех методов
    base_score = 0.5 * ratio_score + 0.3 * partial_score + 0.2 * token_score
    
    # Проверяем на частичное вхождение
    if s1_norm in s2_norm or s2_norm in s1_norm:
        base_score = max(base_score, 0.85)
    
    # Проверка на варианты из словаря
    for base_name, variants in PRODUCT_VARIANTS.items():
        if (s1_norm in variants or s1_norm == base_name) and (s2_norm in variants or s2_norm == base_name):
            result = 0.95
            set_string_similarity_cached(s1, s2, result)
            return result
    
    # Сохраняем результат в кеше
    set_string_similarity_cached(s1, s2, base_score)
    return base_score

async def async_match_positions(
    positions: List[Dict],
    products: List[Dict],
    threshold: Optional[float] = None,
    return_suggestions: bool = False,
) -> List[Dict]:
    """
    Асинхронная версия сопоставления позиций для повышения производительности.
    
    Args:
        positions: Список позиций для сопоставления
        products: Список продуктов из базы
        threshold: Порог сходства
        return_suggestions: Возвращать ли предложения для неопознанных позиций
        
    Returns:
        Список сопоставленных позиций
    """
    if threshold is None:
        threshold = settings.MATCH_THRESHOLD
    
    # Кешируем нормализованные названия продуктов для быстрого поиска
    product_names = {}
    for product in products:
        if isinstance(product, dict):
            name = product.get("name", "")
            product_id = product.get("id", "")
        else:
            name = getattr(product, "name", "")
            product_id = getattr(product, "id", "")
            
        if name:
            norm_name = normalize_product_name(name.lower().strip())
            product_names[norm_name] = {"product": product, "name": name, "id": product_id}
    
    # Создаем задачи для асинхронного сопоставления
    async def match_position(pos, pos_index):
        start_time = time.time()
        
        name = getattr(pos, "name", None)
        if name is None and isinstance(pos, dict):
            name = pos.get("name", "")
            
        # Проверяем кеш по названию
        cache_key = (name, threshold, return_suggestions)
        if cache_key in _position_match_cache:
            result = _position_match_cache[cache_key].copy()
            result["_match_time"] = 0  # Время из кеша = 0
            return pos_index, result
        
        qty = getattr(pos, "qty", None)
        if qty is None and isinstance(pos, dict):
            qty = pos.get("qty", "")
            
        unit = getattr(pos, "unit", None)
        if unit is None and isinstance(pos, dict):
            unit = pos.get("unit", "")
            
        best_match = None
        best_score = -1.0
        status = "unknown"
        fuzzy_scores = []
        
        # Нормализуем название для быстрого поиска
        normalized_name = normalize_product_name(name.lower().strip()) if name else ""
        
        # Сначала проверяем точное совпадение по нормализованному названию
        if normalized_name in product_names:
            product_data = product_names[normalized_name]
            best_match = product_data["product"]
            best_score = 1.0
            status = "ok"
        else:
            # Если нет точного совпадения, ищем нечеткое
            for product in products:
                if isinstance(product, dict):
                    compare_val = product.get("name", "")
                else:
                    compare_val = getattr(product, "name", "")
                    
                normalized_compare = normalize_product_name(compare_val.lower().strip())
                
                # Используем кешированное вычисление сходства
                similarity = calculate_string_similarity(normalized_name, normalized_compare)
                fuzzy_scores.append((similarity, product))
                
                if similarity > best_score:
                    best_score = similarity
                    best_match = product
            
            # Определяем статус
            if best_score >= threshold:
                status = "ok"
            else:
                status = "unknown"
        
        # Обрабатываем числовые поля
        total = None
        price = None
        if isinstance(pos, dict):
            total = pos.get("total")
            price = pos.get("price")
        else:
            total = getattr(pos, "total", None)
            price = getattr(pos, "price", None)
            
        # Приводим значения к числовым типам
        try:
            qty_f = float(qty) if qty and qty != "" else None
        except (ValueError, TypeError):
            qty_f = None
            
        try:
            total_f = float(total) if total and total != "" else None
        except (ValueError, TypeError):
            total_f = None
            
        try:
            price_f = float(price) if price and price != "" else None
        except (ValueError, TypeError):
            price_f = None
            
        # Вычисляем недостающие значения
        if price_f is None and total_f is not None and qty_f not in (None, 0):
            price_f = total_f / qty_f
            
        line_total_f = None
        if price_f is not None and qty_f not in (None, 0):
            line_total_f = price_f * qty_f
        elif total_f is not None:
            line_total_f = total_f
            
        # Формируем результат
        result = {
            "name": name,
            "qty": qty,
            "unit": unit,
            "status": status,
            "score": best_score if best_score > 0 else None,
            "price": price_f,
            "line_total": line_total_f,
        }
        
        # Добавляем название из базы, если нашли соответствие
        if best_match and status == "ok":
            if isinstance(best_match, dict):
                matched_name = best_match.get("name", "")
            else:
                matched_name = getattr(best_match, "name", "")
            result["matched_name"] = matched_name
            
        # Добавляем предложения для неопознанных позиций
        if return_suggestions and status == "unknown":
            fuzzy_scores.sort(
                reverse=True, key=lambda x: x[0]
            )
            result["suggestions"] = [
                p
                for s, p in fuzzy_scores[:5]
                if s > settings.MATCH_MIN_SCORE
            ]
            
        # Замеряем время выполнения
        match_time = time.time() - start_time
        result["_match_time"] = match_time
        
        # Сохраняем в кеше для будущих запросов
        _position_match_cache[cache_key] = result.copy()
        
        return pos_index, result
    
    # Запускаем задачи асинхронно
    tasks = [match_position(pos, i) for i, pos in enumerate(positions)]
    results_with_index = await asyncio.gather(*tasks)
    
    # Восстанавливаем исходный порядок
    results_with_index.sort(key=lambda x: x[0])
    results = [r[1] for r in results_with_index]
    
    # Собираем статистику по времени
    total_time = sum(r.get("_match_time", 0) for r in results)
    avg_time = total_time / len(results) if results else 0
    logger.debug(f"Сопоставление выполнено за {total_time:.3f}с (среднее: {avg_time:.3f}с на позицию)")
    
    # Удаляем временные поля
    for r in results:
        if "_match_time" in r:
            del r["_match_time"]
    
    return results

# --- Functions merged from app/matcher.py ---

def match_supplier(supplier_name: str, suppliers: List[Dict], threshold: Optional[float] = None) -> Dict:
    """
    Match supplier name with supplier database using fuzzy matching.
    Adapted to use the improved normalization and similarity functions.
    
    Args:
        supplier_name: Supplier name from the invoice
        suppliers: List of supplier dictionaries from the database
        threshold: Similarity threshold
        
    Returns:
        Dictionary with matched supplier data or original name if no match found
    """
    if threshold is None:
        threshold = settings.MATCH_THRESHOLD # Assuming settings is available here, or pass it

    if not supplier_name or not suppliers:
        return {"name": supplier_name, "id": None, "status": "unknown"}
    
    # Use normalize_product_name for consistency, though it's product-focused,
    # basic lowercasing and stripping is what's mostly needed here.
    # Or, create a specific normalize_supplier_name if different logic is needed.
    normalized_invoice_supplier_name = normalize_product_name(supplier_name) 
    best_match_info = None
    best_score = -1.0
    
    for supplier_db_entry in suppliers:
        db_supplier_name = ""
        supplier_id = None
        supplier_code = ""

        if isinstance(supplier_db_entry, dict):
            db_supplier_name = supplier_db_entry.get("name", "")
            supplier_id = supplier_db_entry.get("id")
            supplier_code = supplier_db_entry.get("code", "")
        else: # Assuming an object with attributes
            db_supplier_name = getattr(supplier_db_entry, "name", "")
            supplier_id = getattr(supplier_db_entry, "id", None)
            supplier_code = getattr(supplier_db_entry, "code", "")
            
        if not db_supplier_name:
            continue
            
        normalized_db_supplier_name = normalize_product_name(db_supplier_name)

        # Check for exact match first (case insensitive after normalization)
        if normalized_invoice_supplier_name == normalized_db_supplier_name:
            return {
                "name": db_supplier_name, # Use the name from the database
                "id": supplier_id,
                "code": supplier_code,
                "status": "ok",
                "score": 1.0
            }
            
        similarity = calculate_string_similarity(normalized_invoice_supplier_name, normalized_db_supplier_name)
        
        if similarity > best_score:
            best_score = similarity
            best_match_info = {
                "name": db_supplier_name,
                "id": supplier_id,
                "code": supplier_code,
            }
    
    if best_match_info and best_score >= threshold:
        return {
            **best_match_info,
            "status": "ok",
            "score": best_score
        }
    
    return {
        "name": supplier_name,
        "id": None,
        "status": "unknown",
        "score": best_score if best_score > -1.0 else None # Return best_score even if below threshold
    }

def fuzzy_find(query: str, products: List[Dict], threshold: Optional[float] = None) -> List[Dict]:
    """
    Find products using fuzzy matching.
    Adapted to use improved normalization and similarity.
    
    Args:
        query: Search query
        products: List of product dicts (expected to have 'name' and 'id')
        threshold: Similarity threshold
        
    Returns:
        List of matching products with scores
    """
    if threshold is None:
        threshold = settings.MATCH_THRESHOLD

    if not query or not products:
        return []
    
    normalized_query = normalize_product_name(query)
    
    results = []
    for product_item in products:
        product_name = ""
        product_id = None
        if isinstance(product_item, dict):
            product_name = product_item.get("name", "")
            product_id = product_item.get("id")
        else: # Assuming object
            product_name = getattr(product_item, "name", "")
            product_id = getattr(product_item, "id", None)

        if not product_name:
            continue
            
        normalized_product_name = normalize_product_name(product_name)
        score = calculate_string_similarity(normalized_query, normalized_product_name)
        
        if score >= threshold:
            results.append({
                "name": product_name, # Original name from product list
                "id": product_id,
                "score": score
            })
            
    # Sort by score descending
    results.sort(key=lambda x: x["score"], reverse=True)
    return results

def fuzzy_best(name: str, catalog: List[Dict], threshold: Optional[float] = None) -> Tuple[Optional[Dict], float]:
    """
    Finds the best product match in a catalog list.
    Returns the matched product dict and score.
    
    Args:
        name: Name to search for
        catalog: List of product dicts (must have 'name' and 'id')
        threshold: Min similarity score
        
    Returns:
        Tuple (best_matched_product_dict, score), or (None, 0.0) if no good match
    """
    if threshold is None:
        threshold = settings.MATCH_MIN_SCORE # Use MATCH_MIN_SCORE for selecting a single best

    if not name or not catalog:
        return None, 0.0

    normalized_query = normalize_product_name(name)
    
    best_score = -1.0
    best_match_product = None
    
    for product_item in catalog:
        product_name = ""
        if isinstance(product_item, dict):
            product_name = product_item.get("name", "")
        else: # Assuming object
            product_name = getattr(product_item, "name", "")

        if not product_name:
            continue
        
        normalized_product_name = normalize_product_name(product_name)
        score = calculate_string_similarity(normalized_query, normalized_product_name)
        
        if score > best_score:
            best_score = score
            best_match_product = product_item
            
    if best_match_product and best_score >= threshold:
        return best_match_product, best_score
    
    return None, best_score # Return best_score even if below threshold