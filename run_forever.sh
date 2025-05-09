#!/bin/bash

LOGFILE="logs/nota-bot.log"
ERRFILE="logs/nota-bot.err"

# Определяем директорию проекта
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${PROJECT_DIR}"

# Создаем каталог логов, если его нет
mkdir -p logs

# Загружаем переменные окружения из .env
if [ -f "${PROJECT_DIR}/.env" ]; then
  echo "[run_forever.sh] Загружаю переменные окружения из .env..." >> "$LOGFILE"
  # Используем цикл для безопасного экспорта переменных с пробелами
  while IFS='=' read -r key value || [[ -n "$key" ]]; do
    # Пропускаем пустые строки и комментарии
    [[ -z "$key" || "$key" == \#* ]] && continue
    # Экспортируем переменную с сохранением пробелов
    export "$key"="$value"
  done < "${PROJECT_DIR}/.env"
else
  echo "[run_forever.sh] Файл .env не найден, продолжаю без переменных окружения" >> "$LOGFILE"
fi

# Активируем виртуальное окружение, если оно существует
if [ -d "${PROJECT_DIR}/venv" ]; then
  source "${PROJECT_DIR}/venv/bin/activate"
  PYTHON="${PROJECT_DIR}/venv/bin/python"
elif [ -d "${PROJECT_DIR}/.venv" ]; then
  source "${PROJECT_DIR}/.venv/bin/activate"
  PYTHON="${PROJECT_DIR}/.venv/bin/python"
else
  PYTHON="python3"
fi

while true; do
  echo "[run_forever.sh] Запуск бота: $(date)" >> "$LOGFILE"
  "${PYTHON}" "${PROJECT_DIR}/bot.py" >> "$LOGFILE" 2>> "$ERRFILE"
  echo "[run_forever.sh] Бот завершился! Перезапуск через 5 секунд..." >> "$LOGFILE"
  sleep 5
done 