"""
Оптимизированная версия модуля сопоставления названий продуктов.
Включает кеширование, асинхронные операции и улучшенные алгоритмы.
"""

import logging
import re
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple, TypedDict, TypeVar, Union

from rapidfuzz import fuzz, process

from app.models import Position, Product
from app.utils.string_cache import (
    cached_string_similarity,
    get_string_similarity_cached,
    set_string_similarity_cached,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ProductVariant(TypedDict):
    name: str
    variants: List[str]


class MatchResult(TypedDict):
    name: str
    score: float
    original: Dict[str, Any]


# Расширенный словарь синонимов и вариантов написания
PRODUCT_VARIANTS: Dict[str, List[str]] = {
    "romaine": ["romana", "romaine lettuce", "romaine salad"],
    "chickpeas": ["chick peas", "chickpea", "chick pea", "garbanzo", "garbanzo beans"],
    "green bean": ["green beans", "french beans", "string beans"],
    "english spinach": ["english spinach", "spinach", "baby spinach"],
    "tomato": ["cherry tomato", "cherry tomatoes", "roma tomato", "roma tomatoes"],
    "eggplant": ["aubergine", "purple eggplant"],
    "watermelon": ["water melon", "watermelons", "seedless watermelon"],
    "chili": ["chilli", "chilies", "chillies", "red chili", "green chili"],
    "mango": ["mangoes", "champagne mango", "ataulfo mango"],
    "lettuce": ["iceberg", "iceberg lettuce", "lettuce heads"],
    "potato": ["potatoes", "white potato", "russet potato"],
    "onion": ["onions", "white onion", "red onion", "yellow onion"],
}

# Шаблон для поиска единиц измерения
UNIT_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*((?:kg|g|l|ml|oz|lb|pcs|pack|box|ctn|each|unit|bunch)s?)", re.IGNORECASE
)

# Кеш для сохранения предварительно вычисленных результатов сопоставления
_position_match_cache: Dict[Tuple[str, float, bool], Dict[str, Any]] = {}


@lru_cache(maxsize=1000)
def normalize_product_name(name: str) -> str:
    """
    Нормализация названия продукта для сопоставления с базой.
    Сохраняет оригинальную форму слова (единственное/множественное число),
    но удаляет лишние слова и нормализует регистр.

    Args:
        name: Исходное название продукта

    Returns:
        Нормализованное название
    """
    if not name:
        return ""

    if name is None:
        return ""

    # Приводим к нижнему регистру и удаляем лишние пробелы
    name = name.lower().strip()

    # Удаляем единицы измерения в конце названия
    match = UNIT_PATTERN.search(name)
    if match:
        name = name.replace(match.group(0), "").strip()

    # Удаляем слова-филлеры, которые не меняют смысл
    fillers = ["fresh", "organic", "premium", "quality", "natural", "extra"]
    for filler in fillers:
        if name.startswith(filler + " "):
            name = name[len(filler) + 1 :]
        name = name.replace(" " + filler + " ", " ")
        if name.endswith(" " + filler):
            name = name[: -len(filler) - 1]

    # Проверяем на синонимы в словаре PRODUCT_VARIANTS
    for base_name, variants in PRODUCT_VARIANTS.items():
        # Точное совпадение с базовым именем
        if name == base_name:
            return name
        # Точное совпадение с вариантами
        if name in variants:
            return base_name

    return name


def _is_plural_variant(s1: str, s2: str) -> bool:
    """Проверяет, являются ли строки вариантами единственного/множественного числа"""
    if s1 == s2:
        return False

    # Простые правила для английского языка
    if s1.endswith("s") and s2 == s1[:-1]:  # cats -> cat
        return True
    if s2.endswith("s") and s1 == s2[:-1]:  # cat -> cats
        return True
    if s1.endswith("ies") and s2 == s1[:-3] + "y":  # berries -> berry
        return True
    if s2.endswith("ies") and s1 == s2[:-3] + "y":  # berry -> berries
        return True

    return False


