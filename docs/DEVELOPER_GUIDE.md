# Руководство разработчика Nota AI

## Введение

Данное руководство предназначено для разработчиков, присоединяющихся к проекту Nota AI. Оно содержит подробное описание ключевых компонентов системы, рабочих процессов и соглашений по написанию кода.

## Установка среды разработки

### Требования

- Python 3.10+
- Redis
- Git
- OpenCV (для обработки изображений)
- Pillow (для обработки изображений)
- OpenAI API ключ

### Первоначальная настройка

1. Клонирование репозитория:
   ```bash
   git clone https://github.com/username/Nota-v3-.git
   cd Nota-v3-
   ```

2. Создание виртуального окружения:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/macOS
   venv\Scripts\activate     # Windows
   ```

3. Установка зависимостей:
   ```bash
   pip install -r requirements.txt
   ```

4. Создание файла .env с переменными окружения:
   ```
   OPENAI_OCR_KEY=sk-...
   OPENAI_CHAT_KEY=sk-...
   OPENAI_ASSISTANT_ID=asst_...
   TELEGRAM_TOKEN=...
   SYRVE_API_URL=https://api.syrve.com
   SYRVE_LOGIN=api_user
   SYRVE_PASSWORD=...
   SYRVE_CONCEPTION_ID=...
   SYRVE_STORE_ID=...
   SYRVE_DEFAULT_SUPPLIER_ID=...
   ```

5. Запуск тестов для проверки корректности настройки:
   ```bash
   pytest -v
   ```

## Структура проекта и модули

### Основные пакеты и их назначение

#### app/assistants/

Отвечает за взаимодействие с OpenAI API для обработки команд и распознавания документов.

- **client.py**: Основной клиент для работы с Assistant API
- **thread_pool.py**: Управление пулом потоков для ускорения работы
- **intent_adapter.py**: Преобразование ответов в структурированный формат
- **trace_openai.py**: Трассировка запросов к OpenAI для отладки

Ключевые функции:
- `run_thread_safe_async()`: Асинхронная обработка команды пользователя
- `parse_assistant_output()`: Парсинг структурированного ответа от ассистента

#### app/edit/

Отвечает за логику редактирования инвойса.

- **apply_intent.py**: Применение команд редактирования
- **free_parser.py**: Парсер свободных команд пользователя

Ключевые функции:
- `apply_intent()`: Применяет команду к данным инвойса
- `set_price()`, `set_name()`, `set_date()`: Редактирование конкретных полей

#### app/formatters/

Форматирование отчетов и данных для отображения.

- **report.py**: Построение отчетов об инвойсах

Ключевые функции:
- `build_report()`: Создает отчет с подсветкой ошибок и форматированием

#### app/fsm/

Управление состояниями диалога.

- **states.py**: Классы состояний для конечных автоматов

Ключевые классы:
- `NotaStates`: Основные состояния работы бота
- `EditFree`: Состояния для свободного редактирования

#### app/handlers/

Обработчики сообщений и действий пользователя.

- **edit_flow.py**: Обработка команд редактирования
- **incremental_photo_handler.py**: Обработка фотографий с прогрессивным UI
- **name_picker.py**: Обработка подсказок для неопознанных позиций
- **syrve_handler.py**: Интеграция с Syrve API

#### app/i18n/

Система локализации.

- **__init__.py**: Функции для работы с переводами
- **texts_en.yaml**: Английские строки интерфейса

Ключевые функции:
- `t(key, lang)`: Получение локализованной строки

#### app/imgprep/

Подготовка изображений для OCR.

- **prepare.py**: Функции предобработки изображений

Ключевые функции:
- `prepare_for_ocr()`: Основная функция предобработки
- `detect_and_align_document()`: Выравнивание документа
- `apply_clahe_and_denoise()`: Улучшение качества изображения

#### app/utils/

Вспомогательные утилиты.

- **api_decorators.py**: Декораторы для работы с API
- **redis_cache.py**: Работа с кэшем Redis
- **monitor.py**: Сбор метрик
- **incremental_ui.py**: Постепенное обновление сообщений

## Рабочие процессы

### Обработка фотографии инвойса

1. **Загрузка фото**:
   - Пользователь отправляет фото в чат
   - Входная точка: `incremental_photo_handler.py::photo_handler_incremental()`

2. **Предобработка**:
   - Сохранение изображения во временный файл
   - Обработка через `imgprep/prepare.py::prepare_for_ocr()`
   - Результат: оптимизированное изображение для OCR

3. **OCR**:
   - Отправка изображения на распознавание через OCR API
   - Функция: `ocr.py::call_openai_ocr()`
   - Результат: структурированные данные инвойса

4. **Сопоставление**:
   - Сопоставление распознанных позиций с каталогом продуктов
   - Функция: `matcher.py::match_positions()`
   - Результат: список позиций со статусами (`ok`, `unknown`, `unit_mismatch`)

5. **Формирование отчета**:
   - Создание отчета для пользователя
   - Функция: `formatters/report.py::build_report()`
   - Результат: форматированный текст отчета

6. **Отправка отчета**:
   - Отправка отчета пользователю с кнопками для действий
   - Функция: `incremental_photo_handler.py::ui.complete()`

### Редактирование инвойса

1. **Запрос на редактирование**:
   - Пользователь нажимает кнопку "Редактировать"
   - Входная точка: `edit_flow.py::handle_edit_free()`

2. **Ввод команды**:
   - Пользователь вводит текстовую команду (напр. "строка 2 цена 100")
   - Входная точка: `edit_flow.py::handle_free_edit_text()`

3. **Обработка команды**:
   - Отправка текста ассистенту для распознавания намерения
   - Функция: `assistants/client.py::run_thread_safe_async()`
   - Результат: структурированный intent с действием

4. **Применение изменений**:
   - Применение изменений к данным инвойса
   - Функция: `edit/apply_intent.py::apply_intent()`
   - Результат: обновленный инвойс

5. **Проверка и отображение**:
   - Перепроверка сопоставления и формирование отчета
   - Отправка обновленного отчета пользователю

### Работа с неопознанными позициями

1. **Обнаружение неопознанной позиции**:
   - При статусе `unknown` в результатах сопоставления
   - Функция: `edit_flow.py::handle_free_edit_text()` (после сопоставления)

2. **Поиск похожих позиций**:
   - Нечеткий поиск в каталоге с порогом 75%
   - Функция: `matcher.py::fuzzy_find()`
   - Результат: список ближайших совпадений

3. **Отображение подсказки**:
   - Создание inline-клавиатуры с вариантами
   - Функция: `name_picker.py::show_fuzzy_suggestions()`

4. **Обработка выбора**:
   - Пользователь выбирает подходящее название
   - Входная точка: `name_picker.py::handle_pick_name()`
   - Результат: обновление инвойса и переиндексация

### Отправка в Syrve

1. **Подтверждение инвойса**:
   - Пользователь нажимает "Подтвердить"
   - Входная точка: `syrve_handler.py::handle_invoice_confirm()`

2. **Генерация XML**:
   - Подготовка данных в формате для Syrve
   - Функция: `syrve_client.py::generate_invoice_xml()`
   - Результат: XML-документ для импорта

3. **Авторизация в Syrve**:
   - Получение токена авторизации
   - Функция: `syrve_client.py::auth()`
   - Результат: токен для API-запросов

4. **Отправка данных**:
   - Импорт накладной в Syrve
   - Функция: `syrve_client.py::import_invoice()`
   - Результат: статус операции от API

5. **Обработка результата**:
   - Отображение результата пользователю
   - Обновление метрик и логирование

## Работа с системой локализации

### Использование функции t()

Все строки пользовательского интерфейса должны использовать функцию `t()` для поддержки локализации:

```python
from app.i18n import t

