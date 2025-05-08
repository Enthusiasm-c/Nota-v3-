#!/bin/bash

# Скрипт для запуска подробной пошаговой диагностики процесса OCR

# Проверяем наличие параметра с путем изображения
if [ -z "$1" ]; then
    echo "Ошибка: не указан путь к изображению"
    echo "Использование: $0 <путь_к_изображению> [--skip-preprocessing]"
    exit 1
fi

# Путь к изображению
IMAGE_PATH="$1"

# Проверяем параметр предобработки
PREPROC_FLAG=""
if [ "$2" == "--skip-preprocessing" ]; then
    PREPROC_FLAG="-s"
    echo "Режим: Без предобработки изображения"
else
    echo "Режим: С предобработкой изображения"
fi

# Проверяем существование файла
if [ ! -f "$IMAGE_PATH" ]; then
    echo "Ошибка: файл $IMAGE_PATH не найден"
    exit 1
fi

# Создаем директорию для сохранения результатов
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DEBUG_DIR="debug_ocr_${TIMESTAMP}"
mkdir -p "$DEBUG_DIR"

# Сохраняем информацию о системе
echo "Сохраняем информацию о системе..."
(
    echo "ИНФОРМАЦИЯ О СИСТЕМЕ"
    echo "===================="
    echo "Дата и время: $(date)"
    echo "Версия OS: $(uname -a)"
    echo "Python: $(python3 --version)"
    echo "Директория: $(pwd)"
    echo "===================="
    echo ""
    
    echo "ИНФОРМАЦИЯ ОБ ИЗОБРАЖЕНИИ"
    echo "===================="
    echo "Путь: $IMAGE_PATH"
    echo "Размер: $(ls -lh "$IMAGE_PATH" | awk '{print $5}')"
    file "$IMAGE_PATH"
    echo "===================="
) > "$DEBUG_DIR/system_info.txt"

echo "Запуск подробной диагностики для изображения: $IMAGE_PATH"
echo "Результаты будут сохранены в: $DEBUG_DIR"

# Запускаем скрипт с подробными логами
python3 debug_ocr_detailed.py -i "$IMAGE_PATH" $PREPROC_FLAG -d "$DEBUG_DIR" | tee "$DEBUG_DIR/debug_log.txt"

# Анализируем результат
EXIT_CODE=$?
if [ $EXIT_CODE -eq 0 ]; then
    echo "Диагностика успешно завершена"
    echo "Путь к результатам: $DEBUG_DIR"
    echo "Для просмотра результатов диагностики выполните:"
    echo "  ls -la $DEBUG_DIR"
else
    echo "Ошибка при выполнении диагностики (код $EXIT_CODE)"
    echo "Частичные результаты могут быть доступны в: $DEBUG_DIR"
fi

exit $EXIT_CODE 