@cached_string_similarity
def calculate_string_similarity(s1: Optional[str], s2: Optional[str], **kwargs) -> float:
    """
    Вычисляет схожесть двух строк с использованием различных метрик.

    Args:
        s1: Первая строка
        s2: Вторая строка

    Returns:
        Оценка схожести от 0 до 1
    """
    # Проверяем на None
    if s1 is None or s2 is None:
        return 0.0

    # Проверяем кеш
    cached_result = get_string_similarity_cached(s1, s2)
    if cached_result is not None:
        return cached_result

    # Нормализуем строки
    s1_norm = normalize_product_name(s1)
    s2_norm = normalize_product_name(s2)

    # Если после нормализации строки пустые, возвращаем 0
    if not s1_norm or not s2_norm:
        return 0.0

    # Если строки идентичны после нормализации
    if s1_norm == s2_norm:
        result = 1.0
        set_string_similarity_cached(s1, s2, result)
        return result

    # Используем RapidFuzz для вычисления схожести
    ratio_score = fuzz.ratio(s1_norm, s2_norm) / 100
    partial_ratio_score = fuzz.partial_ratio(s1_norm, s2_norm) / 100
    token_sort_score = fuzz.token_sort_ratio(s1_norm, s2_norm) / 100
    token_set_score = fuzz.token_set_ratio(s1_norm, s2_norm) / 100

    # Вычисляем взвешенную оценку с приоритетом на token_sort и token_set
    base_score = (
        ratio_score * 0.2
        + partial_ratio_score * 0.2
        + token_sort_score * 0.3
        + token_set_score * 0.3
    )

    # Проверяем на частичное вхождение
    if s1_norm in s2_norm or s2_norm in s1_norm:
        base_score = max(base_score, 0.85)

    # Добавляем бонус для множественного числа
    if _is_plural_variant(s1_norm, s2_norm):
        base_score = min(1.0, base_score + 0.15)  # Увеличиваем бонус до 0.15

    # Если одна строка является префиксом другой, уменьшаем оценку
    if len(s1_norm) < len(s2_norm) and s2_norm.startswith(s1_norm):
        base_score *= 0.8  # Уменьшаем оценку для префиксов
    elif len(s2_norm) < len(s1_norm) and s1_norm.startswith(s2_norm):
        base_score *= 0.8  # Уменьшаем оценку для префиксов

    # Сохраняем результат в кеше
    set_string_similarity_cached(s1, s2, base_score)
    return base_score


# Обертка-скорер для использования в rapidfuzz (ожидает int 0-100)
def _rapid_similarity(s1: str, s2: str, *, processor=None, score_cutoff=None) -> int:
    """Совместимый с rapidfuzz scorer, использующий calculate_string_similarity (0-1)"""
    score = int(calculate_string_similarity(s1, s2) * 100)
    if score_cutoff is not None and score < score_cutoff:
        return 0
    return score


async def async_match_positions(
    items: List[Union[Dict[str, Any], Position]],
    reference_items: List[Union[Dict[str, Any], Product]],
    threshold: float = 0.8,
    key: str = "name",
) -> List[Dict[str, Any]]:
    """
    Асинхронно сопоставляет позиции с референсными данными.

    Args:
        items: Список позиций для сопоставления (словари или объекты Position)
        reference_items: Список референсных позиций (словари или объекты Product)
        threshold: Порог схожести (0-1)
        key: Ключ для сравнения

    Returns:
        Список совпадений с полями status и score
    """
    results = []

    # Создаем список названий продуктов из базы для быстрого поиска
    reference_names = []
    reference_dict = {}

    for ref_item in reference_items:
        if isinstance(ref_item, dict):
            ref_name = ref_item.get(key, "").lower().strip()
            reference_dict[ref_name] = ref_item
        else:
            ref_name = getattr(ref_item, key, "").lower().strip()
            reference_dict[ref_name] = ref_item
        if ref_name:
            reference_names.append(ref_name)

    for item in items:
        # Получаем значение атрибута в зависимости от типа объекта
        if isinstance(item, dict):
            item_name = item.get(key, "")
            if item_name is None:
                item_name = ""
            item_name = item_name.lower().strip()
            item_data = item.copy()
        else:
            item_name = getattr(item, key, "")
            if item_name is None:
                item_name = ""
            item_name = item_name.lower().strip()
            if hasattr(item, "model_dump"):
                item_data = item.model_dump()
            else:
                item_data = {
                    "name": getattr(item, "name", ""),
                    "qty": getattr(item, "qty", None),
                    "unit": getattr(item, "unit", None),
                    "price": getattr(item, "price", None),
                    "total": getattr(item, "total", None),
                }

        if not item_name:
            results.append({"status": "unknown", "score": 0.0})
            continue

        # Используем process.extractOne с обновленным API
        best_match = process.extractOne(
            item_name, reference_names, scorer=_rapid_similarity, score_cutoff=int(threshold * 100)
        )

        if best_match:
            matched_name, score, _ = best_match
            score = score / 100  # Конвертируем обратно в float 0-1
            if score >= threshold:
                ref_item = reference_dict[matched_name]

                # Преобразуем объект Product в словарь, если это объект
                if isinstance(ref_item, Product):
                    ref_data = ref_item.model_dump()
                else:
                    ref_data = ref_item.copy()

                # Сохраняем все атрибуты исходной позиции
                result = item_data.copy()
                # Добавляем атрибуты из найденного совпадения
                result.update(ref_data)
                # Добавляем статус и оценку
                result["status"] = "ok"
                result["score"] = score
                results.append(result)
        else:
            # Если совпадение не найдено, возвращаем исходные данные с нулевой оценкой
            result = item_data.copy()
            result["status"] = "unknown"
            result["score"] = 0.0
            results.append(result)

    return results


