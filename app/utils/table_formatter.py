from typing import Tuple

def format_price(price_str: str) -> str:
    """
    Форматирует строку цены, удаляя пробелы и 'IDR'.
    """
    # Удаляем все нечисловые символы, кроме цифр
    price = ''.join(c for c in price_str if c.isdigit())
    # Форматируем цену с пробелами между тысячами
    if len(price) > 3:
        # Разделяем число на группы по 3 цифры справа налево и соединяем пробелами
        groups = []
        for i in range(len(price), 0, -3):
            start = max(0, i - 3)
            groups.insert(0, price[start:i])
        price = ' '.join(groups)
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
    # Заголовок таблицы со смещенными названиями столбцов
    # Name влево на 2 знака, QTY влево на 2 знака (было 3), Unit влево на 4 знака, Price влево на 5 знаков
    header = "| # |Name| QTY|Unit|Price (IDR) |\n"
    separator = "|---|---|----|---|-----------|\n"
    
    lines = text.split('\n')
    rows = []
    current_row = 1
    
    for line in lines:
        # Пропускаем заголовок и пустые строки
        if not line.strip() or line.strip().upper().startswith('NAME') or line.strip() == 'IDR':
            continue
            
        name, qty, unit, price = parse_table_line(line)
        if name and qty:  # Проверяем, что строка содержит данные
            # Форматируем строку таблицы, добавляем пробел после номера
            row = f"| {current_row} |{name}| {qty}|{unit}| {price} |\n"
            rows.append(row)
            current_row += 1
    
    return header + separator + ''.join(rows) 