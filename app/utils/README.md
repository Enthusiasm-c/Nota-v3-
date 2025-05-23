# Утилиты для Nota Telegram Бота

Этот каталог содержит утилиты и вспомогательные классы, используемые в Nota Telegram боте.

## IncrementalUI - Класс для прогрессивных обновлений UI

Класс `IncrementalUI` предоставляет возможность создавать прогрессивные обновления интерфейса пользователя в Telegram боте. Это улучшает UX, делая длительные операции более наглядными и информативными для пользователей.

### Возможности

- Создание, обновление и завершение сообщений с индикатором прогресса
- Поддержка анимированного спиннера для индикации активного процесса
- Добавление новых строк к сообщению без изменения предыдущих
- Автоматический троттлинг обновлений для предотвращения перегрузки Telegram API
- Поддержка обработки ошибок и отображение сообщений об ошибках
- Удобные хелперы для стандартных сценариев использования

### Пример использования

```python
async def handle_long_process(message: Message):
    # Инициализируем и запускаем UI
    ui = IncrementalUI(message.bot, message.chat.id)
    await ui.start("Начинаем обработку...")

    try:
        # Шаг 1: Загрузка данных
        await ui.start_spinner()  # Запуск анимированного спиннера
        data = await load_data()
        ui.stop_spinner()  # Остановка спиннера
        await ui.update("✅ Данные загружены")

        # Шаг 2: Обработка данных
        await ui.append("🔄 Обработка данных...")
        await process_data(data)
        await ui.update("✅ Данные обработаны", replace_last=True)

        # Шаг 3: Формирование отчета
        await ui.append("📊 Формирование отчета...")
        result = await generate_report(data)

        # Добавляем результат с клавиатурой
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(text="Подробнее", callback_data="details"),
                InlineKeyboardButton(text="Готово", callback_data="done")
            ]]
        )

        # Завершаем UI с финальным сообщением и клавиатурой
        await ui.complete("✅ Обработка завершена!", keyboard)

        return result

    except Exception as e:
        # В случае ошибки, показываем информативное сообщение
        await ui.error(f"Произошла ошибка: {str(e)}")
        return None
```

### Хелпер with_progress

Для упрощения типовых сценариев, класс предоставляет статический метод `with_progress`:

```python
result = await IncrementalUI.with_progress(
    message=message,
    initial_text="Начинаем обработку...",
    process_func=process_data,  # Асинхронная функция с логикой обработки
    final_text="Обработка успешно завершена!",
    final_kb=keyboard,  # Опциональная клавиатура для финального сообщения
    error_text="При обработке произошла ошибка"  # Шаблон для сообщения об ошибке
)
```

### Интеграция с существующими обработчиками

Для интеграции в существующие обработчики:

1. Импортируйте класс: `from app.utils.incremental_ui import IncrementalUI`
2. Создайте экземпляр в начале асинхронной функции
3. Используйте методы `start`, `update`, `append` и `complete` для обновления UI
4. Оберните критические операции в `try-except` и вызывайте `ui.error()` при ошибках

### Примеры кода и интеграции

- `/app/utils/incremental_ui_example.py` - примеры использования класса
- `/app/handlers/incremental_edit_flow.py` - интеграция с обработчиком редактирования
- `/app/handlers/incremental_photo_handler.py` - интеграция с обработчиком фото
