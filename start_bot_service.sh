#!/bin/bash

# Директория проекта
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

# Функция для логирования
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$PROJECT_DIR/bot_service.log"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Проверка наличия Python
if ! command -v python3 &> /dev/null; then
    log "ERROR: Python3 не найден"
    exit 1
fi

# Проверка наличия виртуального окружения
if [ ! -d "venv" ]; then
    log "Создаем виртуальное окружение..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

# Функция для запуска бота
start_bot() {
    log "Запуск бота..."
    while true; do
        PYTHONPATH="$PROJECT_DIR" python3 bot.py 2>> "$PROJECT_DIR/bot_error.log"
        EXIT_CODE=$?
        
        if [ $EXIT_CODE -ne 0 ]; then
            log "Бот завершился с ошибкой (код $EXIT_CODE). Перезапуск через 10 секунд..."
            sleep 10
        else
            log "Бот завершился штатно. Перезапуск..."
        fi
    done
}

# Запуск бота в фоновом режиме
start_bot &

# Сохраняем PID процесса
echo $! > "$PROJECT_DIR/bot.pid"
log "Бот запущен с PID $(cat "$PROJECT_DIR/bot.pid")" 