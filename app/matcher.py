"""
Оптимизированная версия модуля сопоставления названий продуктов.
Включает кеширование, асинхронные операции и улучшенные алгоритмы.
"""

import asyncio
import logging
import re
import time
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple, TypedDict, TypeVar, Union

from rapidfuzz import fuzz, process

from app.config import settings
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
    Приводит к единственному числу и удаляет лишние слова.

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

    # Простые правила приведения к единственному числу
    if name.endswith("s") and len(name) > 3:
        # Обработка исключений
        if name.endswith("ies"):
            singular = name[:-3] + "y"
        elif name.endswith("es") and len(name) > 3 and name[-3] in "sxzh":
            singular = name[:-2]
        else:
            singular = name[:-1]

        # Если нашли синоним для единственного числа, используем его
        for base_name, variants in PRODUCT_VARIANTS.items():
            if singular == base_name or singular in variants:
                return base_name

        return singular

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
) -> Tuple[Optional[str], float]:
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
        # Возвращаем только название, как ожидают тесты
        return best_match, best_score * 100

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
    positions: List[Dict[str, Any]],
    products: List[Union[Product, Dict[str, Any]]],
    threshold: float = 0.7,
) -> List[Dict[str, Any]]:
    """
    Функция обратной совместимости для тестов.
    Сопоставляет позиции с продуктами и возвращает результаты в старом формате.

    Args:
        positions: Список позиций для сопоставления
        products: Список продуктов для поиска (объектов Product или словарей)
        threshold: Минимальный порог схожести

    Returns:
        Список результатов сопоставления
    """
    results = []

    for position in positions:
        # Находим лучшее совпадение
        match_result = find_best_match(position, products, threshold)

        # Формируем результат в старом формате
        result = position.copy()  # Сохраняем исходные данные позиции
        result["status"] = match_result["status"]
        result["confidence"] = match_result["confidence"]

        # ЗАЩИТА: Гарантируем что исходное имя сохранится
        original_name = position.get("name")
        if original_name is not None:
            result["name"] = original_name

        if match_result["matched_product"]:
            # Извлекаем название из продукта (словарь или объект)
            if isinstance(match_result["matched_product"], dict):
                matched_name = match_result["matched_product"].get("name", "")
            else:
                matched_name = getattr(match_result["matched_product"], "name", "")

            # ЗАЩИТА: Проверяем что matched_name не пустое
            if matched_name and str(matched_name).strip():
                result["matched_name"] = matched_name
            else:
                result["matched_name"] = None
            result["matched_product"] = match_result["matched_product"]
        else:
            result["matched_name"] = None
            result["matched_product"] = None

        results.append(result)

    # Логируем результаты
    matched_count = sum(1 for r in results if r["status"] == "ok")
    logger.info(f"Match results: {matched_count}/{len(results)} positions matched successfully")

    return results


# Функции обратной совместимости для тестов
def normalize_name(name: str) -> str:
    """Функция обратной совместимости для normalize_product_name"""
    if not name:
        return ""

    # Приводим к нижнему регистру
    name = name.lower()

    # Заменяем специальные символы на пробелы
    name = re.sub(r"[-_./]", " ", name)

    # Убираем лишние пробелы
    name = re.sub(r"\s+", " ", name).strip()

    return name


def normalize_unit(unit: str) -> str:
    """Нормализация единиц измерения"""
    if not unit:
        return ""

    unit = unit.lower().strip()

    # Словарь вариантов единиц измерения
    unit_variants = {
        # Килограмм
        "kilogram": "kg",
        "kilograms": "kg",
        "кг": "kg",
        "килограмм": "kg",
        "килограммы": "kg",
        # Штуки
        "piece": "pcs",
        "pieces": "pcs",
        "штука": "pcs",
        "штуки": "pcs",
        "шт": "pcs",
        # Литры
        "liter": "l",
        "liters": "l",
        "литр": "l",
        "литры": "l",
        # Граммы
        "gram": "g",
        "grams": "g",
        "грамм": "g",
        "граммы": "g",
    }

    return unit_variants.get(unit, unit)


