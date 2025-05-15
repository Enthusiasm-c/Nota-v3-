#!/usr/bin/env python3
"""
Интеграционный тест для проверки полного процесса редактирования инвойса
и корректного отображения кнопки "Отправить накладную" после исправления.
"""

import asyncio
import logging
import re
from pprint import pprint
from copy import deepcopy
from aiogram.types import Message, User, Chat
from aiogram.fsm.context import FSMContext
from unittest.mock import AsyncMock, MagicMock, patch
import json

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Создаем тестовый инвойс без ошибок
test_invoice = {
    "date": "01.01.2023",
    "supplier": "Test Supplier",
    "positions": [
        {"name": "Apple", "qty": 1, "unit": "pc", "price": 100, "status": "ok"},
        {"name": "Banana", "qty": 2, "unit": "kg", "price": 50, "status": "ok"},
        {"name": "Coffee", "qty": 0.5, "unit": "kg", "price": 200, "status": "ok"}
    ]
}

# Имитация сообщения пользователя
def create_mock_message(text=""):
    message = AsyncMock(spec=Message)
    message.text = text
    message.answer = AsyncMock()
    message.answer.return_value = AsyncMock()
    message.from_user = MagicMock(spec=User)
    message.from_user.id = 123456
    message.chat = MagicMock(spec=Chat)
    message.chat.id = 123456
    message.bot = AsyncMock()
    return message

# Имитация состояния FSM
class MockFSMContext:
    def __init__(self, data=None):
        self.data = data or {}
        self.state = None
        
    async def get_data(self):
        return self.data
        
    async def update_data(self, **kwargs):
        self.data.update(kwargs)
        
    async def set_state(self, state):
        self.state = state
        
    async def clear(self):
        self.data = {}
        self.state = None

# Создаем собственный парсер интентов для тестов
async def test_intent_parser(text: str):
    """Упрощенный парсер интентов для тестирования"""
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
    
    # Парсинг команды редактирования единицы измерения с qty
    line_unit_match_qty = re.search(r"\b(?:строка|line)\s+(\d+)\s+qty\s+([a-zA-Zа-яА-Я]+)", text_l)
    if line_unit_match_qty:
        line_num = int(line_unit_match_qty.group(1)) - 1
        unit = line_unit_match_qty.group(2).strip()
        return {"action": "edit_unit", "index": line_num, "value": unit}
    
    # Парсинг команды редактирования строки с количеством
    line_qty_match = re.search(r"\b(?:строка|line)\s+(\d+)\s+(?:количество|quantity|qty)\s+(\d+[.,]?\d*)", text_l)
    if line_qty_match:
        line_num = int(line_qty_match.group(1)) - 1
        qty = line_qty_match.group(2).replace(',', '.')
        return {"action": "edit_quantity", "index": line_num, "value": qty}
    
    # Неизвестная команда
    return {"action": "unknown", "user_message": "Команда не распознана. Попробуйте еще раз."}