def fuzzy_find(
    query: str,
    items: List[Union[Dict[str, Any], Any]],
    threshold: float = 0.6,
    key: str = "name",
    limit: int = 5,
) -> List[MatchResult]:
    """
    Нечеткий поиск по списку элементов.

    Args:
        query: Строка поиска
        items: Список элементов для поиска (словари или объекты)
        threshold: Минимальный порог схожести (0-1)
        key: Ключ для поиска в словарях
        limit: Максимальное количество результатов

    Returns:
        Список найденных элементов с оценками схожести
    """
    if not query or not items:
        return []

    # Нормализуем запрос
    query = normalize_product_name(query)
    if not query:
        return []

    # Создаем список названий для поиска
    choices = []
    choice_map = {}

    for item in items:
        if isinstance(item, dict):
            name = item.get(key, "")
        else:
            name = getattr(item, key, "")

        if name:
            name = name.lower().strip()
            choices.append(name)
            choice_map[name] = item

    # Используем process.extract для поиска совпадений
    matches = []
    for choice in choices:
        score = calculate_string_similarity(query, choice)
        if score >= threshold:
            matches.append((choice, score))

    # Сортируем результаты по убыванию оценки
    matches.sort(key=lambda x: x[1], reverse=True)
    matches = matches[:limit]

    results = []
    for name, score in matches:
        original = choice_map[name]

        result: MatchResult = {
            "name": name,
            "score": score,
            "original": original,  # сохраняем объект как есть
        }
        results.append(result)

    return results


def fuzzy_best(
    query: str,
    items: Union[Dict[str, Any], List[Dict[str, Any]]],
    threshold: Optional[float] = None,
) -> Tuple[Optional[Dict[str, Any]], float]:
    """
    Находит наиболее похожий элемент в словаре или списке.

    Args:
        query: Строка поиска
        items: Словарь или список элементов для поиска
        threshold: Минимальный порог схожести (0-1)

    Returns:
        Кортеж (найденный элемент, оценка схожести)
    """
    if not query:
        return "", 0.0

    # Нормализуем запрос
    query = normalize_product_name(query)
    if not query:
        return "", 0.0

    # Преобразуем входные данные в список для поиска
    if isinstance(items, dict):
        choices = list(items.keys())
        items_dict = items
    else:
        choices = [item.get("name", "") for item in items if item.get("name")]
        items_dict = {item["name"]: item for item in items if item.get("name")}

    if not choices:
        return "", 0.0

    # Ищем лучшее совпадение
    best_match = None
    best_score = 0.0

    for choice in choices:
        score = calculate_string_similarity(query, choice)
        if threshold is None or score >= threshold:
            if score > best_score:
                best_match = choice
                best_score = score

    if best_match:
        result = {
            "name": best_match,
            "id": (
                items_dict[best_match]
                if isinstance(items, dict)
                else items_dict[best_match].get("id")
            ),
        }
        # Масштабируем score от 0 до 100 для совместимости с тестами
        return result, best_score * 100

    return "", 0.0


def match_supplier(
    supplier_name: str,
    suppliers: List[Dict],
    threshold: Optional[float] = None,
) -> Dict:
    """
    Находит поставщика по названию в списке поставщиков.

    Args:
        supplier_name: Название поставщика для поиска
        suppliers: Список поставщиков
        threshold: Минимальный порог схожести (0-1)

    Returns:
        Словарь с информацией о найденном поставщике
    """
    if not supplier_name:
        return {"name": supplier_name, "id": None, "code": None, "status": "unknown", "score": 0.0}

    # Создаем список названий для поиска
    choices = []
    supplier_map = {}

    for supplier in suppliers:
        if isinstance(supplier, dict):
            name = supplier.get("name", "")
        else:
            name = getattr(supplier, "name", "")

        if name:
            name_orig = name
            name = name.lower().strip()
            choices.append(name)
            supplier_map[name] = {
                "name": name_orig,
                "id": (
                    supplier.get("id", None)
                    if isinstance(supplier, dict)
                    else getattr(supplier, "id", None)
                ),
                "code": (
                    supplier.get("code", None)
                    if isinstance(supplier, dict)
                    else getattr(supplier, "code", None)
                ),
            }

    if not choices:
        return {"name": supplier_name, "id": None, "code": None, "status": "unknown", "score": 0.0}

    # Используем process.extractOne для поиска лучшего совпадения
    threshold_local = threshold if threshold is not None else 0.8
    best_match = process.extractOne(
        supplier_name,
        choices,
        scorer=_rapid_similarity,
        score_cutoff=int(threshold_local * 100) if threshold_local is not None else None,
    )

    if best_match:
        matched_name, score, _ = best_match
        score = score / 100  # Конвертируем обратно в float 0-1
        if threshold_local is None or score >= threshold_local:
            supplier = supplier_map[matched_name]
            return {
                "name": supplier["name"],
                "id": supplier["id"],
                "code": supplier["code"],
                "status": "ok",
                "score": score,
            }

    return {"name": supplier_name, "id": None, "code": None, "status": "unknown", "score": 0.0}


