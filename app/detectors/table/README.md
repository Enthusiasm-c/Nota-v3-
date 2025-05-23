# Модуль детекции таблиц

Этот модуль предназначен для обнаружения таблиц и ячеек на изображениях накладных, используя PP-Structure от PaddleOCR.

## Установка зависимостей

```bash
# Установка PaddleOCR и зависимостей
pip install paddlepaddle
pip install "paddleocr>=2.6.0.3"
```

## Использование

### В коде

```python
from app.detectors.table.factory import get_detector

# Получаем детектор таблиц
detector = get_detector()  # по умолчанию 'paddle'

# Загружаем изображение
with open("path/to/invoice.jpg", "rb") as f:
    image_bytes = f.read()

# Детектируем таблицы
result = detector.detect(image_bytes)
tables = result.get('tables', [])
print(f"Обнаружено таблиц: {len(tables)}")

# Извлекаем ячейки для дальнейшей обработки
cells = detector.extract_cells(image_bytes)
print(f"Извлечено ячеек: {len(cells)}")
```

### Тестирование через CLI

Для тестирования модуля на отдельных изображениях используйте скрипт `tools/test_table_detector.py`:

```bash
python tools/test_table_detector.py --image путь/к/накладной.jpg --output результат.jpg
```

Параметры:
- `--image` или `-i`: путь к тестовому изображению (обязательный)
- `--output` или `-o`: путь для сохранения визуализации (опциональный)
- `--method` или `-m`: метод детекции ('paddle', по умолчанию)

## Интеграция с OCR-пайплайном

Для интеграции детектора таблиц в OCR-пайплайн используйте следующий код:

```python
from app.detectors.table.factory import get_detector
from app.ocr import call_openai_ocr

async def process_invoice_with_table_detection(image_bytes):
    # Инициализируем детектор
    detector = get_detector()

    # Извлекаем ячейки таблицы
    cells = detector.extract_cells(image_bytes)

    # Обрабатываем каждую ячейку через OCR
    results = []
    for cell in cells:
        # Извлекаем изображение ячейки (в будущей реализации)
        # cell_image = cell.get('image')

        # Обрабатываем через OCR (пока используем bbox)
        # cell_result = await call_openai_ocr(cell_image)

        # Сохраняем результат с координатами
        # results.append({
        #    'bbox': cell.get('bbox'),
        #    'text': cell_result
        # })

    return results
```

## Расширение

Для добавления новых методов детекции:

1. Создайте новый класс-наследник от `TableDetector`
2. Реализуйте методы `detect()` и `extract_cells()`
3. Добавьте новый метод в фабрику `get_detector()`