# Основной тест для проверки редактирования даты
async def test_full_edit_process():
    """Проверяет весь процесс редактирования и формирования клавиатуры"""
    try:
        print("\n=== ИНТЕГРАЦИОННЫЙ ТЕСТ РЕДАКТИРОВАНИЯ ИНВОЙСА ===")
        
        # Импортируем необходимую функцию
        from app.handlers.edit_core import process_user_edit
        
        # 1. Создаем мок-объекты
        message = create_mock_message("дата 15.03.2023")
        invoice = deepcopy(test_invoice)
        state = MockFSMContext({"invoice": invoice, "lang": "ru"})
        
        # Предварительная проверка исходного состояния
        original_date = invoice["date"]
        print(f"Исходная дата инвойса: {original_date}")
        
        # 2. Создаем функции обратного вызова для UI
        sent_messages = []
        
        async def mock_send_processing(text):
            sent_messages.append({"type": "processing", "text": text})
            
        async def mock_send_result(text):
            sent_messages.append({"type": "result", "text": text})
            
        async def mock_send_error(text):
            sent_messages.append({"type": "error", "text": text})
            
        async def mock_fuzzy_suggester(message, state, name, idx, lang):
            sent_messages.append({"type": "fuzzy", "name": name, "idx": idx})
            return False
            
        async def mock_edit_state():
            await state.set_state("edit_mode")
        
        # 3. Выполняем редактирование инвойса
        print("Выполняем команду редактирования даты...")
        
        # Патчим функцию match_positions, чтобы не зависеть от базы данных
        with patch('app.matcher.match_positions') as mock_match:
            # Возвращаем те же позиции с правильными статусами
            mock_match.return_value = [
                {"name": "Apple", "qty": 1, "unit": "pc", "price": 100, "status": "ok"},
                {"name": "Banana", "qty": 2, "unit": "kg", "price": 50, "status": "ok"},
                {"name": "Coffee", "qty": 0.5, "unit": "kg", "price": 200, "status": "ok"}
            ]
            
            # Патчим функцию load_products
            with patch('app.data_loader.load_products') as mock_load:
                mock_load.return_value = []
                
                # Выполняем редактирование
                result = await process_user_edit(
                    message=message,
                    state=state,
                    user_text="дата 15.03.2023",
                    lang="ru",
                    send_processing=mock_send_processing,
                    send_result=mock_send_result,
                    send_error=mock_send_error,
                    run_openai_intent=test_intent_parser,  # Используем наш тестовый парсер
                    fuzzy_suggester=mock_fuzzy_suggester,
                    edit_state=mock_edit_state
                )
                
                # Проверяем результат
                if result:
                    new_invoice, match_results, has_errors = result
                    print(f"Обновленная дата инвойса: {new_invoice.get('date', 'не найдена')}")
                    print(f"Статус has_errors: {has_errors}")
                    
                    # Создаем клавиатуру на основе результата
                    from app.keyboards import build_main_kb
                    keyboard = build_main_kb(has_errors)
                    confirm_button_exists = len(keyboard.inline_keyboard) > 1
                    
                    print(f"Наличие кнопки подтверждения: {confirm_button_exists}")
                    if confirm_button_exists:
                        print(f"Текст кнопки: {keyboard.inline_keyboard[1][0].text}")
                    else:
                        print("Кнопка подтверждения отсутствует!")
                    
                    # Проверка сообщений, отправленных пользователю
                    print("\nОтправленные сообщения:")
                    for idx, msg in enumerate(sent_messages):
                        print(f"  Сообщение {idx+1}: Тип={msg['type']}")
                    
                    # Проверка данных из состояния
                    state_data = await state.get_data()
                    print("\nСостояние после редактирования:")
                    print(f"  unknown_count: {state_data.get('unknown_count', 'отсутствует')}")
                    print(f"  partial_count: {state_data.get('partial_count', 'отсутствует')}")
                    
                    # Финальные проверки
                    print("\n=== РЕЗУЛЬТАТЫ ТЕСТА ===")
                    print(f"Дата изменена: {'ДА' if new_invoice.get('date') != original_date else 'НЕТ'}")
                    print(f"Кнопка подтверждения отображается: {'ДА' if confirm_button_exists else 'НЕТ'}")
                    print(f"Ошибок нет (has_errors=False): {'ДА' if not has_errors else 'НЕТ'}")
                    
                    if not has_errors and confirm_button_exists and new_invoice.get('date') != original_date:
                        print("\n✅ ТЕСТ ПРОЙДЕН: Редактирование работает корректно и кнопка подтверждения отображается!")
                    else:
                        print("\n❌ ТЕСТ НЕ ПРОЙДЕН: Есть проблемы с редактированием или отображением кнопки подтверждения.")
                else:
                    print("❌ Ошибка: process_user_edit вернул None")
        
    except Exception as e:
        logger.error(f"Ошибка при тестировании: {e}", exc_info=True)

# Запуск тестов
def main():
    """Запускает интеграционные тесты"""
    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(test_full_edit_process())
    except Exception as e:
        logger.error(f"Ошибка в main: {e}", exc_info=True)

if __name__ == "__main__":
    main() 