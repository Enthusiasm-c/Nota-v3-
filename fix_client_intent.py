#!/usr/bin/env python3
# Скрипт для исправления отступов в функции attempt_fast_intent_recognition

import re

# Путь к файлу client.py
client_file = 'app/assistants/client.py'

# Читаем весь файл
with open(client_file, 'r') as f:
    content = f.read()

# Исправление отступов в блоке цены
content = re.sub(
    r'            price = price_match\.group\(4\)\.strip\(\)\n'
    r'                        return \{',
    r'            price = price_match.group(4).strip()\n'
    r'            return {',
    content
)

# Исправление отступов в блоке количества
content = re.sub(
    r'            qty = qty_match\.group\(4\)\.strip\(\)\n'
    r'                return \{',
    r'            qty = qty_match.group(4).strip()\n'
    r'            return {',
    content
)

# Исправление отступов в блоке единицы измерения
content = re.sub(
    r'            unit = unit_match\.group\(4\)\.strip\(\)\n'
    r'                        return \{',
    r'            unit = unit_match.group(4).strip()\n'
    r'            return {',
    content
)

# Исправление отступов в значениях line_index и value
content = re.sub(
    r'                "action": "(set_price|set_quantity|set_unit)",\n'
    r'                "line_index": line_num - 1,  # Конвертируем в 0-based индекс\n'
    r'                "value": (price|qty|unit)',
    r'                "action": "\\1",\n'
    r'                "line_index": line_num - 1,  # Конвертируем в 0-based индекс\n'
    r'                "value": \\2',
    content
)

# Записываем исправленное содержимое в файл
with open(client_file, 'w') as f:
    f.write(content)

print(f"Исправлены отступы в функции attempt_fast_intent_recognition в файле {client_file}") 