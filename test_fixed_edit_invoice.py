#!/usr/bin/env python3
"""
Тестовый скрипт для диагностики и исправления проблемы с отсутствием кнопки 
"Отправить накладную" после редактирования инвойса без ошибок.
"""

import logging
import asyncio
from pprint import pprint
from copy import deepcopy

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

# Тест, который проверяет как распознается статус ошибок
async def test_invoice_status():
    """Тестирует определение статуса has_errors в build_report и формирование клавиатуры"""
    try:
        from app.formatters.report import build_report
        from app.matcher import match_positions
        from app.data_loader import load_products
        
        # 1. Загружаем тестовый инвойс
        print("\n=== Тест статуса инвойса после редактирования ===")
        invoice = deepcopy(test_invoice)
        
        # 2. Запускаем матчинг позиций
        print("Запускаем матчинг позиций...")
        products = load_products()
        match_results = match_positions(invoice["positions"], products)
        
        # 3. Формируем отчет
        print("Формируем отчет...")
        text, has_errors = build_report(invoice, match_results)
        print(f"Результат has_errors = {has_errors}")
        
        # Диагностика внутреннего кода build_report
        print("\n=== Диагностика функции build_report ===")
        
        # Проверяем статусы позиций
        statuses = [item.get("status", "") for item in match_results]
        print(f"Статусы всех позиций: {statuses}")
        
        # Подсчитываем вручную ошибки
        ok_count = sum(1 for item in match_results if item.get("status") == "ok" or item.get("status") == "manual")
        issues_count = len(match_results) - ok_count
        print(f"Ручной подсчет: ok_count={ok_count}, issues_count={issues_count}")
        
        # Проверяем поля qty и price
        for idx, item in enumerate(match_results):
            qty = item.get("qty", None)
            price = item.get("price", None) 
            if price in (None, "", "—"):
                price = item.get("unit_price", None)
                
            if qty in (None, "", "—") or price in (None, "", "—"):
                print(f"⚠️ Позиция {idx + 1}: отсутствует цена или количество")
        
        # 4. Проверяем формирование клавиатуры
        print("\n=== Проверка формирования клавиатуры ===")
        from app.keyboards import build_main_kb
        keyboard = build_main_kb(has_errors)
        
        # Проверяем наличие кнопки подтверждения
        confirm_button_exists = len(keyboard.inline_keyboard) > 1
        confirm_button_text = keyboard.inline_keyboard[1][0].text if confirm_button_exists else "Кнопка отсутствует"
        
        print(f"Наличие кнопки подтверждения: {confirm_button_exists}")
        print(f"Текст кнопки: {confirm_button_text if confirm_button_exists else 'Н/Д'}")
        
        # 5. Смотрим на поведение process_user_edit в edit_core.py
        print("\n=== Анализ обработки в process_user_edit ===")
        from app.handlers.edit_core import process_user_edit
        
        # Проверяем условие переопределения has_errors
        unknown_count = sum(1 for r in match_results if r.get("status") == "unknown")
        partial_count = sum(1 for r in match_results if r.get("status") == "partial")
        print(f"unknown_count={unknown_count}, partial_count={partial_count}")
        
        # Имитируем проверку из edit_core.py
        forced_has_errors = False
        if not has_errors and (unknown_count > 0 or partial_count > 0):
            forced_has_errors = True
        print(f"Форсированный has_errors={forced_has_errors}")
        
        # 6. Проверяем также значение для окончательной клавиатуры
        print("\n=== Окончательное состояние клавиатуры ===")
        final_has_errors = has_errors or forced_has_errors  
        final_keyboard = build_main_kb(final_has_errors)
        
        final_confirm_button_exists = len(final_keyboard.inline_keyboard) > 1
        final_confirm_button_text = final_keyboard.inline_keyboard[1][0].text if final_confirm_button_exists else "Кнопка отсутствует"
        
        print(f"Финальный has_errors={final_has_errors}")
        print(f"Наличие кнопки в финальной клавиатуре: {final_confirm_button_exists}")
        print(f"Текст кнопки: {final_confirm_button_text if final_confirm_button_exists else 'Н/Д'}")
        
        # 7. Рекомендации по исправлению
        print("\n=== Рекомендации по исправлению ===")
        if has_errors:
            print("1. Проверьте логику определения has_errors в build_report:")
            print("   - Убедитесь, что статусы 'ok' и 'manual' считаются корректными")
            print("   - Проверьте правильность подсчета issues_count")
        
        if forced_has_errors:
            print("2. В файле edit_core.py (строка ~180) изменить условие:")
            print("   Было: if not has_errors and (unknown_count > 0 or partial_count > 0):")
            print("   Стало: if unknown_count > 0 or partial_count > 0:")
            print("   Или удалить это принудительное переопределение flag has_errors")
            
        if not has_errors and not forced_has_errors and not final_confirm_button_exists:
            print("3. Проверьте передачу правильного значения has_errors в build_main_kb в incremental_edit_flow.py")
            
    except Exception as e:
        logger.error(f"Ошибка при тестировании: {e}", exc_info=True)

# Основная функция для запуска тестов
def main():
    """Запускает тесты и выводит результаты"""
    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(test_invoice_status())
    except Exception as e:
        logger.error(f"Ошибка в main: {e}", exc_info=True)

if __name__ == "__main__":
    main() 