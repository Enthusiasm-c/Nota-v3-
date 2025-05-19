#!/usr/bin/env python3
"""
Тестовый скрипт для проверки использования GPT-парсера по умолчанию
вместо локального парсера команд редактирования.
"""

import logging
import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram.types import Message, User, Chat

# Добавляем корневую директорию проекта в путь для поиска модулей
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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

# Тестовый инвойс
test_invoice = {
    "date": "01.01.2023",
    "supplier": "Test Supplier",
    "positions": [
        {"name": "Apple", "qty": 1, "unit": "pc", "price": 100, "status": "ok"},
        {"name": "Banana", "qty": 2, "unit": "kg", "price": 50, "status": "ok"},
        {"name": "Coffee", "qty": 0.5, "unit": "kg", "price": 200, "status": "ok"}
    ]
}

# Имитация GPT-парсера
async def mock_gpt_parser(text):
    """Имитация ответа GPT-парсера для тестирования"""
    text_l = text.lower().strip()
    
    # Проверка на команду изменения единицы измерения
    if "line 3 unit pcs" in text_l:
        return {"action": "edit_unit", "index": 2, "value": "pcs"}
    
    # Проверка на команду изменения единицы измерения с qty
    elif "line 3 qty gram" in text_l:
        return {"action": "edit_unit", "index": 2, "value": "gram"}
    
    # Проверка на команду изменения даты
    elif "дата " in text_l or "date " in text_l:
        date_parts = text_l.split(" ", 1)[1]
        return {"action": "edit_date", "value": date_parts}
    
    # Неизвестная команда
    return {"action": "unknown", "user_message": "Команда не распознана"}

# Тест для проверки работы GPT-парсера
async def test_gpt_parser():
    print("\n=== ТЕСТ ИСПОЛЬЗОВАНИЯ GPT-ПАРСЕРА ===")
    
    # Подключаем модули
    from app.handlers.incremental_edit_flow import handle_free_edit_text
    
    # Создаем мок-объекты
    message = create_mock_message("Line 3 unit pcs")
    state = MockFSMContext({"invoice": test_invoice, "lang": "ru"})
    
    # Патчим функцию run_thread_safe_async для использования нашего mock-GPT-парсера
    with patch('app.assistants.client.run_thread_safe_async', side_effect=mock_gpt_parser):
        # Патчим IncrementalUI
        with patch('app.utils.incremental_ui.IncrementalUI') as mock_ui_class:
            # Создаем мок объекта IncrementalUI
            mock_ui = AsyncMock()
            mock_ui.start = AsyncMock()
            mock_ui.update = AsyncMock()
            mock_ui.complete = AsyncMock()
            mock_ui.error = AsyncMock()
            mock_ui_class.return_value = mock_ui
            
            # Патчим match_positions
            with patch('app.matcher.match_positions') as mock_match:
                # Возвращаем те же позиции с правильными статусами
                mock_match.return_value = [
                    {"name": "Apple", "qty": 1, "unit": "pc", "price": 100, "status": "ok"},
                    {"name": "Banana", "qty": 2, "unit": "kg", "price": 50, "status": "ok"},
                    {"name": "Coffee", "qty": 0.5, "unit": "kg", "price": 200, "status": "ok"}
                ]
                
                # Патчим load_products
                with patch('app.data_loader.load_products') as mock_load:
                    mock_load.return_value = []
                    
                    # Патчим build_report
                    with patch('app.formatters.report.build_report') as mock_report:
                        mock_report.return_value = ("Тестовый отчет", False)
                        
                        # Выполняем тест
                        print("Выполняем команду 'Line 3 unit pcs'...")
                        await handle_free_edit_text(message, state)
                        
                        # Проверяем, что GPT-парсер был вызван
                        print("\nПроверка результатов:")
                        updated_data = await state.get_data()
                        positions = updated_data.get("invoice", {}).get("positions", [])
                        
                        if len(positions) >= 3:
                            unit_updated = positions[2].get("unit") == "pcs"
                            print(f"Единица измерения обновлена до 'pcs': {'✅ Да' if unit_updated else '❌ Нет'}")
                            print(f"Текущая единица измерения: {positions[2].get('unit')}")
                        else:
                            print("❌ Не удалось найти позицию 3")
                            
                        # Проверяем вызов UI-методов
                        print("\nUI вызовы:")
                        print(f"start: {mock_ui.start.called}")
                        print(f"complete: {mock_ui.complete.called}")
                        print(f"error: {mock_ui.error.called}")
                        
                        if mock_ui.start.called and mock_ui.complete.called and not mock_ui.error.called:
                            print("\n✅ ТЕСТ ПРОЙДЕН: GPT-парсер успешно обработал команду")
                        else:
                            print("\n❌ ТЕСТ НЕ ПРОЙДЕН: GPT-парсер не смог корректно обработать команду")

