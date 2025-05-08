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
ASSISTANT_TRACE_LOG="$LOG_DIR/assistant_trace.log"
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
elif [ -d "$PROJECT_DIR/.venv" ]; then
    source "$PROJECT_DIR/.venv/bin/activate"
    log "Virtual environment (.venv) activated"
fi

# Загрузка переменных окружения
source "$PROJECT_DIR/.env"

# Функция для показа логов в реальном времени
tail_logs() {
    # Организуем вывод логов в systemd журнал
    touch "$ASSISTANT_TRACE_LOG"
    tail -f "$ASSISTANT_TRACE_LOG" >> "$LOG_DIR/bot_output.log" 2>&1 &
    TAIL_PID=$!
    
    # Сохраняем PID для корректного завершения
    echo $TAIL_PID > "$LOG_DIR/tail.pid"
}

# Корректная обработка сигналов
shutdown() {
    log "Получен сигнал завершения, останавливаю бота (PID: $BOT_PID)..."
    if [ -n "$BOT_PID" ]; then
        # Отправляем SIGINT вместо SIGTERM для корректного завершения
        kill -SIGINT $BOT_PID
        # Ждем до 8 секунд завершения процесса
        for i in {1..8}; do
            if ! kill -0 $BOT_PID 2>/dev/null; then
                log "Бот корректно завершил работу"
                break
            fi
            sleep 1
        done
        # Если процесс не завершился, используем SIGKILL
        if kill -0 $BOT_PID 2>/dev/null; then
            log "Бот не завершился вовремя, принудительное завершение..."
            kill -SIGKILL $BOT_PID
        fi
    fi
    
    # Останавливаем процесс tail, если запущен
    if [ -f "$LOG_DIR/tail.pid" ]; then
        TAIL_PID=$(cat "$LOG_DIR/tail.pid")
        if [ -n "$TAIL_PID" ]; then
            kill $TAIL_PID 2>/dev/null || true
            rm "$LOG_DIR/tail.pid"
        fi
    fi
    
    exit 0
}

# Регистрируем обработчики сигналов
trap shutdown SIGINT SIGTERM

# Начинаем следить за логами
tail_logs

# Запускаем бота в фоне и запоминаем его PID
python bot.py >> "$LOG_DIR/bot_output.log" 2>> "$LOG_DIR/bot_stderr.log" &
BOT_PID=$!
log "Bot started with PID: $BOT_PID"

# Ждем завершения процесса
wait $BOT_PID
EXIT_CODE=$?
log "Bot process exited with code $EXIT_CODE"

# Останавливаем tail логов
if [ -f "$LOG_DIR/tail.pid" ]; then
    TAIL_PID=$(cat "$LOG_DIR/tail.pid")
    if [ -n "$TAIL_PID" ]; then
        kill $TAIL_PID 2>/dev/null || true
        rm "$LOG_DIR/tail.pid"
    fi
fi

# Выходим с кодом завершения бота
exit $EXIT_CODE 