# Базовое использование
message = t("button.confirm", lang="en")  # "✅ Confirm"

# С параметрами
message = t("status.edit_success", {"field": "price"}, lang="en")  # "The price has been successfully changed!"
```

### Структура ключей

Ключи организованы в иерархическую структуру:
- `button.*` - тексты кнопок
- `status.*` - статусные сообщения
- `error.*` - сообщения об ошибках
- `report.*` - сообщения в отчетах
- `suggestion.*` - тексты подсказок
- `example.*` - примеры команд
- `welcome.*` - приветственные сообщения

### Добавление новых строк

1. Добавьте строку в `app/i18n/texts_en.yaml`
2. Используйте новый ключ в коде с функцией `t()`

## Система обработки изображений

### Процесс предобработки

Полный процесс предобработки включает:

1. **Проверка размера**:
   ```python
   if max(h, w) > 1600 or len(img_bytes) > 2 * 1024 * 1024:
       img = resize_if_needed(img)
   ```

2. **Детекция и выравнивание**:
   ```python
   aligned_img = detect_and_align_document(img)
   if aligned_img is not None:
       img = aligned_img
   ```

3. **Улучшение контраста**:
   ```python
   enhanced_img = apply_clahe_and_denoise(img)
   ```

4. **Бинаризация и морфология**:
   ```python
   binary_img = apply_threshold_and_morph(enhanced_img)
   ```

5. **Сохранение**:
   ```python
   processed_bytes = save_to_webp(binary_img)
   ```

### Настройка параметров

Ключевые параметры предобработки:
- `max_size` - максимальный размер стороны изображения (1600px)
- `clipLimit` - лимит контрастности для CLAHE (автоматический)
- `quality` - качество сжатия WebP (90%)
- `max_size_kb` - максимальный размер результата в KB (200KB)

## Обработка ошибок и мониторинг

### Декораторы для API

Для надежной работы с внешними API используйте декораторы из `app/utils/api_decorators.py`:

```python
@with_retry_backoff(max_retries=2, initial_backoff=1.0, backoff_factor=2.0)
async def call_external_api():
    # Код, который может завершиться ошибкой
    pass
