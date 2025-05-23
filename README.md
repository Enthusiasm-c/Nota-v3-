# Nota-v3 Telegram Bot

## Описание

Telegram-бот для автоматической проверки товарных накладных:
- Принимает фото накладной
- Распознаёт позиции через OpenAI Vision (gpt-4o)
- Сверяет с CSV-базой поставщиков и продуктов
- Формирует отчёт в MarkdownV2
- Отвечает пользователю в Telegram

## Форматирование отчёта

Формирование итогового отчёта реализовано в функции `build_report` (`app/formatters/report.py`).

- **Структура отчёта:**
  - Шапка с поставщиком и датой.
  - Разделитель (`──────────────────────────────`).
  - Таблица позиций в Markdown (тройные обратные кавычки, без языка).
  - Разделитель.
  - Итоговые строки: количество успешно определённых позиций и требующих подтверждения.
  - Статус: `ok` (если все позиции успешно определены) или `need check` (если есть нераспознанные или подозрительные позиции).
  - Финальный разделитель.
- **Таблица:**
  - Фиксированная ширина колонок для мобильного отображения.
  - Длинные названия товаров автоматически усекаются с многоточием (`…`).
  - Статусы отображаются с эмодзи (✅, ❓, ⚠️) и текстом.
  - Для Markdown-режима спецсимволы экранируются.
- **Пример блока таблицы:**

    ```
    #   NAME               QTY    UNIT        TOTAL
    1   verylongproductnam…   2    kg      1 000  ✅ ok
    ...
    ```
- **Строки summary:**
  - `Было успешно определено N позиций`
  - `Позиции, требующие подтверждения: M шт.`
  - `ok` или `need check` (см. выше)
- **Разделители** используются для визуального отделения блоков.

---

## UX редактирования и исправления ошибок (Обновлено 2025-05-05)

**Интеллектуальное редактирование с GPT-3.5-turbo:**
- Новая реализация на основе GPT-3.5-turbo для естественного понимания команд пользователя.
- Для исправления ошибок или внесения изменений пользователь пишет свободный текст (например: `строка 2 цена 90000` или `дата 16 апреля`).
- GPT-3.5-turbo распознаёт команду и генерирует JSON-интент, который затем применяется к данным.
- Система полностью понимает естественный язык без необходимости в строгом синтаксисе команд.
- Всё редактирование происходит через одну основную кнопку "✏️ Редактировать".

**Архитектура и принципы работы:**
- Модуль `app/assistants/client.py` обеспечивает безопасное взаимодействие с OpenAI API.
- Модуль `app/edit/apply_intent.py` реализует функции применения интентов к инвойсу (set_price, set_date, и др.).
- Модуль `app/handlers/edit_flow.py` отвечает за обработку сообщений и вызов соответствующих модулей.
- Чёткое разделение ответственностей между модулями улучшает тестируемость и поддерживаемость кода.
- В логах отображается время выполнения запроса к GPT: "Assistant run ok in X.X s".

**Преимущества нового подхода:**
- **Улучшенный UX**: пользователи могут писать команды на естественном языке без жёсткой структуры.
- **Масштабируемость**: легко добавлять новые типы команд, расширяя возможности GPT.
- **Надёжность**: улучшенная обработка ошибок и восстановление при проблемах с API.
- **Поддержка разных форматов**: понимание дат, цен, количества и других атрибутов в разных форматах.
- **Производительность**: быстрая обработка команд с таймаутом 60 секунд.
- **Безопасность**: данные обрабатываются локально после получения интента от GPT.

**Test-Driven Development (TDD):**
- Разработка велась по методологии TDD: сначала тесты, затем код.
- Создан подробный тестовый план в `docs/TEST_PLAN.md` с критериями успеха.
- Все сценарии редактирования покрыты автотестами:
  - `test_free_edit_price.py`: редактирование цены позиции
  - `test_free_edit_date.py`: редактирование даты инвойса
  - `test_apply_intent.py`: тесты логики применения интентов
- Тестируется как интеграция с GPT, так и отдельные компоненты системы.

## Быстрый старт

### Локальная разработка

1. Клонируйте репозиторий:
   ```sh
   git clone https://github.com/your-repo/nota-optimized.git
   cd nota-optimized
   ```

2. Создайте и активируйте виртуальное окружение:
   ```sh
   python -m venv venv
   source venv/bin/activate  # На Windows: venv\Scripts\activate
   ```

3. Установите зависимости:
   ```sh
   pip install -r requirements.txt
   ```

4. Заполните `.env` (см. пример в `.env.example` или используйте `.env.minimal` для минимальной конфигурации)
   ```sh
   cp .env.minimal .env
   # Отредактируйте .env, добавив ваши API ключи
   ```

5. Запустите проверки и тесты:
   ```sh
   ruff check .
   mypy app
   pytest -q
   ```

