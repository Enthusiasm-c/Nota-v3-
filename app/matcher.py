import logging
from typing import Any, Dict, List, Optional, Union

from rapidfuzz import fuzz

from app.models import Position, Product
from app.utils.string_cache import (
    cached_string_similarity,
    get_string_similarity_cached,
    set_string_similarity_cached,
)

logger = logging.getLogger(__name__)


@cached_string_similarity
def calculate_string_similarity(s1: Optional[str], s2: Optional[str], **kwargs) -> float:
    """
    Вычисляет схожесть строк с кешированием и улучшенным алгоритмом.
    
    Использует комбинацию различных методов rapidfuzz для лучшего определения схожести:
    - fuzz.ratio: общая схожесть строк
    - fuzz.partial_ratio: находит совпадения подстрок (например "mayo" в "mayonnaise")
    - fuzz.token_sort_ratio: учитывает порядок слов
    
    Args:
        s1: Первая строка
        s2: Вторая строка
        **kwargs: Дополнительные параметры (для совместимости)
    
    Returns:
        Коэффициент схожести от 0 до 1
    """
    if s1 is None or s2 is None:
        return 0.0
    if s1 == s2:
        return 1.0
    
    # Нормализация строк для лучшего сопоставления
    s1_normalized = s1.lower().strip()
    s2_normalized = s2.lower().strip()
    
    # Проверяем кеш
    cached_result = get_string_similarity_cached(s1_normalized, s2_normalized)
    if cached_result is not None:
        return cached_result
    
    # Вычисляем различные метрики схожести
    ratio = fuzz.ratio(s1_normalized, s2_normalized) / 100
    partial_ratio = fuzz.partial_ratio(s1_normalized, s2_normalized) / 100
    token_sort_ratio = fuzz.token_sort_ratio(s1_normalized, s2_normalized) / 100
    
    # Комбинированный алгоритм:
    # 1. Если partial_ratio высокий (одна строка содержится в другой), учитываем это
    # 2. Используем взвешенную комбинацию метрик
    
    # Особая обработка случаев вложенности (например "mayo" в "mayonnaise")
    if partial_ratio > 0.9:
        # Если одна строка почти полностью содержится в другой
        # Учитываем длину строк - короткие аббревиатуры получают бонус
        len_diff = abs(len(s1_normalized) - len(s2_normalized))
        shorter_len = min(len(s1_normalized), len(s2_normalized))
        
        if shorter_len > 0 and len_diff <= shorter_len * 2:
            # Если разница в длине разумная, даем высокий балл
            similarity = max(ratio, 0.8)  # Минимум 80% для partial match
        else:
            similarity = partial_ratio * 0.9  # Снижаем если слишком разные длины
    else:
        # Стандартная комбинация метрик
        # 60% ratio + 30% partial_ratio + 10% token_sort_ratio
        similarity = (ratio * 0.6) + (partial_ratio * 0.3) + (token_sort_ratio * 0.1)
    
    # Ограничиваем результат диапазоном [0, 1]
    similarity = max(0.0, min(1.0, similarity))
    
    # Сохраняем в кеш
    set_string_similarity_cached(s1_normalized, s2_normalized, similarity)
    
    return similarity


def fuzzy_find(
    query: str,
    items: List[Union[Dict[str, Any], Product]],
    threshold: float = 0.75,
    key: str = "name",
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """
    Находит элементы, похожие на запрос, используя нечёткое сопоставление.
    
    Args:
        query: Строка для поиска
        items: Список элементов для поиска
        threshold: Минимальный порог схожести (0-1)
        key: Ключ/атрибут для сравнения
        limit: Максимальное количество результатов
    
    Returns:
        Список найденных элементов с добавленным полем 'score'
    """
    if not query or not items:
        return []
    
    results = []
    query_normalized = query.lower().strip()
    
    for item in items:
        # Получаем значение для сравнения
        if isinstance(item, dict):
            item_value = item.get(key, "")
            item_data = item.copy()
        else:
            item_value = getattr(item, key, "")
            item_data = {
                "id": getattr(item, "id", ""),
                "name": getattr(item, "name", ""),
                "alias": getattr(item, "alias", ""),
                "unit": getattr(item, "unit", ""),
            }
        
        if not item_value:
            continue
        
        # Вычисляем схожесть
        score = calculate_string_similarity(query_normalized, item_value)
        
        if score >= threshold:
            result = item_data.copy()
            result["score"] = score
            results.append(result)
    
    # Сортируем по убыванию схожести и ограничиваем количество
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]