def get_unit_variants(unit: str) -> set:
    """Получить все варианты единицы измерения"""
    unit_groups = {
        "kg": {"kg", "kilogram", "kilograms", "кг", "килограмм", "килограммы"},
        "pcs": {"pcs", "piece", "pieces", "штука", "штуки", "шт"},
        "l": {"l", "liter", "liters", "литр", "литры"},
        "g": {"g", "gram", "grams", "грамм", "граммы"},
    }

    normalized = normalize_unit(unit)
    return unit_groups.get(normalized, {unit})


def check_unit_compatibility(unit1: str, unit2: str) -> bool:
    """Проверить совместимость единиц измерения"""
    variants1 = get_unit_variants(unit1)
    variants2 = get_unit_variants(unit2)
    return bool(variants1 & variants2)


def calculate_similarity(s1: str, s2: str) -> float:
    """Функция обратной совместимости для calculate_string_similarity"""
    # Специальная обработка для пустых строк
    if not s1 and not s2:
        return 1.0
    if not s1 or not s2:
        return 0.0

    return calculate_string_similarity(s1, s2)


def fuzzy_match_product(
    query: str, products: List[Union[Product, Dict[str, Any]]], threshold: float = 0.7
) -> Tuple[Optional[Union[Product, Dict[str, Any]]], float]:
    """
    Нечеткий поиск продукта по названию или алиасу

    Args:
        query: Строка поиска
        products: Список продуктов (объектов Product или словарей)
        threshold: Минимальный порог схожести

    Returns:
        Кортеж (найденный продукт, оценка схожести)
    """
    if not query or not products:
        return None, 0.0

    best_product = None
    best_score = 0.0

    for product in products:
        # Работаем с объектами Product и словарями
        if isinstance(product, dict):
            product_name = product.get("name", "")
            product_alias = product.get("alias", "")
        else:
            product_name = getattr(product, "name", "")
            product_alias = getattr(product, "alias", "") if hasattr(product, "alias") else ""

        # Проверяем название
        name_score = calculate_string_similarity(query, product_name)

        # Проверяем алиас, если есть
        alias_score = 0.0
        if product_alias:
            alias_score = calculate_string_similarity(query, product_alias)

        # Берем лучшую оценку
        score = max(name_score, alias_score)

        if score > best_score:
            best_score = score
            best_product = product

    if best_score >= threshold:
        return best_product, best_score

    return None, best_score


def find_best_match(
    position: Dict[str, Any], products: List[Union[Product, Dict[str, Any]]], threshold: float = 0.7
) -> Dict[str, Any]:
    """
    Найти лучшее совпадение для позиции

    Args:
        position: Словарь с данными позиции (название, единица и т.д.)
        products: Список продуктов для поиска (объектов Product или словарей)
        threshold: Минимальный порог схожести

    Returns:
        Словарь с результатами поиска
    """
    position_name = position.get("name", "")
    position_unit = position.get("unit", "")
    position_price = position.get("price", None)

    # Ищем продукт
    matched_product, confidence = fuzzy_match_product(position_name, products, threshold)

    if matched_product is None:
        return {
            "matched_product": None,
            "confidence": confidence,
            "status": "unknown",
            "unit_match": False,
        }

    # Проверяем совместимость единиц
    unit_match = True
    status = "ok"

    if position_unit:
        if isinstance(matched_product, dict):
            product_unit = matched_product.get("unit", "")
        else:
            product_unit = (
                getattr(matched_product, "unit", "") if hasattr(matched_product, "unit") else ""
            )

        if product_unit:
            unit_match = check_unit_compatibility(position_unit, product_unit)
            if not unit_match:
                status = "unit_mismatch"

    # Учитываем подсказку цены, если есть
    if position_price:
        if isinstance(matched_product, dict):
            product_price_hint = matched_product.get("price_hint", None)
        else:
            product_price_hint = (
                getattr(matched_product, "price_hint", None)
                if hasattr(matched_product, "price_hint")
                else None
            )

        if product_price_hint:
            price_diff = abs(position_price - product_price_hint) / product_price_hint
            if price_diff > 0.5:  # Если цена отличается больше чем на 50%
                confidence *= 0.9  # Немного снижаем уверенность

    return {
        "matched_product": matched_product,
        "confidence": confidence,
        "status": status,
        "unit_match": unit_match,
    }


