# Nota-v3 Telegram Bot

## Описание

Telegram-бот для автоматической проверки товарных накладных:
- Принимает фото накладной
- Распознаёт позиции через OpenAI Vision (gpt-4o)
- Сверяет с CSV-базой поставщиков и продуктов
- Формирует отчёт в MarkdownV2
- Отвечает пользователю в Telegram

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