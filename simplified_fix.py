#!/usr/bin/env python3
"""
Анализатор и корректор проблем с кнопками в Telegram боте.
Этот скрипт анализирует код и применяет важные исправления к файлам для устранения проблемы зависания бота.
"""

import os
import re
import sys
import shutil
import time
from pathlib import Path

# Версия скрипта
VERSION = "1.0.0"
# Файлы для анализа
BOT_FILE = "bot.py"
HANDLERS_FILE = "app/handlers.py"
PHOTO_HANDLER_FILE = "app/handlers/incremental_photo_handler.py"

# Цвета для вывода в консоль
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def print_header(text):
    """Печать заголовка."""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text.center(80)}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.ENDC}\n")

def print_info(text):
    """Печать информационного сообщения."""
    print(f"{Colors.BLUE}[INFO] {text}{Colors.ENDC}")

def print_success(text):
    """Печать успешного действия."""
    print(f"{Colors.GREEN}[OK] {text}{Colors.ENDC}")

def print_warning(text):
    """Печать предупреждения."""
    print(f"{Colors.WARNING}[WARNING] {text}{Colors.ENDC}")

def print_error(text):
    """Печать ошибки."""
    print(f"{Colors.FAIL}[ERROR] {text}{Colors.ENDC}")

def backup_file(file_path):
    """Создает резервную копию файла."""
    if not os.path.exists(file_path):
        print_error(f"Файл {file_path} не найден!")
        return False
    
    backup_path = f"{file_path}.bak.{int(time.time())}"
    shutil.copy2(file_path, backup_path)
    print_info(f"Создана резервная копия: {backup_path}")
    return True

def check_file_content(file_path, patterns):
    """Проверяет содержимое файла на наличие паттернов."""
    if not os.path.exists(file_path):
        print_error(f"Файл {file_path} не найден!")
        return {}
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    results = {}
    for name, pattern in patterns.items():
        matches = re.findall(pattern, content, re.DOTALL)
        results[name] = matches
    
    return results

def fix_cancel_button_in_bot(file_path):
    """Исправляет обработчик кнопки Cancel в главном файле бота."""
    if not os.path.exists(file_path):
        print_error(f"Файл {file_path} не найден!")
        return False
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Ищем обработчик cancel:all
    handler_pattern = r'(@dp\.callback_query\(F\.data == "cancel:all"\).*?async def handle_cancel_all.*?\n\s*logger\.info.*?)(\n\s*\n)'
    handler_found = re.search(handler_pattern, content, re.DOTALL)
    
    if not handler_found:
        print_warning("Не найден обработчик cancel:all в bot.py!")
        return False
    
    # Заменяем обработчик на исправленную версию
    fixed_handler = '''@dp.callback_query(F.data == "cancel:all")
        async def handle_cancel_all(call, state: FSMContext):
            """Обработчик кнопки Cancel с установкой правильного состояния"""
            # Немедленно отвечаем на callback
            await call.answer("Отмена")
            
            # Очищаем состояние полностью для устранения зависаний
            await state.clear()
            
            # Устанавливаем новое чистое состояние
            await state.set_state(NotaStates.main_menu)
            
            # Импортируем клавиатуру заранее
            from app.keyboards import kb_main
            
            # Удаляем клавиатуру (потенциально может вызвать ошибку)
            try:
                await call.message.edit_reply_markup(reply_markup=None)
            except Exception as e:
                logger.warning(f"Не удалось удалить клавиатуру: {e}")
            
            # Отправляем новое сообщение
            try:
                await call.message.answer(
                    "Обработка отменена. Вы можете загрузить новое фото чека.",
                    reply_markup=kb_main(lang="en")
                )
                logger.info(f"Пользователь {call.from_user.id} отменил обработку и вернулся в главное меню")
            except Exception as e:
                logger.error(f"Ошибка при отправке сообщения: {e}")
                # В случае ошибки пытаемся отправить сообщение без клавиатуры
                await call.message.answer("Операция отменена.")
'''
    
    # Заменяем обработчик
    updated_content = re.sub(handler_pattern, r'\\1\n        '.join(fixed_handler.split('\n')) + r'\2', content, flags=re.DOTALL)
    
    # Проверка, изменилось ли содержимое
    if updated_content == content:
        print_warning("Не удалось обновить обработчик cancel:all в bot.py!")
        return False
    
    # Сохраняем изменения
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(updated_content)
    
    print_success("Обработчик cancel:all в bot.py исправлен!")
    return True