# Для тестов из test_fuzzy_match.py нужна старая версия normalize_product_name
def normalize_product_name_legacy(name: str) -> str:
    """
    Нормализация названия продукта для сопоставления с базой (старая версия).
    Приводит к единственному числу и удаляет лишние слова.

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

    # Простые правила приведения к единственному числу
    if name.endswith("s") and len(name) > 3:
        # Обработка исключений
        if name.endswith("ies"):
            singular = name[:-3] + "y"
        elif name.endswith("es") and len(name) > 3 and name[-3] in "sxzh":
            singular = name[:-2]
        else:
            singular = name[:-1]

        # Если нашли синоним для единственного числа, используем его
        for base_name, variants in PRODUCT_VARIANTS.items():
            if singular == base_name or singular in variants:
                return base_name

        return singular

    return name


# Переопределяем normalize_product_name для обратной совместимости с тестами
def normalize_product_name(name: str) -> str:
    """Функция обратной совместимости - использует старую логику приведения к единственному числу"""
    return normalize_product_name_legacy(name)

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
        if (s1_norm in variants or s1_norm == base_name) and (
            s2_norm in variants or s2_norm == base_name
        ):
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
            fuzzy_scores.sort(reverse=True, key=lambda x: x[0])
            result["suggestions"] = [p for s, p in fuzzy_scores[:5] if s > settings.MATCH_MIN_SCORE]

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
    logger.debug(
        f"Сопоставление выполнено за {total_time:.3f}с (среднее: {avg_time:.3f}с на позицию)"
    )

    # Удаляем временные поля
    for r in results:
        if "_match_time" in r:
            del r["_match_time"]

    return results


# --- Functions merged from app/matcher.py ---


def match_supplier(
    supplier_name: str, suppliers: List[Dict], threshold: Optional[float] = None
) -> Dict:
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
        threshold = settings.MATCH_THRESHOLD  # Assuming settings is available here, or pass it

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
        else:  # Assuming an object with attributes
            db_supplier_name = getattr(supplier_db_entry, "name", "")
            supplier_id = getattr(supplier_db_entry, "id", None)
            supplier_code = getattr(supplier_db_entry, "code", "")

        if not db_supplier_name:
            continue

        normalized_db_supplier_name = normalize_product_name(db_supplier_name)

        # Check for exact match first (case insensitive after normalization)
        if normalized_invoice_supplier_name == normalized_db_supplier_name:
            return {
                "name": db_supplier_name,  # Use the name from the database
                "id": supplier_id,
                "code": supplier_code,
                "status": "ok",
                "score": 1.0,
            }

        similarity = calculate_string_similarity(
            normalized_invoice_supplier_name, normalized_db_supplier_name
        )

        if similarity > best_score:
            best_score = similarity
            best_match_info = {
                "name": db_supplier_name,
                "id": supplier_id,
                "code": supplier_code,
            }

    if best_match_info and best_score >= threshold:
        return {**best_match_info, "status": "ok", "score": best_score}

    return {
        "name": supplier_name,
        "id": None,
        "status": "unknown",
        "score": (
            best_score if best_score > -1.0 else None
        ),  # Return best_score even if below threshold
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
        else:  # Assuming object
            product_name = getattr(product_item, "name", "")
            product_id = getattr(product_item, "id", None)

        if not product_name:
            continue

        normalized_product_name = normalize_product_name(product_name)
        score = calculate_string_similarity(normalized_query, normalized_product_name)

        if score >= threshold:
            results.append(
                {
                    "name": product_name,  # Original name from product list
                    "id": product_id,
                    "score": score,
                }
            )

    # Sort by score descending
    results.sort(key=lambda x: x["score"], reverse=True)
    return results


def fuzzy_best(
    name: str, catalog: List[Dict], threshold: Optional[float] = None
) -> Tuple[Optional[Dict], float]:
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
        threshold = settings.MATCH_MIN_SCORE  # Use MATCH_MIN_SCORE for selecting a single best

    if not name or not catalog:
        return None, 0.0

    normalized_query = normalize_product_name(name)

    best_score = -1.0
    best_match_product = None

    for product_item in catalog:
        product_name = ""
        if isinstance(product_item, dict):
            product_name = product_item.get("name", "")
        else:  # Assuming object
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

    return None, best_score  # Return best_score even if below threshold