```

### Метрики и мониторинг

Для отслеживания производительности используйте функции из `app/utils/monitor.py`:

```python
# Счетчики
increment_counter("nota_invoices_total", {"status": "ok"})

# Гистограммы
record_histogram("nota_ocr_latency_ms", latency_ms)
```

### Логирование

Используйте стандартный модуль logging с правильным контекстом:

```python
logger.info("Processing invoice", extra={"data": {"invoice_id": invoice_id}})
logger.error("API error", extra={"data": {"error": str(e), "status_code": response.status_code}})
```

## Соглашения по коду

### Стиль кода

- Следуйте стандарту PEP 8
- Используйте snake_case для функций и переменных
- Используйте CamelCase для классов
- Максимальная длина строки: 88 символов (как в black)

### Типизация

Используйте аннотации типов для улучшения читаемости и предотвращения ошибок:

```python
def process_data(data: Dict[str, Any], options: Optional[List[str]] = None) -> ParsedData:
    # ...
```

### Тестирование

Пишите тесты для всех новых функций:

```python
def test_function_name():
    # Подготовка
    input_data = ...
    expected_output = ...
    
    # Выполнение
    result = function_name(input_data)
    
    # Проверка
    assert result == expected_output
```

### Документация

Документируйте функции и классы в формате Google Style DocStrings:

```python
def function_name(param1: str, param2: int) -> bool:
    """
    Краткое описание функции.
    
    Args:
        param1: Описание первого параметра
        param2: Описание второго параметра
        
    Returns:
        Описание возвращаемого значения
        
    Raises:
        ValueError: Когда случается ошибка валидации
    """
```

## Советы по отладке

### Отладка OpenAI API

Для отладки запросов к OpenAI используйте трассировку:

```python
import os
os.environ["OPENAI_LOG"] = "debug"
```

### Тестирование обработки изображений

Для тестирования предобработки изображений:

```python
from app.imgprep import prepare_for_ocr
from PIL import Image
import numpy as np
import cv2

# Загрузка изображения
img = Image.open("path/to/image.jpg")
img_np = np.array(img)

# Поэтапная обработка
aligned = detect_and_align_document(img_np)
enhanced = apply_clahe_and_denoise(aligned if aligned is not None else img_np)
binary = apply_threshold_and_morph(enhanced)

# Сохранение результатов для проверки
cv2.imwrite("aligned.jpg", cv2.cvtColor(aligned, cv2.COLOR_RGB2BGR))
cv2.imwrite("enhanced.jpg", enhanced)
cv2.imwrite("binary.jpg", binary)
```

### Тестирование интеграции с Syrve

Для тестирования интеграции без фактической отправки:

```python
# Создайте файл XML
xml = await generate_invoice_xml(invoice_data, openai_client)
with open("test_invoice.xml", "w") as f:
    f.write(xml)

# Проверьте валидность XML
import xml.etree.ElementTree as ET
tree = ET.parse("test_invoice.xml")
root = tree.getroot()
```

## Заключение

Данное руководство охватывает основные аспекты разработки проекта Nota AI. При возникновении вопросов обращайтесь к более опытным членам команды или к документации соответствующих библиотек и API.

Дополнительные ресурсы:
- [Официальная документация OpenAI](https://platform.openai.com/docs/guides/vision)
- [Документация aiogram](https://docs.aiogram.dev/)
- [Документация Syrve API](https://api.syrve.com/docs)
- [Справочник по OpenCV](https://docs.opencv.org/)