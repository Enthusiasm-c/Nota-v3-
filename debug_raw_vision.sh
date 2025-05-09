#!/bin/bash

# Скрипт для тестирования сырого распознавания текста (без обработки JSON)

# Проверяем наличие параметра с путем изображения
if [ -z "$1" ]; then
    echo "Ошибка: не указан путь к изображению"
    echo "Использование: $0 <путь_к_изображению>"
    exit 1
fi

# Путь к изображению
IMAGE_PATH="$1"

# Проверяем существование файла
if [ ! -f "$IMAGE_PATH" ]; then
    echo "Ошибка: файл $IMAGE_PATH не найден"
    exit 1
fi

# Создаем временную метку для уникальных имен файлов
TIMESTAMP=$(date +%s)

# 1. Первый запуск - с предобработкой
echo "======================================================"
echo "ЗАПУСК РАСПОЗНАВАНИЯ С ПРЕДОБРАБОТКОЙ ИЗОБРАЖЕНИЯ"
echo "======================================================"
python3 debug_ocr.py -i "$IMAGE_PATH" -r

# Сохраняем результат первого запуска
EXIT_CODE1=$?
if [ $EXIT_CODE1 -eq 0 ]; then
    # Переименовываем файл результата для удобства
    LAST_RESULT=$(ls -t raw_vision_result_*.txt | head -1)
    if [ -n "$LAST_RESULT" ]; then
        mv "$LAST_RESULT" "raw_vision_with_preproc_${TIMESTAMP}.txt"
        echo "✅ Результат с предобработкой: raw_vision_with_preproc_${TIMESTAMP}.txt"
    fi
else
    echo "❌ Ошибка при распознавании с предобработкой (код $EXIT_CODE1)"
fi

# 2. Второй запуск - без предобработки
echo ""
echo "======================================================"
echo "ЗАПУСК РАСПОЗНАВАНИЯ БЕЗ ПРЕДОБРАБОТКИ ИЗОБРАЖЕНИЯ"
echo "======================================================"
python3 debug_ocr.py -i "$IMAGE_PATH" -r -n

# Сохраняем результат второго запуска
EXIT_CODE2=$?
if [ $EXIT_CODE2 -eq 0 ]; then
    # Переименовываем файл результата для удобства
    LAST_RESULT=$(ls -t raw_vision_result_*.txt | head -1)
    if [ -n "$LAST_RESULT" ]; then
        mv "$LAST_RESULT" "raw_vision_no_preproc_${TIMESTAMP}.txt"
        echo "✅ Результат без предобработки: raw_vision_no_preproc_${TIMESTAMP}.txt"
    fi
else
    echo "❌ Ошибка при распознавании без предобработки (код $EXIT_CODE2)"
fi

# 3. Сравнение файлов (если оба запуска успешны)
if [ $EXIT_CODE1 -eq 0 ] && [ $EXIT_CODE2 -eq 0 ]; then
    echo ""
    echo "======================================================"
    echo "СРАВНЕНИЕ РЕЗУЛЬТАТОВ"
    echo "======================================================"
    echo "Сравниваю результаты распознавания (с предобработкой и без):"
    echo "  - raw_vision_with_preproc_${TIMESTAMP}.txt"
    echo "  - raw_vision_no_preproc_${TIMESTAMP}.txt"
    echo ""
    echo "Вы можете сравнить файлы с помощью команды:"
    echo "diff raw_vision_with_preproc_${TIMESTAMP}.txt raw_vision_no_preproc_${TIMESTAMP}.txt"
fi

# Выходим с успешным кодом, если хотя бы один режим сработал успешно
if [ $EXIT_CODE1 -eq 0 ] || [ $EXIT_CODE2 -eq 0 ]; then
    exit 0
else
    exit 1
fi 