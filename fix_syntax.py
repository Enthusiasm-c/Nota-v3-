#!/usr/bin/env python3
"""
Скрипт для исправления синтаксических ошибок в файле bot.py
"""

import re
import sys

def fix_indentation(line):
    """Исправляет неправильные отступы в строке."""
    # Удаляем лишние отступы в начале строки
    return line.lstrip()

def fix_file(input_file, output_file):
    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    fixed_lines = []
    in_try_block = False
    expect_except = False
    bracket_stack = []
    
    for i, line in enumerate(lines):
        # Фиксим блок try-except
        if re.match(r'\s*try\s*:', line):
            in_try_block = True
        elif in_try_block and re.match(r'\s*except\s+', line):
            in_try_block = False
            expect_except = False
        
        # Отслеживаем скобки для выравнивания
        opening_count = line.count('(')
        closing_count = line.count(')')
        
        for _ in range(opening_count):
            bracket_stack.append(1)
        
        for _ in range(closing_count):
            if bracket_stack:
                bracket_stack.pop()
        
        # Исправляем конкретные ошибки
        if i+1 == 935:  # Строка 935 - проблема с началом блока
            line = line.replace('reply_msg = await callback.message.bot.send_message(', 
                               'reply_msg = await callback.message.bot.send_message(\n')
        
        # Исправление для строки с keyboard в блоке handle_field_edit
        if i+1 == 1038:  # Около строки 1038
            if 'keyboard = ' in line:
                # Выравниваем отступ
                line = '            keyboard = build_edit_keyboard(True)\n'
        
        # Исправление для блока с result в try-except
        if i+1 == 1044:  # Около строки 1044
            if 'result = await message.answer(' in line:
                # Полностью переписываем блок
                line = '                    result = await message.answer(\n'
                fixed_lines.append(line)
                fixed_lines.append('                        formatted_report,\n')
                fixed_lines.append('                        reply_markup=keyboard,\n')
                fixed_lines.append('                        parse_mode="HTML"\n')
                fixed_lines.append('                    )\n')
                continue  # Пропускаем добавление оригинальной строки
        
        # Исправление строки return с неправильным отступом (строка 998)
        if i+1 == 998 and 'return' in line and line.strip() == 'return':
            line = '        return\n'
        
        fixed_lines.append(line)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.writelines(fixed_lines)

if __name__ == "__main__":
    # Создаем резервную копию и исправляем файл
    fix_file('bot.py', 'bot_fixed.py')
    print("Файл исправлен и сохранен как bot_fixed.py") 