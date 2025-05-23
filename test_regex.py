#!/usr/bin/env python3
"""
Тестирование регулярного выражения для команды редактирования единицы измерения
"""

import re

def test_regex(pattern, test_strings):
    """Тестирует регулярное выражение на наборе строк"""
    for text in test_strings:
        print(f"\nТестируем: '{text}'")
        text_l = text.lower().strip()
        match = re.search(pattern, text_l)
        
        if match:
            print(f"✅ Найдено совпадение: {match.groups()}")
            line_num = int(match.group(1)) - 1
            unit = match.group(2).strip()
            print(f"   Индекс: {line_num}, Единица: '{unit}'")
        else:
            print("❌ Совпадение не найдено")

if __name__ == "__main__":
    # Шаблон для распознавания команд редактирования единицы измерения
    pattern = r"\b(?:строка|line)\s+(\d+)\s+(?:единица|unit|ед|ед\.|unit|qty)\s+(\w+)"
    
    # Тестовые строки
    test_strings = [
        "Line 3 qty gram",
        "строка 1 единица кг",
        "строка 2 ед шт",
        "line 4 unit pcs",
        "line 10 qty piece",
        "line 3 quantity 5",  # Не должно совпадать (число вместо единицы)
        "line 3 price 100",   # Не должно совпадать (другая команда)
        "change line 3 to gram"  # Не должно совпадать (другой формат)
    ]
    
    print(f"Тестирование регулярного выражения: {pattern}\n")
    test_regex(pattern, test_strings)
    
    # Проверяем, не конфликтует ли с другими шаблонами
    print("\n\nПроверка конфликтов с другими шаблонами:")
    
    # Шаблон для редактирования количества
    qty_pattern = r"\b(?:строка|line)\s+(\d+)\s+(?:количество|quantity|qty)\s+(\d+[.,]?\d*)"
    print(f"\nШаблон для количества: {qty_pattern}")
    test_regex(qty_pattern, ["строка 1 количество 5", "line 2 qty 10.5", "line 3 qty gram"])
    
    # Проверяем исправленную версию шаблона для редактирования единицы
    print("\n\nПроверка исправленной версии шаблона для единицы измерения:")
    fixed_pattern = r"\b(?:строка|line)\s+(\d+)\s+(?:единица|unit|ед|ед\.|unit)\s+(\w+)"
    test_regex(fixed_pattern, ["line 3 qty gram", "строка 3 единица шт"]) 