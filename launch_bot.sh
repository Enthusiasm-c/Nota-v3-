#!/bin/bash

# Settings
APP_DIR="$(pwd)"
PYTHON_PATH="python3"  # Or full path to your python interpreter
BOT_SCRIPT="bot.py"    # Main bot script name
LOG_DIR="${APP_DIR}/logs"
LOG_FILE="${LOG_DIR}/bot_monitor.log"
ERROR_LOG="${LOG_DIR}/bot_errors.log"
RESTART_LOG="${LOG_DIR}/bot_restarts.log"
PID_FILE="${APP_DIR}/bot.pid"
CHECK_INTERVAL=60      # Health check interval in seconds

# Create log directory if it doesn't exist
mkdir -p "${LOG_DIR}"

# Function to load environment variables from .env file
load_env() {
    if [ -f "${APP_DIR}/.env" ]; then
        log "Loading environment variables from .env file"
        set -a
        source "${APP_DIR}/.env"
        set +a
    else
        error_log ".env file not found"
        return 1
    fi
}

# Logging function
log() {
    local message="$(date '+%Y-%m-%d %H:%M:%S') - $1"
    echo "${message}" | tee -a "${LOG_FILE}"
}

# Error logging function
error_log() {
    local message="$(date '+%Y-%m-%d %H:%M:%S') - ERROR: $1"
    echo "${message}" | tee -a "${ERROR_LOG}"
    echo "${message}" | tee -a "${LOG_FILE}"
}

# Restart logging function
restart_log() {
    local message="$(date '+%Y-%m-%d %H:%M:%S') - RESTART: $1"
    echo "${message}" | tee -a "${RESTART_LOG}"
    echo "${message}" | tee -a "${LOG_FILE}"
}

# Bot start function
start_bot() {
    log "Starting bot..."
    
    # Load environment variables
    load_env
    
    # Check if bot is already running
    if [ -f "${PID_FILE}" ]; then
        local old_pid=$(cat "${PID_FILE}")
        if ps -p "${old_pid}" > /dev/null 2>&1; then
            error_log "Bot is already running with PID ${old_pid}"
            return 1
        else
            log "Found stale PID file. Removing..."
            rm -f "${PID_FILE}"
        fi
    fi
    
    # Start bot in background
    cd "${APP_DIR}"
    
    # Launch with output redirection to log files
    nohup ${PYTHON_PATH} ${BOT_SCRIPT} > "${LOG_DIR}/bot_stdout.log" 2> "${LOG_DIR}/bot_stderr.log" &
    
    local bot_pid=$!
    echo "${bot_pid}" > "${PID_FILE}"
    
    # Verify process is running
    if ps -p "${bot_pid}" > /dev/null 2>&1; then
        log "Bot successfully started with PID ${bot_pid}"
        return 0
    else
        error_log "Failed to start bot"
        return 1
    fi
}

# Bot stop function
stop_bot() {
    log "Stopping bot..."
    if [ -f "${PID_FILE}" ]; then
        local pid=$(cat "${PID_FILE}")
        if ps -p "${pid}" > /dev/null 2>&1; then
            log "Sending SIGTERM to PID ${pid}"
            kill "${pid}"
            
            # Wait up to 10 seconds for graceful shutdown
            for i in {1..10}; do
                if ! ps -p "${pid}" > /dev/null 2>&1; then
                    log "Bot successfully stopped"
                    rm -f "${PID_FILE}"
                    return 0
                fi
                sleep 1
            done
            
            # Force kill if still running
            if ps -p "${pid}" > /dev/null 2>&1; then
                log "Force killing process (SIGKILL) for PID ${pid}"
                kill -9 "${pid}"
                rm -f "${PID_FILE}"
            fi
        else
            log "Process with PID ${pid} not found"
            rm -f "${PID_FILE}"
        fi
    else
        log "PID file not found, bot is not running"
    fi
}

# Bot status check function
check_bot() {
    if [ -f "${PID_FILE}" ]; then
        local pid=$(cat "${PID_FILE}")
        if ps -p "${pid}" > /dev/null 2>&1; then
            # Additional activity check (can be extended)
            local process_uptime=$(ps -o etimes= -p "${pid}")
            log "Bot is running (PID ${pid}, uptime: ${process_uptime} sec)"
            return 0
        else
            error_log "Bot is not running! PID file exists but process with PID ${pid} not found"
            rm -f "${PID_FILE}"
            return 1
        fi
    else
        error_log "Bot is not running! PID file not found"
        return 1
    fi
}

# Bot restart function
restart_bot() {
    restart_log "Restarting bot..."
    stop_bot
    sleep 2
    start_bot
}

# Monitor and auto-restart function
monitor_and_restart() {
    log "Starting bot monitoring with ${CHECK_INTERVAL} seconds interval"
    
    while true; do
        if ! check_bot; then
            restart_log "Bot stopped detected. Auto-restarting..."
            start_bot
        fi
        sleep ${CHECK_INTERVAL}
    done
}

# Command line argument handling
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
        # Start bot and monitoring
        start_bot
        monitor_and_restart
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|monitor}"
        echo "  start   - start the bot"
        echo "  stop    - stop the bot"
        echo "  restart - restart the bot"
        echo "  status  - check bot status"
        echo "  monitor - start bot with continuous monitoring and auto-restart"
        exit 1
        ;;
esac

exit 0 