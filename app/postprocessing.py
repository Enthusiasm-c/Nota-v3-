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
    
    parsed.total_price = clean_num(parsed.total_price)
    # Логируем итоговые данные
    log_indonesian_invoice(req_id, parsed.dict(), phase="postprocessing")
    return parsed 