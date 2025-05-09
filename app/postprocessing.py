import re
import logging
from typing import Optional, List
from app.models import ParsedData, Position
from app.data_loader import load_products
from app.utils.enhanced_logger import log_indonesian_invoice, log_format_issues

# Автокоррекция числовых значений (поддержка 10,000 10.000 10k 10к и т.д.)
def clean_num(val) -> Optional[float]:
    if val in (None, "", "null", "—"):
        return None
    
    # Предварительная очистка от валютных символов
    s = str(val).lower()
    s = s.replace("rp", "").replace("руб", "").replace("idr", "")
    
    # Обработка суффикса "k" или "к" (тысячи)
    mult = 1
    if s.endswith("k") or s.endswith("к"):
        mult = 1000
        s = s[:-1]
    
    # Сохраняем только цифры, точки, запятые и пробелы (пробелы могут быть разделителями тысяч)
    s = ''.join(c for c in s if c.isdigit() or c in '., ')
    
    # Удаляем все пробелы
    s = s.replace(" ", "")
    
    # Если в строке есть и запятая, и точка - это сложное число с разделителями
    if ',' in s and '.' in s:
        # Определяем последний разделитель (обычно десятичный)
        last_comma_pos = s.rfind(',')
        last_dot_pos = s.rfind('.')
        
        if last_dot_pos > last_comma_pos:
            # Американский формат: 1,234.56
            s = s.replace(',', '')
        else:
            # Европейский формат: 1.234,56
            s = s.replace('.', '')
            s = s.replace(',', '.')
    elif ',' in s:
        # Проверяем, является ли запятая разделителем тысяч или десятичным
        if len(s.split(',')[-1]) == 3 and s.count(',') > 0:
            # Вероятно, это разделитель тысяч: 1,234
            s = s.replace(',', '')
        else:
            # Вероятно, это десятичный разделитель: 1,23
            s = s.replace(',', '.')
    elif '.' in s:
        # Проверяем, является ли точка разделителем тысяч
        if len(s.split('.')[-1]) == 3 and s.count('.') > 0:
            # Вероятно, это разделитель тысяч: 1.234
            s = s.replace('.', '')
            
    # На этом этапе в строке должны остаться только цифры и возможно одна точка как десятичный разделитель
    try:
        return float(s) * mult
    except (ValueError, TypeError):
        # Если что-то пошло не так, пробуем более агрессивную фильтрацию
        s = re.sub(r'[^0-9.]', '', s)
        if s:
            try:
                return float(s) * mult
            except (ValueError, TypeError):
                return None
        return None

# Автозамена названий по словарю (расстояние Левенштейна <= 2)
def autocorrect_name(name: str, allowed_names: List[str]) -> str:
    from rapidfuzz.distance import Levenshtein
    name = name.strip()
    best = name
    min_dist = 3
    
    # Отладочное логирование
    logging.debug(f"autocorrect_name: проверяем '{name}' среди {len(allowed_names)} допустимых названий")
    
    for ref in allowed_names:
        dist = Levenshtein.distance(name.lower(), ref.lower())
        if dist < min_dist:
            min_dist = dist
            best = ref
            logging.debug(f"Найдено лучшее совпадение: '{ref}' с расстоянием {dist}")
    
    result = best if min_dist <= 2 else name
    logging.debug(f"autocorrect_name: '{name}' -> '{result}' (расстояние={min_dist})")
    return result

# Словарь для нормализации единиц измерения
UNIT_MAPPING = {
    # Весовые единицы
    "kilogram": "kg",
    "kilograms": "kg",
    "kg": "kg",
    "kgs": "kg",
    "kilogramme": "kg",
    "kilogrammes": "kg",
    "kilo": "kg",
    "kilos": "kg",
    
    "gram": "g",
    "grams": "g",
    "g": "g",
    "gr": "g",
    "gm": "g",
    "gramme": "g",
    "grammes": "g",
    
    # Объемные единицы
    "liter": "l",
    "liters": "l",
    "litre": "l",
    "litres": "l",
    "l": "l",
    "lt": "l",
    
    "milliliter": "ml",
    "milliliters": "ml",
    "millilitre": "ml",
    "millilitres": "ml",
    "ml": "ml",
    
    # Штучные единицы
    "piece": "pcs",
    "pieces": "pcs",
    "pcs": "pcs",
    "pc": "pcs",
    "pce": "pcs",
    "ea": "pcs",
    "each": "pcs",
    
    # Упаковки
    "pack": "pack",
    "package": "pack",
    "packet": "pack",
    "pkg": "pack",
    
    # Бутылки
    "bottle": "btl",
    "bottles": "btl",
    "btl": "btl",
    "bt": "btl",
    
    # Коробки
    "box": "box",
    "boxes": "box",
    "bx": "box",
    
    # Банки
    "can": "can",
    "cans": "can",
    
    # Контейнеры
    "container": "cont",
    "cont": "cont",
    
    # Ящики
    "crate": "krat",
    "krat": "krat",
    "kratjes": "krat"
}

