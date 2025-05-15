#!/bin/bash
# Скрипт для запуска тестов с покрытием

# Активируем виртуальное окружение
. .venv/bin/activate

# Измерение текущего покрытия для сравнения
echo "Measuring current coverage..."
python -m pytest --cov=app --cov-report=term-missing > current_coverage.log

# Запуск всех юнит-тестов и генерация отчета о покрытии
echo "Running unit tests with coverage..."
python -m pytest tests/unit/ -v --cov=app --cov-report=html:unit_coverage

# Запуск конкретных модулей для целевого улучшения покрытия
echo "Running targeted tests for specific modules..."
python -m pytest tests/unit/test_ocr.py -v
python -m pytest tests/unit/test_postprocessing.py -v
python -m pytest tests/unit/test_matcher.py -v
python -m pytest tests/unit/test_ocr_pipeline.py -v

# Создание финального отчета о покрытии
echo "Generating final coverage report..."
python -m pytest --cov=app --cov-report=html

# Вывод сумарного покрытия
coverage report

echo "Testing completed."