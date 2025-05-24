#!/bin/bash

# Скрипт мониторинга и автоматического перезапуска Nota AI Telegram Bot
# Проверяет состояние бота каждые 30 секунд и перезапускает при необходимости

LOG_FILE="logs/monitor.log"
BOT_LOG_FILE="logs/bot.log"
PID_FILE="bot.pid"
MAX_RESTART_ATTEMPTS=5
RESTART_DELAY=10

# Создаем директорию для логов если её нет
mkdir -p logs

log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

check_bot_running() {
    if [ -f "$PID_FILE" ]; then
        local pid=$(cat "$PID_FILE")
        if ps -p "$pid" > /dev/null 2>&1; then
            return 0  # Бот запущен
        else
            rm -f "$PID_FILE"
            return 1  # PID файл есть, но процесс не найден
        fi
    else
        # Проверяем процессы Python с bot.py
        local bot_processes=$(ps aux | grep -E "[Pp]ython.*bot\.py" | grep -v grep | wc -l)
        if [ "$bot_processes" -gt 0 ]; then
            log_message "ВНИМАНИЕ: Найдены процессы бота без PID файла"
            return 0
        else
            return 1  # Бот не запущен
        fi
    fi
}

check_bot_health() {
    # Проверяем последние записи в логе на наличие ошибок
    if [ -f "$BOT_LOG_FILE" ]; then
        local recent_errors=$(tail -50 "$BOT_LOG_FILE" | grep -E "ERROR|CRITICAL|Exception|Traceback" | wc -l)
        local telegram_conflicts=$(tail -20 "$BOT_LOG_FILE" | grep "TelegramConflictError" | wc -l)

        if [ "$telegram_conflicts" -gt 0 ]; then
            log_message "ПРОБЛЕМА: Обнаружен TelegramConflictError - возможно запущено несколько экземпляров"
            return 1
        fi

        if [ "$recent_errors" -gt 5 ]; then
            log_message "ПРОБЛЕМА: Слишком много ошибок в логах ($recent_errors)"
            return 1
        fi
    fi
    return 0
}

start_bot() {
    log_message "Запуск бота..."

    # Останавливаем все существующие процессы
    ./stop_bot.sh >> "$LOG_FILE" 2>&1
    sleep 3

    # Запускаем бота
    ./start_bot.sh >> "$LOG_FILE" 2>&1

    if [ $? -eq 0 ]; then
        log_message "Бот успешно запущен"
        return 0
    else
        log_message "ОШИБКА: Не удалось запустить бота"
        return 1
    fi
}

restart_attempts=0

log_message "=== Запуск мониторинга Nota AI Bot ==="

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
                log_message "КРИТИЧЕСКАЯ ОШИБКА: Превышено максимальное количество попыток перезапуска ($MAX_RESTART_ATTEMPTS)"
                log_message "Ожидание $((RESTART_DELAY * 6)) секунд перед следующей попыткой..."
                sleep $((RESTART_DELAY * 6))
                restart_attempts=0
            else
                log_message "Ожидание $RESTART_DELAY секунд перед следующей попыткой..."
                sleep "$RESTART_DELAY"
            fi
        fi
    fi

    sleep 30
done
