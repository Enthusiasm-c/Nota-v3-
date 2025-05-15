#!/bin/bash
# Script to run the bot with debug settings
export DEBUG_LEVEL=DEBUG
export LOG_TO_STDOUT=1
export TESTING_MODE=1
export ENABLE_DEBUG_LOGS=1
export PYTHONUNBUFFERED=1  # Отключаем буферизацию вывода Python

echo "Starting bot in DEBUG mode..."

# Определяем, какое виртуальное окружение использовать
if [ -d "venv" ]; then
    echo "Using venv virtual environment"
    source venv/bin/activate
elif [ -d ".venv" ]; then
    echo "Using .venv virtual environment"
    source .venv/bin/activate
elif [ -d "nota_venv" ]; then
    echo "Using nota_venv virtual environment"
    source nota_venv/bin/activate
else
    echo "No virtual environment found, using system Python"
fi

# Запускаем бота через check_and_restart.py
echo "Starting bot with safe restart to prevent Telegram API conflicts..."
python check_and_restart.py