6. Запустите бота:
   ```sh
   make run-local
   # или напрямую:
   # python bot.py
   ```

### Быстрое развертывание на VPS

Для развертывания на небольшом VPS (1 vCPU, 1 GB RAM) используйте наш скрипт одиночного сервера:

```sh
# Полное руководство по развертыванию доступно в:
cat deploy/single_server_setup.md
```

Основные шаги:
1. Настройте сервер по инструкции в `deploy/single_server_setup.md`
2. Установите бота как системный сервис с автоматическим перезапуском
3. Настройте ротацию логов
4. Запустите скрипт тестирования для проверки работоспособности:
   ```sh
   bash scripts/send_test_invoices.sh
   ```

### Sprint 1: Inline corrections & self-learning aliases

- Inline UI for each invoice line: OK, Edit, Remove (in Telegram).
- Alias self-learning: when a new name is confirmed, it is appended to `data/aliases.csv` (no duplicates, lowercase).
- Fuzzy matcher: now merges aliases on startup and suggests top-5 similar products if unknown.
- Unit tests cover alias flow: unknown → edit → alias saved → next run = ok.
- All bot messages and inline captions in English.
- **Immutable data**: `data/base_products.csv` and `data/base_suppliers.csv` are read-only, all new aliases go to `data/aliases.csv`.

### Sprint 2: Real OCR Integration

- **Stub mode** (default): No OpenAI calls, works offline, fast tests.
- **Live mode**: Set `USE_OPENAI_OCR=1` and provide `OPENAI_API_KEY` in your environment to use GPT-4o Vision for real invoice parsing. Uses prompt from `prompts/invoice_ocr_en_v0.3.txt`.
- **Cassette-based tests**: On first run with a real key, a cassette is recorded in `tests/cassettes/`. On CI or without key, cassette is replayed for fast, safe tests.
- **Validation and error handling**: All OCR results validated with Pydantic. If parsing fails, user sees "⚠️ OCR failed, please retake the photo".
- **Number normalization**: Prices and totals are normalized to float (removes Rp, commas, dots, etc).
- **Timeout and logging**: Each OCR call times out after 30s and logs duration and image size.

### Обновление OCR (Май 2025)

В мае 2025 года была выполнена миграция с OpenAI Assistant на прямое использование OpenAI Vision API для OCR.

#### Преимущества:
- **Стабильность**: Более надежная работа без зависимостей от ассистентов.
- **Скорость**: Уменьшение времени обработки с 40-50 секунд до ~8-15 секунд.
- **Точность**: Значительно улучшенное распознавание накладных с меньшим количеством "галлюцинаций".
- **Контроль**: Полный контроль над системным промптом и форматом данных.

#### Технические изменения:
- OCR теперь использует прямой вызов модели `gpt-4-vision-preview` через OpenAI API.
- Улучшен системный промпт с чёткими инструкциями и запретом на галлюцинации.
- Добавлена обработка различных форматов ответа (чистый JSON, JSON с code fence).
- Обновлены тесты для проверки новой реализации.

#### Конфигурация:
Для работы OCR требуется:
1. Указать `OPENAI_OCR_KEY` в файле `.env`
2. Установить необходимые зависимости: `pip install openai pydantic-settings`

### How to enable real OCR

1. Set `USE_OPENAI_OCR=1` in your `.env` or environment.
2. Set your `OPENAI_API_KEY`.
3. Run tests:
   ```sh
   PYTHONPATH=. pytest tests/test_ocr_live.py
   ```
   On first run, cassette will be recorded. On CI, cassette is replayed.

### Roadmap
- [x] Sprint 1: Inline corrections, self-learning aliases
- [x] Sprint 2: Real OCR integration and cassette-based tests
- [x] Sprint C-5: GPT-3.5-turbo диалоговое редактирование и TDD
- [x] Sprint D-1: Walking Skeleton - минимальное production-ready развертывание для 10 инвойсов/день
- [ ] Sprint 3: Price anomaly alerts, daily Syrve CSV sync

---

### Running tests

This project uses `pytest` for running automated tests.

