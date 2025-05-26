#!/bin/bash

# Restart Bot Script
# Kills all existing bot processes and starts a clean instance

echo "🤖 NotaAI Bot Restart Script"
echo "=============================="

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOT_DIR="$SCRIPT_DIR"

echo "📁 Working directory: $BOT_DIR"

# Kill existing bot processes
echo "🔪 Killing existing bot processes..."

# Kill by bot.py name
pkill -f "python.*bot\.py" 2>/dev/null || true
pkill -f "\.venv.*python.*bot" 2>/dev/null || true

# Kill by process name if any
ps aux | grep -E "(python.*bot|bot\.py)" | grep -v grep | awk '{print $2}' | xargs -r kill -9 2>/dev/null || true

# Wait a moment for processes to clean up
sleep 2

# Verify no bot processes remain
remaining=$(ps aux | grep -E "(python.*bot|bot\.py)" | grep -v grep | wc -l)
if [ "$remaining" -gt 0 ]; then
    echo "⚠️  Warning: $remaining bot processes still running"
    ps aux | grep -E "(python.*bot|bot\.py)" | grep -v grep
else
    echo "✅ All bot processes killed"
fi

# Change to bot directory
cd "$BOT_DIR" || {
    echo "❌ Failed to change to bot directory: $BOT_DIR"
    exit 1
}

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "❌ Virtual environment not found at .venv"
    exit 1
fi

# Check if bot.py exists
if [ ! -f "bot.py" ]; then
    echo "❌ bot.py not found in $BOT_DIR"
    exit 1
fi

echo "🚀 Starting new bot instance..."

# Start bot in background with logging
nohup .venv/bin/python bot.py > logs/bot_restart.log 2>&1 &
BOT_PID=$!

# Wait a moment and check if bot started successfully
sleep 3

if kill -0 $BOT_PID 2>/dev/null; then
    echo "✅ Bot started successfully with PID: $BOT_PID"
    echo "📋 Bot logs: tail -f logs/bot_restart.log"
    echo "🔍 Check status: ps aux | grep $BOT_PID"
else
    echo "❌ Bot failed to start"
    echo "📋 Check logs: cat logs/bot_restart.log"
    exit 1
fi

echo "=============================="
echo "🎉 Bot restart completed!"