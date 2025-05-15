import re
from typing import List, Dict, Tuple

def format_price(price_str: str) -> str:
    """
    Форматирует строку цены, удаляя пробелы и 'IDR',
    конвертирует в формат с 'k' для тысяч.
    """
    # Удаляем все нечисловые символы, кроме цифр
    price = ''.join(c for c in price_str if c.isdigit())
    
    try:
        # Преобразуем в число
        price_num = int(price)
        
        # Форматируем с 'k' для тысяч
        if price_num >= 1000:
            return f"{price_num // 1000}k"
        return str(price_num)
    except ValueError:
        return price

def parse_table_line(line: str) -> Tuple[str, str, str, str]:
    """
    Разбирает строку таблицы на компоненты.
    
    Returns:
        Кортеж (name, qty, unit, price)
    """
    # Удаляем начальный номер и лишние пробелы
    parts = line.strip().split()
    if not parts:
        return "", "", "", ""
        
    # Первый элемент - это номер, пропускаем его
    if parts[0].isdigit():
        parts = parts[1:]
    
    # Собираем название до тех пор, пока не встретим число (qty)
    name_parts = []
    i = 0
    while i < len(parts):
        if parts[i].replace('.', '').isdigit():
            break
        name_parts.append(parts[i])
        i += 1
    
    name = ' '.join(name_parts)
    
    # Оставшиеся части - это qty, unit и price
    remaining = parts[i:]
    if len(remaining) >= 3:
        qty = remaining[0]
        unit = remaining[1]
        # Объединяем все оставшиеся части как цену
        price = ' '.join(remaining[2:])
    else:
        qty = remaining[0] if remaining else ""
        unit = remaining[1] if len(remaining) > 1 else ""
        price = remaining[2] if len(remaining) > 2 else ""
    
    return name.strip(), qty.strip(), unit.strip(), format_price(price)

def text_to_markdown_table(text: str) -> str:
    """
    Преобразует текстовый блок в Markdown таблицу.
    """
    # Заголовок таблицы со смещением на один знак влево
    header = "|# |Name|QTY|Unit|Price|\n"
    separator = "|--|----|----|----|----|--|\n"
    
    lines = text.split('\n')
    rows = []
    current_row = 1
    
    for line in lines:
        # Пропускаем заголовок и пустые строки
        if not line.strip() or line.strip().upper().startswith('NAME') or line.strip() == 'IDR':
            continue
            
        name, qty, unit, price = parse_table_line(line)
        if name and qty:  # Проверяем, что строка содержит данные
            # Обработка длинных названий с переносом строки
            if len(name) > 10:
                name_parts = []
                current_part = ""
                for word in name.split():
                    if len(current_part) + len(word) + 1 <= 10:
                        if current_part:
                            current_part += " " + word
                        else:
                            current_part = word
                    else:
                        name_parts.append(current_part)
                        current_part = word
                if current_part:
                    name_parts.append(current_part)
                name = "<br>".join(name_parts)
            
            # Форматируем строку таблицы без восклицательных знаков
            row = f"|{current_row}|{name}|{qty}|{unit}|{price}|\n"
            rows.append(row)
            current_row += 1
    
    return header + separator + ''.join(rows) 