#!/bin/bash

# run_bot.sh - Скрипт для запуска Nota Telegram бота
# Оптимизирован для работы с systemd и обработки сигналов

# Каталог установки - автоопределение или указанный путь
if [ -z "$PROJECT_DIR" ]; then
    # Используем каталог, где находится скрипт
    PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
fi
cd "$PROJECT_DIR"

# Настройка логирования
LOG_DIR="$PROJECT_DIR/logs"
LOG_FILE="$LOG_DIR/bot_startup.log"
mkdir -p "$LOG_DIR"

# Функция логирования
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Очистка временных файлов
log "Cleaning tmp directory..."
mkdir -p "$PROJECT_DIR/tmp"
rm -rf "$PROJECT_DIR/tmp/"*

# Проверка окружения
log "Checking environment..."
if [ ! -f "$PROJECT_DIR/.env" ]; then
    log "ERROR: .env file not found!"
    exit 1
fi

# Сообщаем о запуске
log "Starting Nota Bot"

# Активация виртуального окружения
if [ -d "$PROJECT_DIR/venv" ]; then
    source "$PROJECT_DIR/venv/bin/activate"
    log "Virtual environment activated"
fi

# Загрузка переменных окружения
source "$PROJECT_DIR/.env"

# Функция обработки сигналов завершения
_term() {
    log "Received SIGTERM/SIGINT signal"
    # Передаем сигнал боту для graceful shutdown
    if [ -n "$BOT_PID" ]; then
        log "Sending SIGINT to bot process $BOT_PID"
        kill -INT $BOT_PID
        
        # Ждем до 15 секунд (меньше чем таймаут systemd в 20-25 секунд)
        for i in {1..15}; do
            if ! kill -0 $BOT_PID 2>/dev/null; then
                log "Bot process terminated normally"
                exit 0
            fi
            sleep 1
        done
        
        # Если процесс все еще жив, шлем SIGTERM
        if kill -0 $BOT_PID 2>/dev/null; then
            log "Bot still running after 15s, sending SIGTERM"
            kill -TERM $BOT_PID
            sleep 3
        fi
        
        # Принудительно завершаем, если все еще жив
        if kill -0 $BOT_PID 2>/dev/null; then
            log "WARNING: Bot still running, forcing exit"
            kill -9 $BOT_PID
        fi
    fi
    exit 0
}

# Установка обработчиков сигналов
trap _term SIGTERM
trap _term SIGINT

# Запуск бота с перенаправлением вывода
log "Executing python bot.py"
python3 "$PROJECT_DIR/bot.py" > "$LOG_DIR/bot_stdout.log" 2> "$LOG_DIR/bot_stderr.log" &
BOT_PID=$!
log "Bot started with PID: $BOT_PID"

# Сохраняем PID для внешнего мониторинга
echo $BOT_PID > "$PROJECT_DIR/bot.pid"

# Ждем завершения процесса
wait $BOT_PID
EXIT_CODE=$?
log "Bot process exited with code $EXIT_CODE"

# Очистка
rm -f "$PROJECT_DIR/bot.pid"
exit $EXIT_CODE 