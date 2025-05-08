#!/bin/bash

# Скрипт для тестирования сырого распознавания текста (без обработки JSON)

# Проверяем наличие параметра с путем изображения
if [ -z "$1" ]; then
    echo "Ошибка: не указан путь к изображению"
    echo "Использование: $0 <путь_к_изображению> [--no-preprocessing]"
    exit 1
fi

# Путь к изображению
IMAGE_PATH="$1"

# Проверяем флаг предобработки
if [ "$2" == "--no-preprocessing" ]; then
    NO_PREPROCESSING="-n"
    echo "Режим: Без предобработки изображения"
else
    NO_PREPROCESSING=""
    echo "Режим: С предобработкой изображения"
fi

# Проверяем существование файла
if [ ! -f "$IMAGE_PATH" ]; then
    echo "Ошибка: файл $IMAGE_PATH не найден"
    exit 1
fi

echo "Запуск распознавания сырого текста для изображения: $IMAGE_PATH"

# Запускаем скрипт debug_ocr.py с флагом -r (raw_vision)
python3 debug_ocr.py -i "$IMAGE_PATH" -r $NO_PREPROCESSING

# Сохраняем результат и выходим
EXIT_CODE=$?
if [ $EXIT_CODE -eq 0 ]; then
    echo "Распознавание успешно завершено. Результат сохранен в файл raw_vision_result_*.txt"
else
    echo "Ошибка при распознавании текста (код $EXIT_CODE)"
fi

exit $EXIT_CODE 