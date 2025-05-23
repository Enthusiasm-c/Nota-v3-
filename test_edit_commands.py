#!/usr/bin/env python3
"""
Тестовый скрипт для проверки работы парсера команд редактирования в incremental_edit_flow.py
"""

import logging
import re
from pprint import pprint
from app.edit.apply_intent import apply_intent

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Имитация локального парсера из incremental_edit_flow.py
def local_intent_parser(text: str):
    text_l = text.lower().strip()
    
    # Парсинг команды изменения даты
    date_match = re.search(r"\b(?:дата|date)\s+(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})", text_l)
    if date_match:
        return {"action": "edit_date", "value": date_match.group(1)}
            
    # Парсинг команды редактирования строки с ценой
    line_price_match = re.search(r"\b(?:строка|line)\s+(\d+)\s+(?:цена|price)\s+(\d+[.,]?\d*)", text_l)
    if line_price_match:
        line_num = int(line_price_match.group(1)) - 1  # Конвертируем 1-based в 0-based индекс
        price = line_price_match.group(2).replace(',', '.')
        return {"action": "edit_price", "index": line_num, "value": price}
            
    # Парсинг команды редактирования строки с количеством
    line_qty_match = re.search(r"\b(?:строка|line)\s+(\d+)\s+(?:количество|quantity|qty)\s+(\d+[.,]?\d*)", text_l)
    if line_qty_match:
        line_num = int(line_qty_match.group(1)) - 1  # Конвертируем 1-based в 0-based индекс
        qty = line_qty_match.group(2).replace(',', '.')
        return {"action": "edit_quantity", "index": line_num, "value": qty}
    
    # Парсинг команды редактирования единицы измерения
    line_unit_match = re.search(r"\b(?:строка|line)\s+(\d+)\s+(?:единица|unit|ед|ед\.|unit|qty)\s+(\w+)", text_l)
    if line_unit_match:
        line_num = int(line_unit_match.group(1)) - 1  # Конвертируем 1-based в 0-based индекс
        unit = line_unit_match.group(2).strip()
        return {"action": "edit_unit", "index": line_num, "value": unit}
            
    # Парсинг команды редактирования строки с названием
    line_name_match = re.search(r"\b(?:строка|line)\s+(\d+)\s+(?:название|name)?\s+(.+)$", text_l)
    if line_name_match:
        line_num = int(line_name_match.group(1)) - 1  # Конвертируем 1-based в 0-based индекс
        name = line_name_match.group(2).strip()
        # Проверяем, что название не содержит других ключевых слов команд
        if not any(word in name.lower() for word in ['цена', 'price', 'количество', 'quantity', 'qty', 'единица', 'unit', 'ед', 'ед.']):
            return {"action": "edit_name", "line": line_num, "value": name}
    
    return {"action": "unknown", "user_message": "I couldn't understand your command. Please try again with a simpler format."}

# Тестовый инвойс
test_invoice = {
    "date": "01.01.2023",
    "positions": [
        {"name": "Apple", "qty": 1, "unit": "pc", "price": 100},
        {"name": "Banana", "qty": 2, "unit": "kg", "price": 50},
        {"name": "Coffee", "qty": 0.5, "unit": "pc", "price": 200}
    ]
}

def test_command(command, invoice):
    """Тестирует одну команду редактирования"""
    print(f"\n\033[1m>>> Тестируем команду: '{command}'\033[0m")
    intent = local_intent_parser(command)
    print(f"Распознанный интент: {intent}")
    
    if intent["action"] != "unknown":
        result = apply_intent(invoice, intent)
        print("Результат применения интента:")
        pprint(result)
        return result
    else:
        print(f"Команда не распознана: {intent.get('user_message', 'Неизвестная ошибка')}")
        return invoice

def main():
    """Основная функция тестирования"""
    print("\033[1;32m=== Тестирование команд редактирования инвойса ===\033[0m")
    
    # Исходные данные
    invoice = test_invoice.copy()
    print("\nИсходный инвойс:")
    pprint(invoice)
    
    # Тестируем команду изменения даты
    invoice = test_command("дата 15.05.2023", invoice)
    
    # Тестируем команду изменения цены
    invoice = test_command("строка 1 цена 120", invoice)
    
    # Тестируем команду изменения количества
    invoice = test_command("строка 2 количество 3", invoice)
    
    # Тестируем команду изменения единицы измерения - русский вариант
    invoice = test_command("строка 3 единица кг", invoice)
    
    # Тестируем команду изменения единицы измерения - английский вариант
    invoice = test_command("Line 3 qty gram", invoice)
    
    # Тестируем команду изменения названия
    invoice = test_command("строка 1 название Golden Apple", invoice)
    
    print("\n\033[1;32m=== Итоговый инвойс после всех изменений ===\033[0m")
    pprint(invoice)

if __name__ == "__main__":
    main() 