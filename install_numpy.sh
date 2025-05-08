#!/bin/bash

# Простой скрипт для установки numpy
echo "Начинаю установку numpy..."

# Определяем директорию проекта
PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$PROJECT_DIR"

# Проверка существования virtualenv
if [ -d "$PROJECT_DIR/venv" ]; then
    echo "Обнаружено виртуальное окружение, активирую..."
    source "$PROJECT_DIR/venv/bin/activate"
    PIP="$PROJECT_DIR/venv/bin/pip"
else
    echo "Виртуальное окружение не найдено, использую системный pip"
    PIP="pip3"
fi

# Установка numpy
echo "Устанавливаю numpy..."
$PIP install numpy

# Проверка установки
if python3 -c "import numpy" 2>/dev/null; then
    echo "numpy успешно установлен!"
    echo "Перезапустите бота: systemctl restart nota-bot"
else
    echo "Что-то пошло не так при установке numpy."
    echo "Попробуйте вручную: pip install numpy"
fi

# Самоуничтожение скрипта после выполнения
echo "Скрипт завершил работу. Самоуничтожаюсь..."
rm -- "$0" 