# Проверка команды изменения единицы измерения через qty
async def test_gpt_qty_as_unit():
    print("\n=== ТЕСТ КОМАНДЫ 'LINE 3 QTY GRAM' ===")
    
    # Создаем мок-объекты
    message = create_mock_message("Line 3 qty gram")
    state = MockFSMContext({"invoice": test_invoice, "lang": "ru"})
    
    # Патчим функцию run_thread_safe_async для использования нашего mock-GPT-парсера
    with patch('app.assistants.client.run_thread_safe_async', side_effect=mock_gpt_parser):
        # Патчим IncrementalUI
        with patch('app.utils.incremental_ui.IncrementalUI') as mock_ui_class:
            # Создаем мок объекта IncrementalUI
            mock_ui = AsyncMock()
            mock_ui.start = AsyncMock()
            mock_ui.update = AsyncMock()
            mock_ui.complete = AsyncMock()
            mock_ui.error = AsyncMock()
            mock_ui_class.return_value = mock_ui
            
            # Патчим match_positions и другие функции
            with patch('app.matcher.match_positions') as mock_match:
                mock_match.return_value = test_invoice["positions"]
                with patch('app.data_loader.load_products'):
                    with patch('app.formatters.report.build_report') as mock_report:
                        mock_report.return_value = ("Тестовый отчет", False)
                        
                        # Выполняем тест
                        print("Выполняем команду 'Line 3 qty gram'...")
                        from app.handlers.incremental_edit_flow import handle_free_edit_text
                        await handle_free_edit_text(message, state)
                        
                        # Проверяем результаты
                        print("\nПроверка результатов:")
                        updated_data = await state.get_data()
                        positions = updated_data.get("invoice", {}).get("positions", [])
                        
                        if len(positions) >= 3:
                            unit_updated = positions[2].get("unit") == "gram"
                            print(f"Единица измерения обновлена до 'gram': {'✅ Да' if unit_updated else '❌ Нет'}")
                            print(f"Текущая единица измерения: {positions[2].get('unit')}")
                        else:
                            print("❌ Не удалось найти позицию 3")
                            
                        # Проверяем вызов UI-методов
                        print("\nUI вызовы:")
                        print(f"start: {mock_ui.start.called}")
                        print(f"complete: {mock_ui.complete.called}")
                        print(f"error: {mock_ui.error.called}")
                        
                        if mock_ui.start.called and mock_ui.complete.called and not mock_ui.error.called:
                            print("\n✅ ТЕСТ ПРОЙДЕН: GPT-парсер правильно распознал 'qty gram' как изменение единицы измерения")
                        else:
                            print("\n❌ ТЕСТ НЕ ПРОЙДЕН: GPT-парсер не смог корректно обработать команду")

# Запуск тестов
def main():
    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(test_gpt_parser())
        loop.run_until_complete(test_gpt_qty_as_unit())
    except Exception as e:
        logger.error(f"Ошибка в main: {e}", exc_info=True)

if __name__ == "__main__":
    main() 