#!/usr/bin/env python3
# Скрипт для исправления отступов в блоке except в файле app/assistants/client.py

import re

# Путь к файлу client.py
client_file = 'app/assistants/client.py'

# Читаем весь файл
with open(client_file, 'r') as f:
    content = f.read()

# Исправление отступов в проблемном блоке except
pattern = r'            except Exception as e:\n        logger\.exception\(f"\[run_thread_safe_async\] Error in OpenAI Assistant API call: \{e\}"\)\n                return \{\n                    "action": "unknown", \n            "error": str\(e\),\n            "user_message": "An error occurred while processing your request\. Please try again\."\n        \}'

replacement = '''            except Exception as e:
                logger.exception(f"[run_thread_safe_async] Error in OpenAI Assistant API call: {e}")
                return {
                    "action": "unknown", 
                    "error": str(e),
                    "user_message": "An error occurred while processing your request. Please try again."
                }'''

content = re.sub(pattern, replacement, content)

# Записываем исправленное содержимое в файл
with open(client_file, 'w') as f:
    f.write(content)

print(f"Исправлен блок except в файле {client_file}") 