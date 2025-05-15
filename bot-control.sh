#!/bin/bash
# bot-control.sh - Script for controlling the Nota Telegram bot

# Default configuration
PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
LOG_DIR="$PROJECT_DIR/logs"
PID_FILE="$LOG_DIR/bot.pid"
mkdir -p "$LOG_DIR"

# Function for logging
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Function to check if bot is running
is_bot_running() {
    if [ -f "$PID_FILE" ]; then
        BOT_PID=$(cat "$PID_FILE")
        if ps -p "$BOT_PID" > /dev/null; then
            return 0  # Bot is running
        fi
    fi
    return 1  # Bot is not running
}

# Start the bot
start_bot() {
    if is_bot_running; then
        log "Bot is already running with PID $(cat "$PID_FILE")"
        return 1
    fi
    
    log "Starting bot..."
    "$PROJECT_DIR/run_bot.sh" > "$LOG_DIR/bot_startup_latest.log" 2>&1 &
    sleep 2
    
    if is_bot_running; then
        log "Bot started successfully with PID $(cat "$PID_FILE")"
    else
        log "Failed to start bot. Check logs at $LOG_DIR/bot_startup_latest.log"
        return 1
    fi
}

# Stop the bot
stop_bot() {
    if ! is_bot_running; then
        log "Bot is not running"
        return 1
    fi
    
    BOT_PID=$(cat "$PID_FILE")
    log "Stopping bot with PID $BOT_PID..."
    
    # First try SIGTERM for graceful shutdown
    kill -SIGTERM "$BOT_PID"
    
    # Wait up to 8 seconds for graceful shutdown
    for i in {1..8}; do
        if ! ps -p "$BOT_PID" > /dev/null; then
            log "Bot stopped gracefully"
            rm -f "$PID_FILE"
            return 0
        fi
        sleep 1
    done
    
    # If still running, use SIGKILL
    log "Bot didn't stop gracefully, using SIGKILL..."
    kill -SIGKILL "$BOT_PID"
    sleep 1
    
    if ! ps -p "$BOT_PID" > /dev/null; then
        log "Bot stopped forcefully"
        rm -f "$PID_FILE"
    else
        log "Failed to stop bot"
        return 1
    fi
}

# Restart the bot
restart_bot() {
    log "Restarting bot..."
    stop_bot
    sleep 2
    start_bot
}

# Status of the bot
status_bot() {
    if is_bot_running; then
        BOT_PID=$(cat "$PID_FILE")
        BOT_UPTIME=$(ps -o etime= -p "$BOT_PID")
        log "Bot is running with PID $BOT_PID (uptime: $BOT_UPTIME)"
        
        # Show recent log entries
        log "Recent log entries:"
        tail -n 10 "$LOG_DIR/bot.log" 2>/dev/null || echo "No log file found"
    else
        log "Bot is not running"
    fi
}

# Display usage information
show_usage() {
    echo "Usage: $0 {start|stop|restart|status|logs}"
    echo ""
    echo "Commands:"
    echo "  start    Start the Telegram bot"
    echo "  stop     Stop the running bot instance"
    echo "  restart  Restart the bot (stop and start)"
    echo "  status   Show bot status and recent logs"
    echo "  logs     Show real-time logs"
    echo ""
}

# Show logs
show_logs() {
    LOG_FILE="$LOG_DIR/bot.log"
    if [ -f "$LOG_FILE" ]; then
        tail -f "$LOG_FILE"
    else
        log "Log file not found at $LOG_FILE"
        return 1
    fi
}

# Main logic
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
        status_bot
        ;;
    logs)
        show_logs
        ;;
    *)
        show_usage
        exit 1
        ;;
esac

exit 0