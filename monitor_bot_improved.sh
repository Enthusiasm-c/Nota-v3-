#!/bin/bash

# Улучшенный скрипт мониторинга с защитой от множественных запусков
# Исправлены проблемы с TelegramConflictError

LOG_FILE="logs/monitor.log"
BOT_LOG_FILE="logs/bot.log"
PID_FILE="bot.pid"
MONITOR_PID_FILE="monitor.pid"
MAX_RESTART_ATTEMPTS=3
RESTART_DELAY=15
STOP_TIMEOUT=10

# Создаем директорию для логов если её нет
mkdir -p logs

# Проверяем что не запущен другой мониторинг
if [ -f "$MONITOR_PID_FILE" ]; then
    old_monitor_pid=$(cat "$MONITOR_PID_FILE")
    if ps -p "$old_monitor_pid" > /dev/null 2>&1; then
        echo "Мониторинг уже запущен (PID: $old_monitor_pid). Завершаем."
        exit 1
    else
        rm -f "$MONITOR_PID_FILE"
    fi
fi

# Записываем PID текущего мониторинга
echo $$ > "$MONITOR_PID_FILE"

log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

wait_for_process_stop() {
    local pid=$1
    local timeout=$2
    local count=0

    while [ $count -lt $timeout ] && ps -p "$pid" > /dev/null 2>&1; do
        sleep 1
        count=$((count + 1))
    done

    if ps -p "$pid" > /dev/null 2>&1; then
        return 1  # Процесс все еще работает
    else
        return 0  # Процесс завершен
    fi
}

stop_all_bot_processes() {
    log_message "Принудительная остановка ВСЕХ процессов бота..."

    # Находим все процессы
    local bot_pids=$(ps aux | grep -E "[Pp]ython.*bot\.py" | grep -v grep | awk '{print $2}' || true)

    if [ -n "$bot_pids" ]; then
        log_message "Найдены процессы бота: $bot_pids"

        # Мягкая остановка
        for pid in $bot_pids; do
            log_message "Отправляем SIGTERM процессу $pid"
            kill -TERM "$pid" 2>/dev/null || true
        done

        # Ждем завершения
        sleep $STOP_TIMEOUT

        # Проверяем что остались
        local remaining_pids=$(ps aux | grep -E "[Pp]ython.*bot\.py" | grep -v grep | awk '{print $2}' || true)

        if [ -n "$remaining_pids" ]; then
            log_message "Принудительно завершаем оставшиеся процессы: $remaining_pids"
            for pid in $remaining_pids; do
                kill -9 "$pid" 2>/dev/null || true
            done
            sleep 3
        fi
    fi

    # Очищаем PID файл
    rm -f "$PID_FILE"
    log_message "Все процессы бота остановлены"
}

check_bot_running() {
    local bot_processes=$(ps aux | grep -E "[Pp]ython.*bot\.py" | grep -v grep | wc -l)

    if [ "$bot_processes" -gt 1 ]; then
        log_message "КРИТИЧЕСКАЯ ОШИБКА: Обнаружено $bot_processes процессов бота! Останавливаем все."
        stop_all_bot_processes
        # ИСПРАВЛЕНИЕ: После остановки множественных процессов ждем и проверяем заново
        sleep 5
        local remaining_processes=$(ps aux | grep -E "[Pp]ython.*bot\.py" | grep -v grep | wc -l)
        if [ "$remaining_processes" -eq 0 ]; then
            log_message "Множественные процессы успешно остановлены. Нужен перезапуск."
            return 1  # Нет процессов - нужен запуск
        else
            log_message "После остановки осталось $remaining_processes процессов"
            return 0  # Есть процесс - считаем что работает
        fi
    elif [ "$bot_processes" -eq 1 ]; then
        return 0  # Один процесс - нормально
    else
        return 1  # Нет процессов
    fi
}

check_bot_health() {
    if [ -f "$BOT_LOG_FILE" ]; then
        local telegram_conflicts=$(tail -20 "$BOT_LOG_FILE" | grep "TelegramConflictError" | wc -l)
        local recent_errors=$(tail -50 "$BOT_LOG_FILE" | grep -E "ERROR|CRITICAL|Exception|Traceback" | grep -v "ОТЛАДКА|AI Action" | wc -l)

        if [ "$telegram_conflicts" -gt 0 ]; then
            log_message "ПРОБЛЕМА: TelegramConflictError - множественные экземпляры!"
            stop_all_bot_processes
            return 1
        fi

        if [ "$recent_errors" -gt 50 ]; then
            log_message "ПРОБЛЕМА: Слишком много ошибок ($recent_errors)"
            return 1
        fi
    fi
    return 0
}

start_bot() {
    log_message "Запуск бота..."

    # Убеждаемся что нет других процессов
    stop_all_bot_processes

    # Дополнительная пауза для полной остановки
    sleep 5

    # Запускаем единственный экземпляр
    log_message "Запускаем ЕДИНСТВЕННЫЙ экземпляр бота..."
    cd /root/Nota-v3
    nohup venv/bin/python3 bot.py > logs/bot_stdout.log 2> logs/bot_stderr.log &

    local new_pid=$!
    echo $new_pid > "$PID_FILE"
    log_message "Бот запущен с PID: $new_pid"

    # Ждем инициализации
    sleep 8

    # Проверяем что процесс жив
    if ps -p "$new_pid" > /dev/null 2>&1; then
        log_message "Бот успешно запущен и работает"
        return 0
    else
        log_message "ОШИБКА: Бот не смог запуститься"
        rm -f "$PID_FILE"
        return 1
    fi
}

# Обработчик сигналов для корректного завершения
cleanup() {
    log_message "Получен сигнал завершения мониторинга"
    rm -f "$MONITOR_PID_FILE"
    exit 0
}

trap cleanup SIGTERM SIGINT

restart_attempts=0

log_message "=== Запуск улучшенного мониторинга Nota AI Bot ==="

while true; do
    if check_bot_running; then
        if check_bot_health; then
            # Бот работает нормально
            restart_attempts=0
            echo -n "."  # Показываем что мониторинг активен
        else
            # Бот работает, но есть проблемы
            log_message "Бот работает, но обнаружены проблемы. Перезапуск..."
            if start_bot; then
                restart_attempts=0
            else
                restart_attempts=$((restart_attempts + 1))
            fi
        fi
    else
        # Бот не запущен
        log_message "Бот не запущен. Попытка запуска ($((restart_attempts + 1))/$MAX_RESTART_ATTEMPTS)..."

        if start_bot; then
            restart_attempts=0
        else
            restart_attempts=$((restart_attempts + 1))

            if [ "$restart_attempts" -ge "$MAX_RESTART_ATTEMPTS" ]; then
                log_message "КРИТИЧЕСКАЯ ОШИБКА: Превышено максимальное количество попыток перезапуска"
                log_message "Ожидание $((RESTART_DELAY * 4)) секунд перед следующей попыткой..."
                sleep $((RESTART_DELAY * 4))
                restart_attempts=0
            else
                log_message "Ожидание $RESTART_DELAY секунд перед следующей попыткой..."
                sleep "$RESTART_DELAY"
            fi
        fi
    fi

    sleep 30
done
