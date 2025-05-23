#!/bin/bash

# Скрипт для безопасного запуска Telegram бота
# Убивает все предыдущие процессы и запускает новый экземпляр

set -e  # Прекратить выполнение при ошибке

echo "🔄 Запуск Nota AI Telegram Bot..."

# 1. Убиваем все процессы бота (более широкий поиск)
echo "🔪 Завершение предыдущих процессов бота..."

# Ищем процессы по разным паттернам
pkill -f "python.*bot\.py" || true
pkill -f "Python.*bot\.py" || true
pkill -f "bot\.py" || true

# Дополнительно ищем по PID если есть процессы с полным путем
BOT_PIDS=$(ps aux | grep -E "(Python|python).*bot\.py" | grep -v grep | awk '{print $2}' || true)
if [ ! -z "$BOT_PIDS" ]; then
    echo "🔍 Найдены дополнительные процессы: $BOT_PIDS"
    for pid in $BOT_PIDS; do
        kill $pid 2>/dev/null || true
    done
fi

# Ждем немного чтобы процессы корректно завершились
sleep 3

# 2. Проверяем что процессы действительно завершены
BOT_PROCESSES=$(ps aux | grep -E "(Python|python).*bot\.py" | grep -v grep | wc -l)
if [ "$BOT_PROCESSES" -gt 0 ]; then
    echo "⚠️  Найдены незавершенные процессы, принудительно убиваем..."

    # Получаем PID всех процессов бота
    REMAINING_PIDS=$(ps aux | grep -E "(Python|python).*bot\.py" | grep -v grep | awk '{print $2}' || true)
    if [ ! -z "$REMAINING_PIDS" ]; then
        echo "🔍 Принудительно завершаем PIDs: $REMAINING_PIDS"
        for pid in $REMAINING_PIDS; do
            kill -9 $pid 2>/dev/null || true
        done
    fi

    pkill -9 -f "bot\.py" || true
    sleep 1
fi

# 3. Финальная проверка что нет конфликтующих процессов
REMAINING=$(ps aux | grep -E "(Python|python).*bot\.py" | grep -v grep | wc -l)
if [ "$REMAINING" -gt 0 ]; then
    echo "❌ Не удалось завершить все процессы бота!"
    echo "🔍 Оставшиеся процессы:"
    ps aux | grep -E "(Python|python).*bot\.py" | grep -v grep
    exit 1
fi

echo "✅ Все предыдущие процессы завершены"

# 4. Создаем директорию для логов если её нет
mkdir -p logs

# 5. Запускаем бота
echo "🚀 Запускаем нового бота..."
python bot.py &

# Получаем PID нового процесса
BOT_PID=$!
echo "📋 Бот запущен с PID: $BOT_PID"

# 6. Ждем немного и проверяем что бот успешно запустился
sleep 5

if kill -0 $BOT_PID 2>/dev/null; then
    echo "✅ Бот успешно запущен и работает"
    echo "📄 Логи: tail -f logs/bot.log"
    echo "🔧 Остановка: ./stop_bot.sh"

    # Показываем что теперь запущен только один процесс
    FINAL_COUNT=$(ps aux | grep -E "(Python|python).*bot\.py" | grep -v grep | wc -l)
    echo "📊 Запущено процессов бота: $FINAL_COUNT"
else
    echo "❌ Бот не смог запуститься, проверьте логи"
    exit 1
fi