**1. Activate your virtual environment** (if you haven't already):

```sh
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

**2. Install testing dependencies:**

The testing dependencies, including `pytest`, are listed in `requirements-dev.txt`. Install them using:
```sh
pip install -r requirements-dev.txt
```

**3. Run all tests:**

From the root directory of the project, run the following command:

```sh
PYTHONPATH=. pytest
```

**4. Run a specific test file** (optional):

To run tests from a specific file, you can use:
```sh
PYTHONPATH=. pytest tests/test_alias_flow.py
```

This will run all unit tests in the specified file and check that the alias self-learning mechanism works as expected.

**Note:** As per the instructions for the current task, you should not actually run these test commands now. These instructions are for future reference.

## Структура

```
.
├── bot.py                # точка входа
├── app/
│   ├── config.py         # настройки
│   ├── data_loader.py    # загрузка CSV
│   ├── ocr.py            # OCR stub (OpenAI Vision)
│   ├── matcher.py        # fuzzy & exact match
│   ├── formatters/       # форматирование отчётов
│   │   └── report.py     # построение отчётов
│   ├── edit/             # редактирование инвойсов
│   │   ├── free_parser.py# парсер текстовых команд (устаревший)
│   │   └── apply_intent.py# применение интентов GPT
│   ├── assistants/       # взаимодействие с OpenAI Assistant
│   │   └── client.py     # клиент для OpenAI Assistant API
│   ├── handlers/         # обработчики сообщений
│   │   └── edit_flow.py  # обработка команд редактирования
│   ├── fsm/              # конечные автоматы состояний
│   │   └── states.py     # определение состояний бота
│   └── keyboards.py      # клавиатуры для интерфейса
├── data/
│   ├── suppliers.csv     # база поставщиков
│   ├── products.csv      # база продуктов
│   └── aliases.csv       # самообучающиеся алиасы
├── docs/                 # документация
│   ├── CHANGELOG.md      # история изменений
│   ├── PROJECT_OVERVIEW.md # обзор проекта
│   └── TEST_PLAN.md      # тестовый план
├── requirements.in / requirements.txt
├── .env.example
├── Makefile
└── tests/                # автотесты
```

## Переменные окружения

- `BOT_TOKEN` — токен Telegram-бота
- `OPENAI_API_KEY` — ключ OpenAI для OCR (Vision API)
- `OPENAI_ASSISTANT_ID` — ID Assistant для GPT-3.5-turbo (редактирование)
- `OPENAI_MODEL` — модель для OCR (по умолчанию gpt-4o)
- `MATCH_THRESHOLD` — порог fuzzy-сопоставления (default: 0.75)

## CI

GitHub Actions: `.github/workflows/ci.yml` — тесты и линт при push/pull_request
Nota-v3-

## Управление процессами

Для управления процессами бота доступны следующие скрипты:

### Запуск бота

- `run_bot.sh` - стандартный запуск бота
- `run_forever.sh` - запуск с автоматическим перезапуском при ошибках
- `debug_bot.sh` - запуск в режиме отладки с подробными логами

### Остановка бота

- `stop_service.sh` - корректная остановка бота через systemd (если запущен как сервис)
- `kill_all_nota_processes.sh` - принудительная остановка всех процессов, связанных с ботом
- `emergency_stop.sh` - экстренная остановка всех Python-процессов на сервере (использовать только в крайнем случае)

Для безопасной остановки бота рекомендуется использовать скрипт `stop_service.sh`.
В случае проблем с остановкой можно использовать `kill_all_nota_processes.sh`.
Скрипт `emergency_stop.sh` следует использовать только в экстренных случаях, когда все другие методы не работают.

## Модуль интеграции с Syrve API

Для отправки приходных накладных в систему Syrve (iiko) используется модуль `app/services/syrve_invoice_sender.py`.

### Настройка подключения

1. Скопируйте файл `.env.syrve.example` в `.env` и заполните его реальными значениями:
   ```
   SYRVE_BASE_URL=https://your-server.syrve.online
   SYRVE_LOGIN=your_username
   SYRVE_PASS_SHA1=sha1_hash_of_your_password
   ```

2. Для генерации SHA1-хеша пароля можно использовать команду:
   ```
   echo -n "your_password" | shasum
   ```

### Использование

```python
from app.services.syrve_invoice_sender import SyrveClient, Invoice, InvoiceItem
from decimal import Decimal
from datetime import date

# Создаем элементы накладной
items = [
    InvoiceItem(
        num=1,
        product_id="12345678-1234-1234-1234-123456789abc",  # GUID товара в Syrve
        amount=Decimal("10.5"),
        price=Decimal("100.00"),
        sum=Decimal("1050.00")
    )
]

# Создаем накладную
invoice = Invoice(
    items=items,
    supplier_id="87654321-4321-4321-4321-cba987654321",  # GUID поставщика
    default_store_id="11111111-2222-3333-4444-555555555555",  # GUID склада
    date_incoming=date.today()
)

# Инициализируем клиент из переменных окружения
client = SyrveClient.from_env()

# Отправляем накладную
try:
    result = client.send_invoice(invoice)
    if result:
        print("Накладная успешно импортирована в Syrve")
except Exception as e:
    print(f"Ошибка при отправке накладной: {e}")
```

### Обработка ошибок

Модуль предоставляет специализированные исключения для различных типов ошибок:

- `InvoiceValidationError` - ошибки валидации (неизвестный GUID товара, неверная сумма и т.д.)
- `InvoiceHTTPError` - ошибки HTTP при взаимодействии с API
- `InvoiceAuthError` - ошибки аутентификации

Рекомендуется обрабатывать эти исключения, чтобы предоставить пользователю понятное сообщение об ошибке.
