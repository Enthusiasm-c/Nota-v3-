# Юнит-тесты

В этой директории находятся юнит-тесты для приложения. Юнит-тесты предназначены для проверки отдельных функций и компонентов в изоляции от других частей приложения.

## Структура тестов

Каждый файл тестов соответствует модулю в приложении:

- `test_ocr.py` - тесты для модуля OCR (app/ocr.py)
- `test_postprocessing.py` - тесты для модуля постобработки данных (app/postprocessing.py)
- `test_matcher.py` - тесты для модуля сопоставления (app/matcher.py)
- `test_ocr_pipeline.py` - тесты для OCR пайплайна (app/ocr_pipeline.py)

## Запуск тестов

Запустить все юнит-тесты:
```bash
pytest tests/unit/
```

Запустить конкретный тест:
```bash
pytest tests/unit/test_ocr.py::test_direct_vision_api
```

Запустить тесты с отчетом о покрытии:
```bash
pytest tests/unit/ --cov=app --cov-report=html
```

## Принципы юнит-тестирования

1. **Изоляция** - каждый тест должен быть независим, используя моки для внешних зависимостей
2. **Покрытие** - тесты должны покрывать все ветви кода, включая обработку ошибок
3. **Быстрота** - юнит-тесты должны выполняться быстро
4. **Повторяемость** - каждый запуск теста должен давать одинаковый результат
5. **Нейминг** - названия тестов должны четко описывать, что именно тестируется

## Моки и фикстуры

Для изоляции тестов используются моки и фикстуры, определенные в `conftest.py`. Это позволяет не обращаться к внешним сервисам (OpenAI API, Redis, и т.д.) во время тестирования.

## Покрытие кода

Текущее покрытие кода юнит-тестами:
- `app/ocr.py` - 76%
- `app/postprocessing.py` - 74%
- `app/matcher.py` - 65%
- `app/ocr_pipeline.py` - 11%

Цель: достичь минимум 75% покрытия для всех модулей.

## Добавление новых тестов

При создании новых тестов следуйте этим рекомендациям:

1. Называйте функции тестов с префиксом `test_`
2. Группируйте связанные тесты в классы с префиксом `Test`
3. Используйте параметризацию для тестирования разных входных данных
4. Добавляйте явные ассерты с сообщениями об ошибках
5. Мокайте все внешние зависимости

Пример:
```python
@pytest.mark.parametrize("input_value, expected", [
    ("10,000", 10000),
    ("10.000", 10000),
    (None, None)
])
def test_clean_num(input_value, expected):
    """Тест функции clean_num для разных форматов чисел"""
    result = postprocessing.clean_num(input_value)
    assert result == expected, f"clean_num({input_value}) должно быть {expected}, но получено {result}"
```
