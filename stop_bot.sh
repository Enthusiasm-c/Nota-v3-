#!/bin/bash
# Скрипт для полной остановки всех экземпляров бота

echo "Stopping all bot processes..."

# Попробуем мягкое завершение сначала
pkill -f "python.*bot.py" 2>/dev/null

# Даем процессам 2 секунды на завершение
sleep 2

# Проверяем, остались ли процессы
REMAINING_PROCESSES=$(ps aux | grep -i "python.*bot.py" | grep -v grep | wc -l)

# Если что-то все еще работает, убиваем принудительно
if [ "$REMAINING_PROCESSES" -gt 0 ]; then
    echo "Force stopping remaining processes..."
    pkill -9 -f "python.*bot.py" 2>/dev/null
fi

# Удаляем файл PID, если он существует
rm -f bot.pid 2>/dev/null

# Проверяем окончательный результат
FINAL_CHECK=$(ps aux | grep -i "python.*bot.py" | grep -v grep | wc -l)

if [ "$FINAL_CHECK" -eq 0 ]; then
    echo "All bot processes successfully stopped."
else
    echo "Warning: Some bot processes could not be stopped!"
    ps aux | grep -i "python.*bot.py" | grep -v grep
fi 