def match_positions(
    positions: List[Dict[str, Any]],
    products: List[Union[Product, Dict[str, Any]]],
    threshold: float = 0.7,
) -> List[Dict[str, Any]]:
    """
    Сопоставляет позиции накладной с продуктами из базы данных.
    
    Args:
        positions: Список позиций из накладной
        products: Список продуктов из базы данных
        threshold: Минимальный порог схожести для сопоставления
    
    Returns:
        Список позиций с добавленными полями сопоставления
    """
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
        
        # Ищем лучшее совпадение
        matches = fuzzy_find(
            position_name,
            products,
            threshold=threshold,
            key="name",
            limit=1
        )
        
        result = position.copy()
        
        if matches:
            best_match = matches[0]
            result["status"] = "ok"
            result["score"] = best_match["score"]
            result["matched_name"] = best_match.get("name", "")
            result["matched_product"] = best_match
            result["id"] = best_match.get("id", "")
        else:
            result["status"] = "unknown"
            result["score"] = 0.0
            result["matched_name"] = None
            result["matched_product"] = None
            result["id"] = ""
        
        results.append(result)
    
    return results


async def async_match_positions(
    items: List[Union[Dict[str, Any], Position]],
    reference_items: List[Union[Dict[str, Any], Product]],
    threshold: float = 0.8,
    key: str = "name",
) -> List[Dict[str, Any]]:
    """
    Асинхронная версия функции сопоставления позиций.
    
    Внутренне использует синхронную версию, так как вычисления не требуют I/O.
    Сохранена для обратной совместимости.
    
    Args:
        items: Список позиций для сопоставления
        reference_items: Список эталонных элементов
        threshold: Минимальный порог схожести
        key: Ключ для сравнения
    
    Returns:
        Список сопоставленных позиций
    """
    # Преобразуем items в формат словарей если нужно
    positions = []
    for item in items:
        if isinstance(item, dict):
            positions.append(item)
        else:
            positions.append({
                "name": getattr(item, "name", ""),
                "qty": getattr(item, "qty", None),
                "unit": getattr(item, "unit", None),
                "price": getattr(item, "price", None),
                "total_price": getattr(item, "total_price", None),
            })
    
    # Используем синхронную версию
    return match_positions(positions, reference_items, threshold)


# Дополнительные утилиты для работы со строками
def normalize_product_name(name: str) -> str:
    """
    Нормализует название продукта для лучшего сопоставления.
    
    Args:
        name: Исходное название
    
    Returns:
        Нормализованное название
    """
    if not name:
        return ""
    
    # Удаляем лишние пробелы
    name = " ".join(name.split())
    
    # Удаляем специальные символы в начале и конце
    name = name.strip("-.,;:")
    
    # Приводим к нижнему регистру для сравнения
    return name.lower()


def get_best_match(
    query: str,
    items: List[Union[Dict[str, Any], Product]],
    threshold: float = 0.7,
    key: str = "name",
) -> Optional[Dict[str, Any]]:
    """
    Находит лучшее совпадение для строки запроса.
    
    Args:
        query: Строка для поиска
        items: Список элементов
        threshold: Минимальный порог
        key: Ключ для сравнения
    
    Returns:
        Лучшее совпадение или None
    """
    matches = fuzzy_find(query, items, threshold, key, limit=1)
    return matches[0] if matches else None