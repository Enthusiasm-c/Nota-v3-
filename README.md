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

## Тесты

```sh
make test
```

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