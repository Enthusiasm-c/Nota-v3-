#!/bin/bash

# Функции управления ботом
start() {
    echo "Starting bot in normal mode..."
    python bot.py
}

start_debug() {
    echo "Starting bot in debug mode..."
    LOG_LEVEL=DEBUG python bot.py
}

start_background() {
    echo "Starting bot in background mode..."
    nohup python bot.py > /dev/null 2>&1 &
    echo $! > bot.pid
}

stop() {
    if [ -f bot.pid ]; then
        PID=$(cat bot.pid)
        echo "Stopping bot (PID: $PID)..."
        kill $PID
        rm bot.pid
    else
        echo "Bot is not running (no PID file found)"
    fi
}

restart() {
    stop
    sleep 2
    start
}

status() {
    if [ -f bot.pid ]; then
        PID=$(cat bot.pid)
        if ps -p $PID > /dev/null; then
            echo "Bot is running (PID: $PID)"
        else
            echo "Bot crashed or stopped unexpectedly"
            rm bot.pid
        fi
    else
        echo "Bot is not running"
    fi
}

# Обработка аргументов
case "$1" in
    start)
        start
        ;;
    debug)
        start_debug
        ;;
    background)
        start_background
        ;;
    stop)
        stop
        ;;
    restart)
        restart
        ;;
    status)
        status
        ;;
    *)
        echo "Usage: $0 {start|debug|background|stop|restart|status}"
        exit 1
        ;;
esac

exit 0 