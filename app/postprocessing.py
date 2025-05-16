import re
import logging
from typing import Optional, List
from app.models import ParsedData, Position
from app.data_loader import load_products
from app.utils.enhanced_logger import log_indonesian_invoice, log_format_issues
from app.validators.price_validator import validate_invoice_prices

# Автокоррекция числовых значений с надежной обработкой различных форматов
def clean_num(val, default=None) -> Optional[float]:
    """
    Очистка и конвертация числовых значений из разных форматов.
    Работает с форматами: 1,000.00, 1.000,00, 1 000, 1'000, и т.д.
    Также распознает валютные символы и суффиксы (k, м, млн).
    
    Args:
        val: Входное значение (число, строка, None)
        default: Значение по умолчанию, если не удалось распознать
        
    Returns:
        float: Распознанное число или default при ошибке
    """
    # Проверка на None и пустые значения
    if val in (None, "", "null", "—", "-", "n/a", "NA", "N/A"):
        return default
    
    # Конвертация в строку, если это не строка
    if isinstance(val, (int, float)):
        return float(val)
    
    # Конвертация в строку и нижний регистр
    s = str(val).lower().strip()
    
    # Предварительная очистка от распространённых валютных символов и текста
    currency_patterns = [
        r'(?i)(?:rp|rupiah|idr|руб|рубл[яей]|usd|\$|€|евро|р\.|руб\.|₽)',
        r'(?i)total:?',
        r'(?i)price:?'
    ]
    for pattern in currency_patterns:
        s = re.sub(pattern, '', s)
    
    # Обработка суффиксов кратности
    mult = 1
    # Тысячи: k, к, тыс
    if re.search(r'(?i)[kк]$|тыс\.?$', s):
        mult = 1000
        s = re.sub(r'(?i)[kк]$|тыс\.?$', '', s)
    # Миллионы: m, м, млн
    elif re.search(r'(?i)[mм]$|млн\.?$', s):
        mult = 1000000
        s = re.sub(r'(?i)[mм]$|млн\.?$', '', s)
    
    # Очистка от всех нецифровых символов, кроме разделителей
    # Допустимые разделители: точка, запятая, пробел, апостроф
    s = ''.join(c for c in s if c.isdigit() or c in '., \'')
    
    # Удаляем разделители тысяч (пробелы, апострофы)
    s = s.replace(" ", "").replace("'", "")
    
    # Более сложная логика определения десятичного разделителя
    # Если в строке есть и запятая, и точка
    if ',' in s and '.' in s:
        # Проверяем позиции десятичных разделителей
        last_comma_pos = s.rfind(',')
        last_dot_pos = s.rfind('.')
        
        if last_dot_pos > last_comma_pos:
            # Американский/английский формат: 1,234.56
            s = s.replace(',', '')
        else:
            # Европейский формат: 1.234,56
            s = s.replace('.', '')
            s = s.replace(',', '.')
    elif ',' in s:
        # Только запятые - определяем их роль
        comma_parts = s.split(',')
        
        # Если после запятой 1-2 цифры, это вероятно десятичный разделитель
        # Или если запятая ближе к концу строки
        if len(comma_parts[-1]) <= 2 or len(comma_parts[-1]) < len(s) * 0.3:
            s = s.replace(',', '.')
        else:
            # Вероятно, это разделитель тысяч
            s = s.replace(',', '')
    
    # На этом этапе в строке должны остаться только цифры и возможно одна точка
    try:
        # Если осталась точка в начале или конце, удаляем ее
        s = s.strip('.')
        return float(s) * mult if s else default
    except (ValueError, TypeError):
        # Если что-то пошло не так, делаем последнюю попытку
        try:
            # Оставляем только цифры и точку, точку оставляем только одну и не в начале
            digits_only = re.sub(r'[^0-9]', '', s)
            if not digits_only:
                return default
            return float(digits_only) * mult
        except (ValueError, TypeError):
            return default

