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

1. Установите зависимости:
   ```sh
   pip install -r requirements.txt
   ```
2. Заполните `.env` (см. пример в `.env.example`)
3. Запустите бота:
   ```sh
   make run-local
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
- [ ] Sprint 3: Price anomaly alerts, daily Syrve CSV sync

---

### Running tests

Activate your virtual environment if needed:

```sh
source venv/bin/activate
```

Run all tests:

```sh
PYTHONPATH=. pytest
```

Or run a specific test (e.g. alias flow):

```sh
PYTHONPATH=. pytest tests/test_alias_flow.py
```

This will run all unit tests and check that the alias self-learning mechanism works as expected.

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