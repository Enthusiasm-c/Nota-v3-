#!/usr/bin/env python3
# Скрипт для удаления неполного блока except в файле app/assistants/client.py

import re

# Путь к файлу client.py
client_file = 'app/assistants/client.py'

# Читаем весь файл
with open(client_file, 'r') as f:
    content = f.read()

# Удаление проблемного блока except
pattern = r'        # Остальной код для обработки ошибок остаётся без изменений\n        # \.\.\.\n\n        try:\n            # Здесь должен быть код, который мог вызвать исключение\n            pass  # Заглушка\n        except Exception as e:\n            logger\.exception\(f"\[run_thread_safe_async\] Error in OpenAI Assistant API call: \{e\}"\)\n            return \{\n                "action": "unknown", \n                "error": str\(e\),\n                "user_message": "An error occurred while processing your request\. Please try again\."\n            \}'

replacement = '''        # Остальной код для обработки ошибок остаётся без изменений
        # ...'''

content = re.sub(pattern, replacement, content)

# Записываем исправленное содержимое в файл
with open(client_file, 'w') as f:
    f.write(content)

print(f"Удален проблемный блок except в файле {client_file}") 