# Автозамена названий по словарю (расстояние Левенштейна <= 2)
def autocorrect_name(name: str, allowed_names: List[str]) -> str:
    """
    Автокоррекция названий товаров на основе списка разрешенных названий.
    
    Args:
        name: Исходное название
        allowed_names: Список разрешенных названий
        
    Returns:
        Исправленное или исходное название
    """
    from rapidfuzz.distance import Levenshtein
    
    # Проверка на None
    if name is None:
        return name
        
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
    """
    Улучшенная постобработка данных из OCR с дополнительными проверками и коррекциями.
    
    Args:
        parsed: Исходные данные из OCR
        req_id: Идентификатор запроса для логирования
        
    Returns:
        ParsedData: Обработанные и улучшенные данные
    """
    try:
        # Загружаем продукты для автокоррекции
        products = load_products()
        allowed_names = [p.alias for p in products]
        
        # Отладочное логирование
        logging.info(f"postprocess_parsed_data: загружено {len(products)} продуктов")
        if allowed_names:
            logging.info(f"Первые 5 продуктов: {allowed_names[:5]}")
        
        # Обработка даты инвойса (если есть)
        if parsed.date and isinstance(parsed.date, str):
            try:
                # Если дата в формате DD.MM.YYYY или DD/MM/YYYY, конвертируем в ISO
                date_match = re.match(r'(\d{1,2})[./-](\d{1,2})[./-](\d{4})', parsed.date)
                if date_match:
                    day, month, year = map(int, date_match.groups())
                    from datetime import date
                    parsed.date = date(year, month, day)
                    logging.info(f"Дата конвертирована в ISO формат: {parsed.date.isoformat()}")
            except Exception as date_err:
                logging.warning(f"Ошибка при конвертации даты: {date_err}")
        
        # Обработка общей суммы
        parsed.total_price = clean_num(parsed.total_price)
        
        # Обработка позиций
        pos_count = len(parsed.positions)
        logging.info(f"Обработка {pos_count} позиций")
        
        # Удаляем позиции без имени или количества
        valid_positions = []
        for i, pos in enumerate(parsed.positions):
            # Пропускаем явно пустые позиции
            if not pos.name or pos.name.strip() in ["", "-", "Итого", "Total", "Sum"]:
                logging.info(f"Пропускаем пустую позицию #{i+1}")
                continue
                
            # Очистка числовых значений
            pos.price = clean_num(pos.price)
            pos.qty = clean_num(pos.qty, 1.0)  # Если количество не указано, предполагаем 1
            pos.total_price = clean_num(pos.total_price)
            
            # Автокоррекция имени
            if pos.name:
                logging.info(f"Автокоррекция названия: '{pos.name}'")
                corrected = autocorrect_name(pos.name, allowed_names)
                pos.name = corrected
                logging.info(f"Результат автокоррекции: '{pos.name}'")
                # Логируем слишком длинные названия
                if pos.name and len(pos.name) > 30:
                    log_format_issues(req_id, "position.name", pos.name, "< 30 chars")
            
            # Нормализация единиц измерения
            if hasattr(pos, 'unit'):
                old_unit = pos.unit
                pos.unit = normalize_units(pos.unit, pos.name)
                if old_unit != pos.unit:
                    logging.info(f"Нормализация единицы: '{old_unit}' -> '{pos.unit}'")
            
            # Обеспечение целостности данных
            
            # 1. Если есть цена и количество, но нет итоговой суммы
            if pos.qty and pos.price and (not pos.total_price or pos.total_price == 0):
                pos.total_price = pos.qty * pos.price
                logging.info(f"Вычислена total_price: {pos.qty} * {pos.price} = {pos.total_price}")
            
            # 2. Если есть итоговая сумма и количество, но нет цены
            elif pos.qty and pos.qty > 0 and pos.total_price and (not pos.price or pos.price == 0):
                pos.price = pos.total_price / pos.qty
                logging.info(f"Вычислена price: {pos.total_price} / {pos.qty} = {pos.price}")
            
            # 3. Проверка на аномальные значения
            # Если цена или количество аномально высокие - это может быть ошибка в распознавании
            if pos.price and pos.price > 10_000_000:  # Аномально высокая цена
                pos.price = pos.price / 10  # Корректируем ошибку в десятичном разделителе
                logging.warning(f"Корректировка аномальной цены: {pos.price*10} -> {pos.price}")
            
            if pos.qty and pos.qty > 1000:  # Аномально большое количество
                pos.qty = pos.qty / 10  # Корректируем ошибку в десятичном разделителе
                logging.warning(f"Корректировка аномального количества: {pos.qty*10} -> {pos.qty}")
            
            # Добавляем позицию в валидный список
            valid_positions.append(pos)
        
        # Заменяем список позиций на отфильтрованный
        parsed.positions = valid_positions
        logging.info(f"После фильтрации осталось {len(valid_positions)} позиций")
        
        # Если общая сумма не указана, но есть позиции с ценами - вычисляем её
        if not parsed.total_price or parsed.total_price == 0:
            positions_with_total = [p for p in parsed.positions if p.total_price]
            if positions_with_total:
                total_sum = sum(p.total_price for p in positions_with_total)
                parsed.total_price = total_sum
                logging.info(f"Вычислена общая сумма: {parsed.total_price}")
        
        # Валидация цен
        parsed = validate_invoice_prices(parsed)
        if parsed.has_price_mismatches:
            logging.warning(
                f"[{req_id}] Обнаружены несоответствия в ценах: {parsed.price_mismatch_count} позиций"
            )
        
        # Логируем итоговые данные
        log_indonesian_invoice(req_id, parsed.model_dump(), phase="postprocessing")
        
        return parsed
    except Exception as e:
        # В случае любой ошибки логируем и возвращаем исходные данные
        logging.error(f"Ошибка при постобработке данных: {e}")
        return parsed