#!/bin/bash
# Оптимизированный скрипт запуска бота Nota
# Обеспечивает быстрый запуск, автоматический перезапуск и обработку сигналов

# Каталог установки - автоопределение или указанный путь
if [ -z "$PROJECT_DIR" ]; then
    PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
fi
cd "$PROJECT_DIR"

# Настройка логирования
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/bot_startup.log"

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
log "Starting Optimized Nota Bot"

# Активация виртуального окружения
if [ -d "$PROJECT_DIR/venv" ]; then
    source "$PROJECT_DIR/venv/bin/activate"
    log "Virtual environment activated"
elif [ -d "$PROJECT_DIR/.venv" ]; then
    source "$PROJECT_DIR/.venv/bin/activate"
    log "Virtual environment (.venv) activated"
elif [ -d "$PROJECT_DIR/nota_venv" ]; then
    source "$PROJECT_DIR/nota_venv/bin/activate"
    log "Virtual environment (nota_venv) activated"
fi

# Загрузка переменных окружения
source "$PROJECT_DIR/.env"

# Настройка переменных для логирования и производительности
export DEBUG_LEVEL="DEBUG"
export LOG_TO_STDOUT=1
export PYTHONUNBUFFERED=1
export ENABLE_DEBUG_LOGS=1

# Предварительная проверка Redis
if command -v redis-cli &> /dev/null; then
    log "Checking Redis connection..."
    if ! redis-cli ping > /dev/null 2>&1; then
        log "WARNING: Redis seems to be unavailable. The bot will use local cache."
    else
        log "Redis is available"
    fi
fi

# Запускаем бота через check_and_restart.py
log "Starting bot with safe restart to prevent Telegram API conflicts..."
python check_and_restart.py --force-restart 2>&1 | tee -a "$LOG_FILE"

# Получаем PID запущенного бота
BOT_PID=$(ps aux | grep 'python.*bot\.py' | grep -v grep | awk '{print $2}' | head -1)
if [ -n "$BOT_PID" ]; then
    echo "$BOT_PID" > "$LOG_DIR/bot.pid"
    log "Bot started with PID: $BOT_PID"
else
    log "WARNING: Could not find bot PID, it may not have started correctly."
fi

# Обработка сигналов завершения
shutdown() {
    log "Received termination signal, stopping bot gracefully (PID: $BOT_PID)..."
    if [ -n "$BOT_PID" ]; then
        # Отправляем SIGINT для корректного завершения
        kill -SIGINT $BOT_PID
        
        # Ждем до 15 секунд завершения процесса
        for i in {1..15}; do
            if ! kill -0 $BOT_PID 2>/dev/null; then
                log "Bot gracefully shut down"
                break
            fi
            sleep 1
        done
        
        # Если процесс не завершился, используем SIGKILL
        if kill -0 $BOT_PID 2>/dev/null; then
            log "Bot did not terminate in time, forcing termination..."
            kill -SIGKILL $BOT_PID
        fi
    fi
    
    exit 0
}

# Регистрируем обработчики сигналов
trap shutdown SIGINT SIGTERM

# Вывод консоли для интерактивного использования
echo ""
echo "=== Nota Bot is running! ==="
echo "- Log file: $LOG_FILE"
echo "- Press Ctrl+C to stop the bot"
echo ""

# Мониторинг запущенного процесса (если не на фоне)
if [ -n "$BOT_PID" ]; then
    log "Monitoring bot process with PID: $BOT_PID"
    
    # Ждем завершения процесса
    wait $BOT_PID
    EXIT_CODE=$?
    log "Bot process exited with code $EXIT_CODE"
    
    # Выходим с кодом завершения бота
    exit $EXIT_CODE
fi
