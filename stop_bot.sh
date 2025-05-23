#!/bin/bash

# Скрипт для безопасной остановки Telegram бота

echo "🛑 Остановка Nota AI Telegram Bot..."

# 1. Мягкая остановка всех процессов бота
echo "🔪 Завершение процессов бота..."
BOT_PROCESSES=$(ps aux | grep -E "(Python|python).*bot\.py" | grep -v grep | wc -l)

if [ "$BOT_PROCESSES" -eq 0 ]; then
    echo "✅ Процессы бота не найдены (уже остановлен)"
    exit 0
fi

echo "📋 Найдено процессов бота: $BOT_PROCESSES"
echo "🔍 Детали процессов:"
ps aux | grep -E "(Python|python).*bot\.py" | grep -v grep

# Получаем все PID процессов бота
BOT_PIDS=$(ps aux | grep -E "(Python|python).*bot\.py" | grep -v grep | awk '{print $2}' || true)

# Мягкое завершение всех процессов
if [ ! -z "$BOT_PIDS" ]; then
    echo "🔄 Мягко завершаем процессы: $BOT_PIDS"
    for pid in $BOT_PIDS; do
        kill $pid 2>/dev/null || true
    done
fi

# Дополнительно используем pkill
pkill -f "python.*bot\.py" || true
pkill -f "Python.*bot\.py" || true
pkill -f "bot\.py" || true

# Ждем завершения
sleep 3

# 2. Проверяем результат
REMAINING=$(ps aux | grep -E "(Python|python).*bot\.py" | grep -v grep | wc -l)

if [ "$REMAINING" -eq 0 ]; then
    echo "✅ Все процессы бота успешно завершены"
else
    echo "⚠️  Найдены незавершенные процессы, принудительно убиваем..."

    # Получаем PID оставшихся процессов
    REMAINING_PIDS=$(ps aux | grep -E "(Python|python).*bot\.py" | grep -v grep | awk '{print $2}' || true)
    if [ ! -z "$REMAINING_PIDS" ]; then
        echo "🔍 Принудительно завершаем PIDs: $REMAINING_PIDS"
        for pid in $REMAINING_PIDS; do
            kill -9 $pid 2>/dev/null || true
        done
    fi

    pkill -9 -f "bot\.py" || true
    sleep 1

    # Финальная проверка
    FINAL_CHECK=$(ps aux | grep -E "(Python|python).*bot\.py" | grep -v grep | wc -l)
    if [ "$FINAL_CHECK" -eq 0 ]; then
        echo "✅ Все процессы принудительно завершены"
    else
        echo "❌ Не удалось завершить некоторые процессы:"
        ps aux | grep -E "(Python|python).*bot\.py" | grep -v grep
        exit 1
    fi
fi

echo "🎯 Бот полностью остановлен"