# Типичные единицы измерения для категорий продуктов
PRODUCT_DEFAULT_UNITS = {
    "vegetable": "kg",
    "fruit": "kg",
    "meat": "kg",
    "seafood": "kg",
    "dairy": "pcs",
    "beverage": "pcs",
    "spice": "g",
    "grain": "kg",
    "oil": "btl",
    "sauce": "btl",
    "packaged": "pcs"
}

# Словарь категорий для товаров
PRODUCT_CATEGORIES = {
    "vegetable": ["tomato", "potato", "carrot", "onion", "cucumber", "zucchini", "eggplant", "spinach", "broccoli", "paprika", "lettuce", "romaine", "kale", "cabbage", "mushroom", "radish"],
    "fruit": ["apple", "orange", "banana", "grape", "strawberry", "mango", "pineapple", "lemon", "lime", "sunkist", "watermelon", "dragon fruit"],
    "meat": ["beef", "chicken", "pork", "lamb", "sausage", "bacon", "ham", "tenderloin", "breast"],
    "seafood": ["fish", "salmon", "tuna", "shrimp", "prawn", "crab", "lobster", "mussel", "oyster"],
    "dairy": ["milk", "cheese", "yogurt", "butter", "cream", "mascarpone", "ricotta", "mozzarela", "emmental", "cheddar"],
    "beverage": ["water", "juice", "soda", "tea", "coffee", "cola", "beer", "wine"],
    "spice": ["salt", "pepper", "cumin", "paprika", "oregano", "basil", "thyme", "garlic", "ginger"],
    "grain": ["rice", "pasta", "noodle", "flour", "oat", "quinoa", "buckwheat"],
    "oil": ["olive", "sunflower", "vegetable", "sesame"],
    "sauce": ["ketchup", "mayonnaise", "mustard", "soy", "vinegar"],
    "packaged": ["can", "jar", "packet", "box", "paper"]
}

def normalize_units(unit: str, product_name: str = None) -> str:
    """
    Нормализует единицы измерения на основе словаря маппинга
    и категории продукта.
    
    Args:
        unit: Исходная единица измерения
        product_name: Название продукта (для определения категории)
        
    Returns:
        Нормализованная единица измерения
    """
    if not unit:
        # Если единица не указана, попробуем определить по имени продукта
        if product_name:
            product_name_lower = product_name.lower()
            
            # Определяем категорию продукта
            product_category = None
            for category, products in PRODUCT_CATEGORIES.items():
                for product in products:
                    if product in product_name_lower:
                        product_category = category
                        break
                if product_category:
                    break
            
            # Если категория определена, возвращаем типичную единицу
            if product_category and product_category in PRODUCT_DEFAULT_UNITS:
                return PRODUCT_DEFAULT_UNITS[product_category]
        
        return "pcs"  # Значение по умолчанию, если не удалось определить
    
    # Нормализуем переданную единицу
    unit_lower = unit.lower().strip()
    
    # Проверяем в словаре маппинга
    if unit_lower in UNIT_MAPPING:
        return UNIT_MAPPING[unit_lower]
    
    # Если единица не найдена, возвращаем оригинал или pcs
    return unit if unit else "pcs"

# Основная функция постобработки ParsedData
def postprocess_parsed_data(parsed: ParsedData, req_id: str = "unknown") -> ParsedData:
    products = load_products()
    allowed_names = [p.alias for p in products]
    
    # Отладочное логирование
    logging.info(f"postprocess_parsed_data: загружено {len(products)} продуктов")
    logging.info(f"Первые 5 продуктов: {allowed_names[:5]}")
    
    for pos in parsed.positions:
        pos.price = clean_num(pos.price)
        pos.qty = clean_num(pos.qty)
        pos.total_price = clean_num(pos.total_price)
        if pos.name:
            logging.info(f"Автокоррекция названия: '{pos.name}'")
            corrected = autocorrect_name(pos.name, allowed_names)
            pos.name = corrected
            logging.info(f"Результат автокоррекции: '{pos.name}'")
            # Логируем слишком длинные названия
            if pos.name and len(pos.name) > 30:
                log_format_issues(req_id, "position.name", pos.name, "< 30 chars")
        
        # Normalize unit
        if hasattr(pos, 'unit'):
            pos.unit = normalize_units(pos.unit, pos.name)
        
        # Ensure total price is correct
        if pos.qty and pos.price and (not pos.total_price or pos.total_price == 0):
            pos.total_price = pos.qty * pos.price
        
        # If total price exists but price doesn't, calculate price
        if pos.qty and pos.qty > 0 and pos.total_price and (not pos.price or pos.price == 0):
            pos.price = pos.total_price / pos.qty
    
    parsed.total_price = clean_num(parsed.total_price)
    # Логируем итоговые данные
    log_indonesian_invoice(req_id, parsed.dict(), phase="postprocessing")
    return parsed 