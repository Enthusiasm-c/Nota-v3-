# Руководство разработчика Nota AI

## Архитектура

### Принципы
1. **Разделение слоев**
   - Telegram-слой (`bot.py`, handlers, FSM) отделен от core logic
   - Core logic (`ocr_pipeline.py`, `matcher.py`) остается stateless
   - CSV как source of truth (MVP)

2. **Модули**
   - `app/ocr.py` - OCR через OpenAI Vision
   - `app/matcher.py` - сопоставление с базой
   - `app/validators/` - валидаторы (цены, единицы измерения)
   - `app/formatters/` - форматирование отчетов
   - `app/edit/` - редактирование через GPT-3.5

### Структура проекта
```
.
├── bot.py                # точка входа
├── app/
│   ├── config.py         # настройки
│   ├── data_loader.py    # загрузка CSV
│   ├── ocr.py            # OCR (OpenAI Vision)
│   ├── matcher.py        # fuzzy & exact match
│   ├── validators/       # валидаторы
│   ├── formatters/       # форматирование
│   ├── edit/            # редактирование
│   ├── handlers/        # обработчики
│   └── keyboards.py     # UI компоненты
├── data/               # CSV файлы
└── tests/             # автотесты
```

## Разработка

### Настройка окружения
1. Создайте виртуальное окружение:
   ```bash
   python -m venv venv
   source venv/bin/activate  # или venv\Scripts\activate на Windows
   ```

2. Установите зависимости:
   ```bash
   pip install -r requirements.txt
   ```

3. Настройте переменные окружения:
   ```bash
   cp .env.example .env
   # Отредактируйте .env
   ```

### Тестирование
1. Запуск всех тестов:
   ```bash
   PYTHONPATH=. pytest
   ```

2. Запуск конкретного теста:
   ```bash
   PYTHONPATH=. pytest tests/test_price_validation.py
   ```

3. Проверка типов:
   ```bash
   mypy app
   ```

### Кодовые конвенции
1. **PEP-8 + Ruff defaults**
2. **Типизация**: используйте `typing.Annotated`, `type aliases`, `pydantic.BaseModel`
3. **Async-first**: избегайте блокирующего I/O
4. **Логирование**: используйте `structlog` с полями `module` и `action`
5. **Тесты**: покрытие ≥80%

## OCR и Vision API

### Конфигурация OCR
- `USE_OPENAI_OCR=1` - включение реального OCR
- `OPENAI_API_KEY` - ключ OpenAI
- `OPENAI_MODEL` - модель (по умолчанию gpt-4-vision-preview)

### Режимы работы
1. **Stub mode** (default):
   - Без вызовов OpenAI
   - Быстрые тесты
   - Работа офлайн

2. **Live mode**:
   - Реальные вызовы Vision API
   - Запись кассет для тестов
   - Таймаут 30 секунд

## Управление процессами

### Запуск
- `run_bot.sh` - стандартный запуск
- `run_forever.sh` - с автоперезапуском
- `debug_bot.sh` - режим отладки

### Остановка
- `stop_service.sh` - через systemd
- `kill_all_nota_processes.sh` - принудительно
- `emergency_stop.sh` - экстренная остановка

## Интеграция с Syrve

### Настройка
1. Заполните `.env`:
   ```
   SYRVE_BASE_URL=https://your-server.syrve.online
   SYRVE_LOGIN=your_username
   SYRVE_PASS_SHA1=sha1_hash
   ```

### Использование
```python
from app.services.syrve_invoice_sender import SyrveClient, Invoice

client = SyrveClient.from_env()
result = client.send_invoice(invoice)
```

## Масштабирование
1. Параметризация через `DATA_DIR`
2. Background tasks при QPS > 2
3. Redis key-namespacing по `chat_id`
4. RAM < 150 MB на бота 