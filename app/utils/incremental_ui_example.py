"""
Пример использования класса IncrementalUI.

Этот файл демонстрирует, как можно интегрировать IncrementalUI
в существующие обработчики Telegram-бота для создания
прогрессивных обновлений интерфейса.
"""

import asyncio
import logging
from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from app.utils.incremental_ui import IncrementalUI
from app.i18n import t

logger = logging.getLogger(__name__)
router = Router()

def split_message(text, max_length=4096):
    """
    Разбивает длинный текст на части, не превышающие max_length символов.
    """
    parts = []
    while len(text) > max_length:
        split_at = text.rfind('\n', 0, max_length)
        if split_at == -1:
            split_at = max_length
        parts.append(text[:split_at])
        text = text[split_at:]
    if text:
        parts.append(text)
    return parts

# Пример 1: Базовое использование с простыми обновлениями
@router.message(F.text == "test_incremental_ui")
async def handle_test_incremental_ui(message: types.Message):
    """
    Пример использования IncrementalUI для показа прогресса обработки.
    """
    # Создаем экземпляр IncrementalUI
    ui = IncrementalUI(message.bot, message.chat.id)
    
    # Запускаем UI с начальным сообщением
    await ui.start("Начинаю обработку данных...")
    
    # Имитируем длительный процесс с обновлениями
    await asyncio.sleep(1)
    await ui.update("Загрузка данных: 25%")
    
    await asyncio.sleep(1)
    await ui.update("Загрузка данных: 50%")
    
    await asyncio.sleep(1)
    await ui.update("Загрузка данных: 75%")
    
    await asyncio.sleep(1)
    await ui.update("Загрузка данных: 100%")
    
    # Добавляем дополнительную информацию
    await ui.append("Обработка завершена")
    await ui.append("Найдено 10 записей")
    
    # Создаем клавиатуру для финального сообщения
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Подробнее", callback_data="details"),
                InlineKeyboardButton(text="Отмена", callback_data="cancel")
            ]
        ]
    )
    
    # Завершаем UI с финальным сообщением и клавиатурой
    await ui.complete("Операция успешно выполнена!", keyboard)

# Пример 2: Использование анимированного спиннера
@router.message(F.text == "test_spinner")
async def handle_test_spinner(message: types.Message):
    """
    Пример использования анимированного спиннера для индикации активного процесса.
    """
    ui = IncrementalUI(message.bot, message.chat.id)
    await ui.start("Инициализация процесса...")
    
    # Запускаем анимированный спиннер
    await ui.start_spinner()
    
    # Имитируем длительный процесс без явных прогрессивных этапов
    await asyncio.sleep(3)
    
    # Останавливаем спиннер и завершаем UI
    ui.stop_spinner()
    await ui.complete("Процесс завершен успешно!")

# Пример 3: Использование с обработкой ошибок
@router.message(F.text == "test_error")
async def handle_test_error(message: types.Message):
    """
    Пример обработки ошибки с использованием IncrementalUI.
    """
    ui = IncrementalUI(message.bot, message.chat.id)
    await ui.start("Запуск рискованной операции...")
    
    try:
        # Имитируем процесс с ошибкой
        await asyncio.sleep(1)
        await ui.update("Проверка данных...")
        await asyncio.sleep(1)
        
        # Имитируем ошибку
        raise ValueError("Недопустимый формат данных")
        
    except Exception as e:
        # Завершаем UI с сообщением об ошибке
        await ui.error(f"Ошибка: {str(e)}")

# Пример 4: Использование with_progress хелпера
@router.message(F.text == "test_with_progress")
async def handle_test_with_progress(message: types.Message):
    """
    Пример использования хелпера with_progress для упрощения кода.
    """
    async def process_data(ui):
        """Функция обработки данных, получает ui как параметр."""
        await asyncio.sleep(1)
        await ui.update("Шаг 1: Загрузка файлов")
        
        await asyncio.sleep(1)
        await ui.update("Шаг 2: Извлечение данных")
        
        await asyncio.sleep(1)
        await ui.update("Шаг 3: Проверка целостности")
        
        # Имитируем возврат результата
        return {"status": "success", "items": 42}
    
    # Используем with_progress для выполнения функции с UI
    result = await IncrementalUI.with_progress(
        message=message,
        initial_text="Начинаем обработку...",
        process_func=process_data,
        final_text="Обработка успешно завершена!",
        final_kb=InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(text="Готово", callback_data="done")
            ]]
        ),
        error_text="При обработке произошла ошибка"
    )
    
    # Используем результат функции (в реальном коде)
    logger.info(f"Результат обработки: {result}")

# Пример 5: Интеграция с существующим потоком редактирования
@router.message(F.text.startswith("edit"))
async def handle_edit_with_ui(message: types.Message, state: FSMContext):
    """
    Пример интеграции IncrementalUI с существующим потоком редактирования.
    """
    user_text = message.text[5:].strip()  # Убираем "edit " из начала
    
    # Получаем данные из состояния
    data = await state.get_data()
    invoice = data.get("invoice")
    lang = data.get("lang", "ru")  # Используем русский по умолчанию
    
    if not invoice or not user_text:
        await message.answer(t("edit.nothing_to_edit", lang=lang))
        return
    
    # Создаем UI
    ui = IncrementalUI(message.bot, message.chat.id)
    await ui.start("Анализирую запрос редактирования...")
    
    try:
        # Симуляция запроса к OpenAI для распознавания интента
        await asyncio.sleep(1.5)
        await ui.update("Определение необходимых изменений...")
        
        # Имитация применения изменений
        await asyncio.sleep(1)
        await ui.update("Применение изменений...")
        
        # Имитация обновления отчета
        await asyncio.sleep(1)
        
        # Подготовка результата
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="✏️ Продолжить редактирование", callback_data="edit:free"),
                    InlineKeyboardButton(text="✅ Готово", callback_data="inv_submit")
                ]
            ]
        )
        
        # Завершаем UI с обновленным отчетом
        await ui.complete("Редактирование успешно применено", keyboard)
        
    except Exception as e:
        await ui.error(f"Ошибка при редактировании: {str(e)}")