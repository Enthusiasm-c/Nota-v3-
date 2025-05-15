#!/bin/bash

# Настройки
APP_DIR="$(pwd)"
PYTHON_PATH="python3"  # Или полный путь к вашему интерпретатору python
BOT_SCRIPT="bot.py"    # Имя главного скрипта бота
LOG_DIR="${APP_DIR}/logs"
LOG_FILE="${LOG_DIR}/bot_monitor.log"
ERROR_LOG="${LOG_DIR}/bot_errors.log"
RESTART_LOG="${LOG_DIR}/bot_restarts.log"
PID_FILE="${APP_DIR}/bot.pid"
CHECK_INTERVAL=60      # Интервал проверки работоспособности в секундах

# Создание директории для логов, если она не существует
mkdir -p "${LOG_DIR}"

# Функция для логирования
log() {
    local message="$(date '+%Y-%m-%d %H:%M:%S') - $1"
    echo "${message}" | tee -a "${LOG_FILE}"
}

# Функция для логирования ошибок
error_log() {
    local message="$(date '+%Y-%m-%d %H:%M:%S') - ERROR: $1"
    echo "${message}" | tee -a "${ERROR_LOG}"
    echo "${message}" | tee -a "${LOG_FILE}"
}

# Функция для логирования перезапусков
restart_log() {
    local message="$(date '+%Y-%m-%d %H:%M:%S') - RESTART: $1"
    echo "${message}" | tee -a "${RESTART_LOG}"
    echo "${message}" | tee -a "${LOG_FILE}"
}

# Функция для запуска бота
start_bot() {
    log "Запуск бота..."
    
    # Проверяем, не запущен ли уже бот
    if [ -f "${PID_FILE}" ]; then
        local old_pid=$(cat "${PID_FILE}")
        if ps -p "${old_pid}" > /dev/null 2>&1; then
            error_log "Бот уже запущен с PID ${old_pid}"
            return 1
        else
            log "Обнаружен неактуальный PID файл. Удаляем..."
            rm -f "${PID_FILE}"
        fi
    fi
    
    # Запускаем бот в фоновом режиме
    cd "${APP_DIR}"
    
    # Запускаем с перенаправлением вывода в файлы логов
    nohup ${PYTHON_PATH} ${BOT_SCRIPT} > "${LOG_DIR}/bot_stdout.log" 2> "${LOG_DIR}/bot_stderr.log" &
    
    local bot_pid=$!
    echo "${bot_pid}" > "${PID_FILE}"
    
    # Проверяем, что процесс действительно запущен
    if ps -p "${bot_pid}" > /dev/null 2>&1; then
        log "Бот успешно запущен с PID ${bot_pid}"
        return 0
    else
        error_log "Не удалось запустить бота"
        return 1
    fi
}

# Функция для остановки бота
stop_bot() {
    log "Остановка бота..."
    if [ -f "${PID_FILE}" ]; then
        local pid=$(cat "${PID_FILE}")
        if ps -p "${pid}" > /dev/null 2>&1; then
            log "Отправка сигнала SIGTERM для PID ${pid}"
            kill "${pid}"
            
            # Ждем до 10 секунд для корректного завершения
            for i in {1..10}; do
                if ! ps -p "${pid}" > /dev/null 2>&1; then
                    log "Бот успешно остановлен"
                    rm -f "${PID_FILE}"
                    return 0
                fi
                sleep 1
            done
            
            # Если процесс все еще работает, принудительно завершаем
            if ps -p "${pid}" > /dev/null 2>&1; then
                log "Принудительное завершение процесса (SIGKILL) для PID ${pid}"
                kill -9 "${pid}"
                rm -f "${PID_FILE}"
            fi
        else
            log "Процесс с PID ${pid} не найден"
            rm -f "${PID_FILE}"
        fi
    else
        log "PID файл не найден, бот не запущен"
    fi
}

# Функция для проверки состояния бота
check_bot() {
    if [ -f "${PID_FILE}" ]; then
        local pid=$(cat "${PID_FILE}")
        if ps -p "${pid}" > /dev/null 2>&1; then
            # Дополнительная проверка активности (можно расширить)
            local process_uptime=$(ps -o etimes= -p "${pid}")
            log "Бот работает (PID ${pid}, время работы: ${process_uptime} сек)"
            return 0
        else
            error_log "Бот не работает! PID файл существует, но процесс с PID ${pid} не найден"
            rm -f "${PID_FILE}"
            return 1
        fi
    else
        error_log "Бот не работает! PID файл не найден"
        return 1
    fi
}

# Функция для перезапуска бота
restart_bot() {
    restart_log "Перезапуск бота..."
    stop_bot
    sleep 2
    start_bot
}

# Функция для мониторинга и автоматического перезапуска
monitor_and_restart() {
    log "Запуск мониторинга бота с интервалом ${CHECK_INTERVAL} секунд"
    
    while true; do
        if ! check_bot; then
            restart_log "Обнаружена остановка бота. Автоматический перезапуск..."
            start_bot
        fi
        sleep ${CHECK_INTERVAL}
    done
}

# Обработка аргументов командной строки
case "$1" in
    start)
        start_bot
        ;;
    stop)
        stop_bot
        ;;
    restart)
        restart_bot
        ;;
    status)
        check_bot
        ;;
    monitor)
        # Запуск бота и его мониторинга
        start_bot
        monitor_and_restart
        ;;
    *)
        echo "Использование: $0 {start|stop|restart|status|monitor}"
        echo "  start   - запуск бота"
        echo "  stop    - остановка бота"
        echo "  restart - перезапуск бота"
        echo "  status  - проверка статуса бота"
        echo "  monitor - запуск бота с постоянным мониторингом и автоперезапуском"
        exit 1
        ;;
esac

exit 0 