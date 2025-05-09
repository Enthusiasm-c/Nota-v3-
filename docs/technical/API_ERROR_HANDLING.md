# Обработка ошибок API

Документ описывает стандартизированный подход к обработке ошибок API в Nota-v3.

---

## Основные моменты
- Декораторы для повторов с экспоненциальной задержкой
- Классификация ошибок (TIMEOUT, RATE_LIMIT, VALIDATION, AUTHENTICATION и др.)
- Пользовательские сообщения об ошибках
- Прогресс-бар для многоэтапных операций

## Примеры использования

**Синхронный вызов с повтором:**
```python
from app.utils.api_decorators import with_retry_backoff

@with_retry_backoff(max_retries=3, initial_backoff=1.0, backoff_factor=2.0)
def call_ocr_api(image_bytes):
    ...
```

**Асинхронный вызов с повтором:**
```python
from app.utils.api_decorators import with_async_retry_backoff

@with_async_retry_backoff(max_retries=2, initial_backoff=1.0, backoff_factor=2.0)
async def send_message_to_assistant(thread_id, message):
    ...
```

**Многоэтапная операция с прогрессом:**
```python
from app.utils.api_decorators import with_progress_stages, update_stage

STAGES = { ... }

@with_progress_stages(stages=STAGES)
async def process_invoice(image, **kwargs):
    ...
```

## Классификация ошибок

| Категория      | Примеры                    | Поведение по умолчанию        |
|---------------|----------------------------|------------------------------|
| TIMEOUT       | Таймауты                   | Повтор с задержкой           |
| RATE_LIMIT    | Превышение лимита          | Экспоненциальный повтор      |
| VALIDATION    | Неверный формат            | Не повторять                 |
| AUTHENTICATION| Неверный ключ              | Не повторять                 |
| SERVER        | 5xx ошибки                 | Повтор с задержкой           |
| CLIENT        | 4xx ошибки                 | Зависит от ошибки            |
| NETWORK       | Проблемы с сетью           | Повтор с задержкой           |
| UNKNOWN       | Неожиданные ошибки         | Повторить один раз           |

## Преимущества
- Единообразие обработки ошибок по всему проекту
- Повышение стабильности за счет повторов
- Дружелюбные сообщения для пользователя
- Централизованная логика — проще поддерживать