def match_positions(
    items: List[Union[Dict[str, Any], Position]],
    reference_items: List[Union[Dict[str, Any], Product]],
    threshold: float = 0.8,
    key: str = "name",
    return_suggestions: bool = False,
) -> List[Dict[str, Any]]:
    """
    Синхронная версия сопоставления позиций с референсными данными.

    Args:
        items: Список позиций для сопоставления
        reference_items: Список референсных позиций
        threshold: Порог схожести (0-1)
        key: Ключ для сравнения
        return_suggestions: Возвращать ли предложения для неизвестных позиций

    Returns:
        Список совпадений с полями status и score
    """
    # Создаем список названий продуктов из базы для быстрого поиска
    reference_names = []
    reference_dict = {}

    for ref_item in reference_items:
        if isinstance(ref_item, dict):
            ref_name = ref_item.get(key, "").lower().strip()
        else:
            ref_name = getattr(ref_item, key, "").lower().strip()
        if ref_name:
            reference_names.append(ref_name)
            reference_dict[ref_name] = ref_item

    results = []
    for item in items:
        # Получаем значение атрибута в зависимости от типа объекта
        if isinstance(item, dict):
            item_name = item.get(key, "")
            if item_name is None:
                item_name = ""
            item_name = item_name.lower().strip()
            item_data = item.copy()
        else:
            item_name = getattr(item, key, "")
            if item_name is None:
                item_name = ""
            item_name = item_name.lower().strip()
            if hasattr(item, "model_dump"):
                item_data = item.model_dump()
            else:
                item_data = {
                    "name": getattr(item, "name", ""),
                    "qty": getattr(item, "qty", None),
                    "unit": getattr(item, "unit", None),
                    "price": getattr(item, "price", None),
                    "total": getattr(item, "total", None),
                }

        if not item_name:
            result = {"status": "unknown", "score": 0.0}
            if item_data:
                result.update(item_data)
            results.append(result)
            continue

        # Ищем лучшее совпадение
        best_score = 0.0
        best_match = None
        for ref_name in reference_names:
            score = calculate_string_similarity(item_name, ref_name)
            if score > best_score:
                best_score = score
                best_match = ref_name

        if best_match and best_score >= threshold:
            ref_item = reference_dict[best_match]

            # Преобразуем объект Product в словарь
            if isinstance(ref_item, Product):
                ref_data = ref_item.model_dump()
            elif hasattr(ref_item, "model_dump"):
                ref_data = ref_item.model_dump()
            elif hasattr(ref_item, "__dict__"):
                ref_data = ref_item.__dict__.copy()
            else:
                ref_data = ref_item.copy()

            # Сохраняем все атрибуты исходной позиции
            result = item_data.copy()
            # Добавляем атрибуты из найденного совпадения
            result.update(ref_data)
            # Восстанавливаем оригинальное имя
            result["name"] = item_data.get("name", "")
            # Добавляем статус и оценку
            result["status"] = "ok"
            result["score"] = best_score
            # Вычисляем total, если есть qty и price
            if result.get("qty") is not None and result.get("price") is not None:
                result["total"] = result["qty"] * result["price"]
            results.append(result)
        else:
            # Если совпадение не найдено или ниже порога
            result = item_data.copy()
            result["status"] = "unknown"
            result["score"] = best_score

            # Добавляем предложения, если требуется
            if return_suggestions and best_score >= threshold * 0.8:
                suggestions = []
                for ref_name in reference_names:
                    score = calculate_string_similarity(item_name, ref_name)
                    if score >= threshold * 0.8:
                        ref_item = reference_dict[ref_name]
                        if isinstance(ref_item, Product):
                            sugg_data = ref_item.model_dump()
                        elif hasattr(ref_item, "model_dump"):
                            sugg_data = ref_item.model_dump()
                        elif hasattr(ref_item, "__dict__"):
                            sugg_data = ref_item.__dict__.copy()
                        else:
                            sugg_data = ref_item.copy()
                        suggestions.append(
                            {
                                "name": ref_name,
                                "score": score,
                                "data": sugg_data,
                            }
                        )
                if suggestions:
                    # Сортируем предложения по убыванию оценки и берем top 3
                    suggestions.sort(key=lambda x: x["score"], reverse=True)
                    result["suggestions"] = suggestions[:3]

            results.append(result)

    return results
