# Руководство разработчика Nota-v3

## Введение

Это руководство предназначено для разработчиков, работающих над проектом Nota-v3. Здесь вы найдёте информацию о настройке окружения, архитектуре проекта и различных компонентах системы.

## Содержание

- [Установка и настройка](#установка-и-настройка)
- [Структура проекта](#структура-проекта)
- [Тестирование](#тестирование)
- [Деплой](#деплой)
- [Стиль кода](#стиль-кода)

## Установка и настройка

### Требования

- Python 3.10 или выше
- pip и virtualenv/venv

### Шаги по установке

1. Клонируйте репозиторий:
```sh
git clone <repository-url>
cd nota-v3
```
2. Создайте виртуальное окружение:
```sh
python -m venv venv
source venv/bin/activate  # для Linux/macOS
# или .\venv\Scripts\activate  # для Windows
```
3. Установите зависимости:
```sh
pip install -r requirements.txt
```
4. Настройте переменные окружения:
```sh
cp .env.example .env
# Отредактируйте .env файл, заполнив необходимые переменные
```

### Переменные окружения
- `BOT_TOKEN` — токен Telegram-бота
- `OPENAI_API_KEY` — ключ OpenAI для OCR (Vision API)
- `OPENAI_ASSISTANT_ID` — ID Assistant для GPT-3.5-turbo (редактирование)
- `OPENAI_MODEL` — модель для OCR (по умолчанию gpt-4o)
- `MATCH_THRESHOLD` — порог fuzzy-сопоставления (default: 0.75)

## Структура проекта

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
├── requirements.in / requirements.txt
├── .env.example
├── Makefile
└── tests/                # автотесты
```

## Тестирование

Проект использует pytest для тестирования. Чтобы запустить тесты:
```sh
# Активируйте виртуальное окружение если необходимо
# source venv/bin/activate

# Запустить все тесты
PYTHONPATH=. pytest

# Или запустить конкретный тест
PYTHONPATH=. pytest tests/test_alias_flow.py
```

### Особенности тестирования OCR
1. **Stub mode** (по умолчанию): Без запросов к OpenAI, работает оффлайн, быстрые тесты.
2. **Live mode**: Установите `USE_OPENAI_OCR=1` и укажите `OPENAI_API_KEY` для использования GPT-4o Vision.

Подробный план тестирования представлен в [TEST_PLAN.md](../technical/TEST_PLAN.md).

## Деплой

Проект настроен для деплоя на Linux-сервер с использованием systemd.

### Производственный запуск
1. Установите зависимости на сервере
2. Настройте systemd сервис используя `nota-bot.service.override.conf`
3. Запустите и включите сервис
```sh
systemctl start nota-bot
systemctl enable nota-bot
```

### Мониторинг
Логи доступны через journalctl:
```sh
journalctl -u nota-bot -f
```

## Стиль кода
Проект следует PEP 8 с некоторыми особенностями:
- Используйте snake_case для переменных и функций
- Максимальная длина строки — 100 символов
- Используйте типизацию в новом коде
- Документируйте все публичные функции и классы
