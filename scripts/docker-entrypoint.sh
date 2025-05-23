#!/bin/bash
set -e

echo "Starting Nota Bot Service"

# Проверка наличия необходимых директорий
mkdir -p logs tmp data

# Проверка переменных окружения
if [ -z "$TELEGRAM_TOKEN" ]; then
  echo "Error: TELEGRAM_TOKEN environment variable is not set"
  exit 1
fi

if [ -z "$OPENAI_OCR_KEY" ]; then
  echo "Warning: OPENAI_OCR_KEY environment variable is not set. OCR functionality will be disabled."
fi

echo "Environment check passed"

# Настраиваем логирование
LOG_FILE="logs/nota-bot-$(date +%Y%m%d).log"
touch $LOG_FILE
ln -sf $LOG_FILE logs/nota-bot.log

# Запуск приложения с автоматическим перезапуском
echo "Starting bot..."
exec python bot.py 2>&1 | tee -a $LOG_FILE