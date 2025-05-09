# Улучшения OCR-модуля для индонезийских накладных

## Реализованные компоненты

1. **Детектор таблицы (PP-Structure)**
   - Модуль: `app/detectors/table`
   - Функциональность: Обнаружение таблиц и извлечение ячеек
   - Тесты: `tests/test_table_detector.py`
   - Тестовый инструмент: `tools/test_table_detector.py`

2. **Арифметический валидатор**
   - Модуль: `app/validators/arithmetic.py`
   - Функциональность: Проверка арифметических соотношений и автокоррекция ошибок
   - Тесты: `tests/test_arithmetic_validator.py`
   - Тестовый инструмент: `tools/test_arithmetic_validator.py`

3. **Доменный валидатор (sanity-правила)**
   - Модуль: `app/validators/sanity.py`
   - Функциональность: Проверка бизнес-логики и соответствия доменным правилам
   - Тесты: `tests/test_sanity_validator.py`
   - Тестовый инструмент: `tools/test_sanity_validator.py`

4. **Валидационный пайплайн**
   - Модуль: `app/validators/pipeline.py`
   - Функциональность: Объединение всех валидаторов в один процесс
   - Тесты: `tests/test_validation_pipeline.py`
   - Тестовый инструмент: `tools/test_validation_pipeline.py`

5. **Полный OCR-пайплайн**
   - Модуль: `app/ocr_pipeline.py`
   - Функциональность: Интеграция детекции таблиц, OCR и валидации
   - Тестовый инструмент: `tools/test_ocr_pipeline.py`

## Автокоррекция ошибок

Реализованы следующие механизмы автокоррекции:

1. **Потерянный ноль в цене (PRICE_ZERO_LOST)**
   - Когда: `price < 100 000` и `amount/qty > 100 000`
   - Исправление: `price *= 10`

2. **Лишний ноль в цене (PRICE_EXTRA_ZERO)**
   - Когда: `price > 1000` и `amount/qty < price/10`
   - Исправление: `price /= 10`

3. **Дробные значения в количестве (QTY_DECIMAL_MISSED)**
   - Когда: `qty > 10` и `amount/price < qty/10`
   - Исправление: `qty /= 10`

4. **Несоответствие единиц измерения (UNIT_MISMATCH)**
   - Когда: Штучный товар указан в весовых единицах
   - Исправление: Автозамена на правильную единицу измерения

## Валидация и проверки

1. **Арифметическая валидация**
   - Проверка соотношения: `qty * price = amount`
   - Допустимая погрешность: 1% (настраиваемо)

2. **Доменные правила**
   - Проверка соответствия единиц измерения товарам
   - Проверка диапазонов цен для категорий
   - Проверка диапазонов весов для весовых товаров

## Как использовать

### Детектор таблиц

```bash
python tools/test_table_detector.py --image путь/к/изображению.jpg --output результат.jpg --cells-dir ячейки/
```

### Арифметический валидатор

```bash
python tools/test_arithmetic_validator.py --input путь/к/данным.json --output результат.json
```

### Валидатор бизнес-правил

```bash
python tools/test_sanity_validator.py --input путь/к/данным.json --output результат.json --strict
```

### Полный валидационный пайплайн

```bash
python tools/test_validation_pipeline.py --input путь/к/данным.json --output результат.json
```

### Полный OCR-пайплайн

```bash
python tools/test_ocr_pipeline.py --image путь/к/изображению.jpg --output результат.json --lang id,en
```

## Необходимые зависимости

- `paddlepaddle` - ядро Paddle
- `paddleocr>=2.6.0.3` - детектор таблиц и OCR
- Остальные базовые зависимости проекта

## Метрики

Система предоставляет следующие метрики:

- **Accuracy** - процент корректно распознанных и валидных строк
- **Auto Fixed Count** - количество автоматически исправленных проблем
- **Issues Count** - общее количество обнаруженных проблем
- **Lines With Issues** - количество строк с проблемами

## Интеграция с основным приложением

Для интеграции с основным приложением используйте класс `OCRPipeline`:

```python
from app.ocr_pipeline import OCRPipeline

# Создаем экземпляр с настройками
pipeline = OCRPipeline(
    table_detector_method="paddle",
    arithmetic_max_error=1.0,
    strict_validation=False
)

# Обрабатываем изображение
with open("invoice.jpg", "rb") as f:
    image_bytes = f.read()
    
result = await pipeline.process_image(image_bytes, lang=["id", "en"])

# Результат содержит распознанные строки, проблемы и метаданные
print(f"Accuracy: {result['accuracy']}")
print(f"Lines: {len(result['lines'])}")
print(f"Issues: {len(result['issues'])}")
``` 