def fix_upload_new_button_in_bot(file_path):
    """Исправляет обработчик кнопки Upload New в главном файле бота."""
    if not os.path.exists(file_path):
        print_error(f"Файл {file_path} не найден!")
        return False
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Ищем обработчик action:new
    handler_pattern = r'(@dp\.callback_query\(F\.data == "action:new"\).*?async def cb_new_invoice.*?\n\s*logger\.info.*?)(\n\s*\n)'
    handler_found = re.search(handler_pattern, content, re.DOTALL)
    
    if not handler_found:
        # Возможно, обработчик не существует или имеет другой формат
        print_warning("Не найден обработчик action:new в bot.py!")
        
        # Ищем место, где нужно добавить обработчик
        insertion_point = r'(        # Регистрируем команду старт\n        dp\.message\.register\(cmd_start, CommandStart\(\)\)\n\s*\n)'
        insertion_found = re.search(insertion_point, content, re.DOTALL)
        
        if not insertion_found:
            print_error("Не найдено место для добавления обработчика action:new!")
            return False
        
        # Создаем новый обработчик
        new_handler = '''        # Регистрируем обработчик кнопки "Upload New Invoice" (action:new)
        @dp.callback_query(F.data == "action:new")
        async def cb_new_invoice(call: CallbackQuery, state: FSMContext):
            """Простой обработчик для кнопки Upload New Invoice"""
            # Немедленно отвечаем на callback
            await call.answer()
            
            # Полностью очищаем состояние и устанавливаем новое
            await state.clear()
            await state.set_state(NotaStates.awaiting_file)
            
            # Отправляем сообщение без сложных импортов
            await call.message.answer("Пожалуйста, отправьте фото чека.")
            
            logger.info(f"Пользователь {call.from_user.id} запросил загрузку нового инвойса")
'''
        
        # Добавляем обработчик
        updated_content = re.sub(insertion_point, r'\1' + new_handler, content, flags=re.DOTALL)
        
        # Проверка, изменилось ли содержимое
        if updated_content == content:
            print_warning("Не удалось добавить обработчик action:new в bot.py!")
            return False
        
        # Сохраняем изменения
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(updated_content)
        
        print_success("Добавлен новый обработчик action:new в bot.py!")
        return True
    
    # Если обработчик найден, заменяем его
    fixed_handler = '''@dp.callback_query(F.data == "action:new")
        async def cb_new_invoice(call: CallbackQuery, state: FSMContext):
            """Простой обработчик для кнопки Upload New Invoice"""
            # Немедленно отвечаем на callback
            await call.answer()
            
            # Полностью очищаем состояние и устанавливаем новое
            await state.clear()
            await state.set_state(NotaStates.awaiting_file)
            
            # Отправляем сообщение без сложных импортов
            await call.message.answer("Пожалуйста, отправьте фото чека.")
            
            logger.info(f"Пользователь {call.from_user.id} запросил загрузку нового инвойса")
'''
    
    # Заменяем обработчик
    updated_content = re.sub(handler_pattern, lambda m: fixed_handler + m.group(2), content, flags=re.DOTALL)
    
    # Проверка, изменилось ли содержимое
    if updated_content == content:
        print_warning("Не удалось обновить обработчик action:new в bot.py!")
        return False
    
    # Сохраняем изменения
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(updated_content)
    
    print_success("Обработчик action:new в bot.py исправлен!")
    return True

def fix_handlers_file(file_path):
    """Исправляет конфликты в файле обработчиков."""
    if not os.path.exists(file_path):
        print_error(f"Файл {file_path} не найден!")
        return False
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Ищем обработчик cancel:all
    handler_pattern = r'(@router\.callback_query\(.*?cancel:all.*?\).*?async def handle_cancel.*?\n\s*await call\.answer.*?)\n\s*# Обработка кнопки "Cancel all".*?return\n'
    handler_found = re.search(handler_pattern, content, re.DOTALL)
    
    if not handler_found:
        print_warning("Не найден конфликтующий обработчик в handlers.py!")
        return False
    
    # Заменяем обработчик на версию, которая пропускает cancel:all
    fixed_content = re.sub(handler_pattern,
        r'@router.callback_query(lambda call: call.data.startswith("cancel:") and call.data != "cancel:all")\n'
        r'async def handle_cancel_row(call: CallbackQuery, state: FSMContext):\n'
        r'    """Обработчик кнопок cancel:<index> (НЕ для cancel:all)"""\n'
        r'    # Немедленно отвечаем на callback\n'
        r'    await call.answer("Отмена редактирования строки")\n\n'
        r'    # Для других кнопок с cancel продолжаем обработку\n',
        content, flags=re.DOTALL)
    
    # Проверка, изменилось ли содержимое
    if fixed_content == content:
        print_warning("Не удалось исправить обработчик в handlers.py!")
        return False
    
    # Сохраняем изменения
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(fixed_content)
    
    print_success("Обработчик в handlers.py исправлен для предотвращения конфликтов!")
    return True

def main():
    """Основная функция скрипта."""
    print_header(f"Анализатор и корректор проблем с кнопками Telegram бота v{VERSION}")
    print_info("Анализ и исправление проблем с кнопками в Telegram боте...")
    
    # Проверка наличия файлов
    for file_path in [BOT_FILE, HANDLERS_FILE, PHOTO_HANDLER_FILE]:
        if not os.path.exists(file_path):
            print_error(f"Файл {file_path} не найден!")
            return 1
    
    # Создание резервных копий
    for file_path in [BOT_FILE, HANDLERS_FILE, PHOTO_HANDLER_FILE]:
        backup_file(file_path)
    
    # Исправление обработчиков кнопок
    fix_cancel_button_in_bot(BOT_FILE)
    fix_upload_new_button_in_bot(BOT_FILE)
    fix_handlers_file(HANDLERS_FILE)
    
    print_header("Исправления применены!")
    print_info("Теперь необходимо перезапустить бота с помощью скрипта:")
    print_info("./start_bot_debugged.sh")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())