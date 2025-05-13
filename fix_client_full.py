#!/usr/bin/env python3
# Скрипт для полной замены функции attempt_fast_intent_recognition

import re

# Путь к файлу client.py
client_file = 'app/assistants/client.py'

# Читаем весь файл
with open(client_file, 'r') as f:
    content = f.read()

# Новая функция с правильными отступами
new_function = """
def attempt_fast_intent_recognition(user_input: str) -> Optional[Dict[str, Any]]:
    \"\"\"
    Быстрое распознавание часто встречающихся команд без обращения к OpenAI
    
    Args:
        user_input: Текстовая команда пользователя
        
    Returns:
        Dict или None: Распознанное намерение или None, если не удалось распознать
    \"\"\"
    text = user_input.lower()
    
    # Распознавание команды редактирования строки (цена)
    price_match = re.search(r'(строк[аи]?|line|row)\\s+(\\d+).*?(цен[аыу]|price)\\s+(\\d+)', text)
    if price_match:
        try:
            line_num = int(price_match.group(2))
            price = price_match.group(4).strip()
            return {
                "action": "set_price",
                "line_index": line_num - 1,  # Конвертируем в 0-based индекс
                "value": price
            }
        except Exception:
            pass
    
    # Распознавание команды редактирования строки (количество)
    qty_match = re.search(r'(строк[аи]?|line|row)\\s+(\\d+).*?(кол-во|количество|qty|quantity)\\s+(\\d+)', text)
    if qty_match:
        try:
            line_num = int(qty_match.group(2))
            qty = qty_match.group(4).strip()
            return {
                "action": "set_quantity",
                "line_index": line_num - 1,  # Конвертируем в 0-based индекс
                "value": qty
            }
        except Exception:
            pass
    
    # Распознавание команды редактирования строки (единица измерения)
    unit_match = re.search(r'(строк[аи]?|line|row)\\s+(\\d+).*?(ед[\\.\\s]изм[\\.ерение]*|unit)\\s+(\\w+)', text)
    if unit_match:
        try:
            line_num = int(unit_match.group(2))
            unit = unit_match.group(4).strip()
            return {
                "action": "set_unit",
                "line_index": line_num - 1,  # Конвертируем в 0-based индекс
                "value": unit
            }
        except Exception:
            pass
    
    # Распознавание команды изменения даты
    date_match = re.search(r'дат[аы]?\\s+(\\d{1,2})[\\\s./-](\\d{1,2}|января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)', text)
    if date_match:
        # Для даты используем адаптер IntentAdapter для корректного форматирования
        from app.assistants.intent_adapter import adapt_intent
        return adapt_intent(f"set_date {user_input}")
    
    # Если ничего не распознано, возвращаем None
    return None
"""

# Замена всей функции
pattern = r'def attempt_fast_intent_recognition.*?return None'
replacement = new_function.strip()
content = re.sub(pattern, replacement, content, flags=re.DOTALL)

# Записываем исправленное содержимое в файл
with open(client_file, 'w') as f:
    f.write(content)

print(f"Функция attempt_fast_intent_recognition полностью заменена в файле {client_file}") 