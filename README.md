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