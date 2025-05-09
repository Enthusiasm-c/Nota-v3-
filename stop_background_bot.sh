#!/bin/bash
# Скрипт для поиска и остановки всех фоновых процессов бота Nota
# Автор: Claude AI
# Дата: $(date +%Y-%m-%d)

echo "=== Скрипт остановки фонового бота Nota v1.0 ==="
echo "Этот скрипт найдет и остановит все фоновые процессы бота"
echo "для подготовки к запуску в режиме отладки."
echo ""

# Директория для логов
LOG_DIR="logs"
mkdir -p "$LOG_DIR"
DATE_STAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="$LOG_DIR/bot_stop_$DATE_STAMP.log"

# Функция логирования
log() {
    echo "[$(date +%Y-%m-%d\ %H:%M:%S)] $1" | tee -a "$LOG_FILE"
}

log "Начинаем остановку бота"

# Найдем все процессы run_forever, которые запускают бота в фоне
log "Поиск процессов run_forever.sh..."
FOREVER_PIDS=$(pgrep -f "run_forever\.sh")

if [ -n "$FOREVER_PIDS" ]; then
    log "Найдены процессы run_forever.sh: $FOREVER_PIDS"
    for pid in $FOREVER_PIDS; do
        log "Останавливаем процесс run_forever.sh (PID: $pid)"
        kill -15 $pid
    done
else
    log "Процессы run_forever.sh не найдены"
fi

# Найдем все процессы бота
log "Поиск процессов бота (bot.py)..."
BOT_PIDS=$(pgrep -f "python.*bot\.py")

if [ -n "$BOT_PIDS" ]; then
    log "Найдены процессы бота: $BOT_PIDS"
    for pid in $BOT_PIDS; do
        log "Останавливаем процесс бота (PID: $pid)"
        kill -15 $pid
    done
else
    log "Процессы бота не найдены"
fi

# Подождем 5 секунд, чтобы процессы могли корректно завершиться
log "Ожидаем 5 секунд для корректного завершения процессов..."
sleep 5

# Проверим, остались ли процессы, и принудительно завершим их
log "Проверяем, остались ли процессы..."
REMAINING_FOREVER=$(pgrep -f "run_forever\.sh")
REMAINING_BOT=$(pgrep -f "python.*bot\.py")

if [ -n "$REMAINING_FOREVER" ] || [ -n "$REMAINING_BOT" ]; then
    log "Найдены оставшиеся процессы, принудительно завершаем..."
    
    if [ -n "$REMAINING_FOREVER" ]; then
        log "Оставшиеся процессы run_forever.sh: $REMAINING_FOREVER"
        for pid in $REMAINING_FOREVER; do
            log "Принудительно завершаем процесс run_forever.sh (PID: $pid)"
            kill -9 $pid
        done
    fi
    
    if [ -n "$REMAINING_BOT" ]; then
        log "Оставшиеся процессы бота: $REMAINING_BOT"
        for pid in $REMAINING_BOT; do
            log "Принудительно завершаем процесс бота (PID: $pid)"
            kill -9 $pid
        done
    fi
else
    log "Все процессы успешно остановлены"
fi

# Сохраним список всех текущих процессов Python для анализа
log "Сохраняем список текущих Python-процессов..."
ps aux | grep python | grep -v grep > "$LOG_DIR/python_processes_$DATE_STAMP.txt"
log "Список процессов сохранен в $LOG_DIR/python_processes_$DATE_STAMP.txt"

# Проверим наличие скрипта для отладки и предложим его запустить
if [ -f "debug_bot.sh" ]; then
    log "Найден скрипт debug_bot.sh для запуска в режиме отладки"
    log "Рекомендуемая команда запуска бота с подробными логами:"
    echo ""
    echo "  ./debug_bot.sh"
    echo ""
else
    log "Скрипт debug_bot.sh не найден"
    log "Рекомендуемая команда запуска бота с подробными логами:"
    echo ""
    echo "  PYTHONPATH=. python bot.py"
    echo ""
fi

# Предупреждение о запуске в systemd
log "Проверяем наличие systemd-сервиса..."
if systemctl list-unit-files | grep -q nota-bot; then
    log "ВНИМАНИЕ: Обнаружен systemd-сервис для бота"
    log "Если бот запускается через systemd, выполните также:"
    echo ""
    echo "  sudo systemctl stop nota-bot"
    echo ""
else
    log "Systemd-сервис для бота не обнаружен"
fi

log "Операция завершена. Все фоновые процессы бота остановлены."
echo ""
echo "=== Все готово для запуска бота в режиме отладки ==="
echo "Журнал операции сохранен в $LOG_FILE"
echo ""

exit 0 