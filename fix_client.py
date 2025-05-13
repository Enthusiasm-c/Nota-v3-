#!/usr/bin/env python3
# Скрипт для исправления отступов в файле app/assistants/client.py

import re

# Путь к файлу client.py
client_file = 'app/assistants/client.py'

# Читаем весь файл
with open(client_file, 'r') as f:
    content = f.read()

# Исправление отступов в блоке обработки name
content = re.sub(
    r'(                name = match_name\.group\(2\)\.strip\(\)\n'
    r'                results\.append\(\{"action": "set_name", "line": line, "name": name\}\)\n)'
    r'                    except Exception:',
    r'\1            except Exception:', 
    content
)

# Исправление отступов в блоке обработки unit
content = re.sub(
    r'(                elif invoice_lines is not None and \(line < 0 or line >= invoice_lines\):\n'
    r'                    results\.append\(\{"action": "unknown", "error": "line_out_of_range", "line": line\}\)\n'
    r'                    continue\n)'
    r'                    \n'
    r'                    (unit = match_unit\.group\(2\)\.strip\(\)\n'
    r'                    results\.append\(\{"action": "set_unit", "line": line, "unit": unit\}\))',
    r'\1                \n\2',
    content
)

# Записываем исправленное содержимое в новый файл
with open(f'{client_file}.fixed', 'w') as f:
    f.write(content)

print(f"Создан исправленный файл {client_file}.fixed")
print("Проверьте его и замените оригинальный файл для применения изменений.") 