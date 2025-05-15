#!/usr/bin/env python3
"""
Финальное тестирование исправленных регулярных выражений для команд редактирования
"""

import re

def test_regex(command, text):
    """Тестирует все регулярные выражения на заданной команде"""
    text_l = text.lower().strip()
    results = {}
    
    # Проверка для команды изменения единицы измерения с qty
    line_unit_match_qty = re.search(r"\b(?:строка|line)\s+(\d+)\s+qty\s+([a-zA-Zа-яА-Я]+)", text_l)
    if line_unit_match_qty:
        line_num = int(line_unit_match_qty.group(1)) - 1
        unit = line_unit_match_qty.group(2).strip()
        results["unit_qty"] = {"action": "edit_unit", "index": line_num, "value": unit}
    
    # Проверка для команды изменения количества
    line_qty_match = re.search(r"\b(?:строка|line)\s+(\d+)\s+(?:количество|quantity|qty)\s+(\d+[.,]?\d*)", text_l)
    if line_qty_match:
        line_num = int(line_qty_match.group(1)) - 1
        qty = line_qty_match.group(2).replace(',', '.')
        results["quantity"] = {"action": "edit_quantity", "index": line_num, "value": qty}
    
    # Проверка для стандартной команды изменения единицы измерения
    line_unit_match = re.search(r"\b(?:строка|line)\s+(\d+)\s+(?:единица|единицы|unit|ед|ед\.)\s+(\w+)", text_l)
    if line_unit_match:
        line_num = int(line_unit_match.group(1)) - 1
        unit = line_unit_match.group(2).strip()
        results["unit"] = {"action": "edit_unit", "index": line_num, "value": unit}
    
    print(f"\n=== Тестирование команды: '{command}' ===")
    print(f"Результаты распознавания:")
    
    if "unit_qty" in results:
        print(f"✅ Распознано как изменение единицы измерения (с qty): {results['unit_qty']}")
    else:
        print("❌ Не распознано как изменение единицы измерения (с qty)")
    
    if "quantity" in results:
        print(f"{'✅' if command.endswith('10.5') else '❌'} Распознано как изменение количества: {results['quantity']}")
    else:
        print("❌ Не распознано как изменение количества")
    
    if "unit" in results:
        print(f"{'✅' if 'единица' in command or 'unit' in command else '❌'} Распознано как изменение единицы измерения (стандартный шаблон): {results['unit']}")
    else:
        print("❌ Не распознано как изменение единицы измерения (стандартный шаблон)")
    
    # Определение итогового интента
    if "unit_qty" in results:
        print("\n✅ Итоговый интент: изменение единицы измерения")
        return results["unit_qty"]
    elif "unit" in results:
        print("\n✅ Итоговый интент: изменение единицы измерения")
        return results["unit"]
    elif "quantity" in results:
        print("\n✅ Итоговый интент: изменение количества")
        return results["quantity"]
    else:
        print("\n❌ Интент не распознан")
        return {"action": "unknown"}

def main():
    """Основная функция тестирования"""
    print("=== ФИНАЛЬНОЕ ТЕСТИРОВАНИЕ УЛУЧШЕННОГО ПАРСЕРА КОМАНД ===\n")
    
    # Тестовые команды
    commands = [
        "Line 3 qty gram",           # Должно распознать как unit
        "line 2 qty 10.5",           # Должно распознать как quantity
        "строка 1 единица шт",       # Должно распознать как unit
        "строка 4 количество 5"      # Должно распознать как quantity
    ]
    
    for cmd in commands:
        intent = test_regex("Команда", cmd)
    
    print("\n=== ТЕСТИРОВАНИЕ ЗАВЕРШЕНО ===")

if __name__ == "__main__":
    main() 