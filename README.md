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

**Новая логика редактирования инвойсов:**
- Все редактирование теперь происходит через одну основную кнопку "✏️ Редактировать".
- Для исправления ошибок или внесения изменений пользователь пишет свободный текст (например: `строка 2 цена 90000` или `дата — 26 апреля`).
- **Больше нет инлайн-кнопок для каждой строки**: все старые per-line inline edit-кнопки полностью удалены из кода и интерфейса.
- После нажатия "Редактировать" бот ожидает свободный ввод с инструкцией и примерами.
- После любого изменения бот пересчитывает ошибки и обновляет отчёт. Если ошибок больше нет — появляется кнопка подтверждения.
- Все сценарии (исправление, удаление, добавление строки) поддерживаются через свободный ввод.

**Фаззи-подсказки названий продуктов:**
- При вводе нераспознанного имени продукта (например "строка 2 name aple") бот автоматически ищет ближайшее совпадение в базе продуктов.
- Если найдено совпадение с порогом ≥82%, бот предлагает вариант: "Наверное, вы имели в виду "Apple"? ✓ Да | ✗ Нет"
- При подтверждении (✓ Да) продукт автоматически сопоставляется и сохраняется в aliases.csv для дальнейшего использования.
- При отклонении (✗ Нет) используется оригинальное введенное название.

**Преимущества:**
- Интерфейс стал чище и быстрее: нет лишних кнопок, всё делается одной командой.
- Удобно для мобильных пользователей: не нужно искать нужную кнопку для каждой строки.
- Логика ошибок и подтверждения стала прозрачнее: всегда виден актуальный статус инвойса.
- Интеллектуальные подсказки имен продуктов ускоряют работу и уменьшают опечатки.
- Система самообучения автоматически пополняет базу алиасов для будущего использования.

**Тесты:**
- Все сценарии редактирования покрыты автотестами: изменение даты, редактирование и удаление строк, добавление новых позиций.
- Добавлены тесты для проверки новой клавиатуры с 2-3 кнопками (test_keyboard_main_edit.py).
- Добавлены тесты для проверки фаззи-подсказок и механизма подтверждения (test_fuzzy_confirm.py).
- После изменений все тесты проходят и подтверждают отсутствие старого поведения с инлайн-кнопками.

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
│   ├── formatter.py      # отчёт
│   └── keyboards.py      # placeholder
├── data/
│   ├── suppliers.csv
│   └── products.csv
├── requirements.in / requirements.txt
├── .env.example
├── Makefile
└── tests/
```

## Переменные окружения

- `BOT_TOKEN` — токен Telegram-бота
- `OPENAI_API_KEY` — ключ OpenAI
- `OPENAI_MODEL` — модель (по умолчанию gpt-4o)
- `MATCH_THRESHOLD` — порог fuzzy-сопоставления (default: 0.75)

## CI

GitHub Actions: `.github/workflows/ci.yml` — тесты и линт при push/pull_request
Nota-v3-