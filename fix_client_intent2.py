#!/usr/bin/env python3
# Скрипт для исправления значений в блоках функции attempt_fast_intent_recognition

import re

# Путь к файлу client.py
client_file = 'app/assistants/client.py'

# Читаем весь файл
with open(client_file, 'r') as f:
    content = f.read()

# Исправление в блоке цены
content = re.sub(
    r'                "action": "\\1",\n'
    r'                "line_index": line_num - 1,  # Конвертируем в 0-based индекс\n'
    r'                "value": \\2',
    r'                "action": "set_price",\n'
    r'                "line_index": line_num - 1,  # Конвертируем в 0-based индекс\n'
    r'                "value": price',
    content
)

# Исправление в блоке количества
content = re.sub(
    r'price_match.*?return \{.*?"action": "\\1",.*?"value": \\2',
    r'price_match = re.search(r\'(строк[аи]?|line|row)\\s+(\\d+).*?(цен[аыу]|price)\\s+(\\d+)\', text)\n'
    r'    if price_match:\n'
    r'        try:\n'
    r'            line_num = int(price_match.group(2))\n'
    r'            price = price_match.group(4).strip()\n'
    r'            return {\n'
    r'                "action": "set_price",\n'
    r'                "line_index": line_num - 1,  # Конвертируем в 0-based индекс\n'
    r'                "value": price',
    content, 
    flags=re.DOTALL
)

# Исправление в блоке количества
content = re.sub(
    r'qty_match.*?return \{.*?"action": "\\1",.*?"value": \\2',
    r'qty_match = re.search(r\'(строк[аи]?|line|row)\\s+(\\d+).*?(кол-во|количество|qty|quantity)\\s+(\\d+)\', text)\n'
    r'    if qty_match:\n'
    r'        try:\n'
    r'            line_num = int(qty_match.group(2))\n'
    r'            qty = qty_match.group(4).strip()\n'
    r'            return {\n'
    r'                "action": "set_quantity",\n'
    r'                "line_index": line_num - 1,  # Конвертируем в 0-based индекс\n'
    r'                "value": qty',
    content, 
    flags=re.DOTALL
)

# Исправление в блоке единицы измерения
content = re.sub(
    r'unit_match.*?return \{.*?"action": "\\1",.*?"value": \\2',
    r'unit_match = re.search(r\'(строк[аи]?|line|row)\\s+(\\d+).*?(ед[\.\\s]изм[\.ерение]*|unit)\\s+(\\w+)\', text)\n'
    r'    if unit_match:\n'
    r'        try:\n'
    r'            line_num = int(unit_match.group(2))\n'
    r'            unit = unit_match.group(4).strip()\n'
    r'            return {\n'
    r'                "action": "set_unit",\n'
    r'                "line_index": line_num - 1,  # Конвертируем в 0-based индекс\n'
    r'                "value": unit',
    content, 
    flags=re.DOTALL
)

# Записываем исправленное содержимое в файл
with open(client_file, 'w') as f:
    f.write(content)

print(f"Исправлены значения в функции attempt_fast_intent_recognition в файле {client_file}") 