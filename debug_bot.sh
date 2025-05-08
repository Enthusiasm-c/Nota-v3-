#!/bin/bash

# debug_bot.sh - Скрипт для отладки и диагностики бота
# Запускает бота с подробными логами и мониторит его работу

# Цвета для лучшей читаемости
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

# Определяем директорию проекта
PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$PROJECT_DIR"

# Проверка существования виртуального окружения
if [ -d "$PROJECT_DIR/venv" ]; then
    echo -e "${GREEN}[+] Обнаружено виртуальное окружение, активирую...${NC}"
    source "$PROJECT_DIR/venv/bin/activate"
    PYTHON="$PROJECT_DIR/venv/bin/python"
else
    echo -e "${YELLOW}[!] Виртуальное окружение не найдено, использую системный Python${NC}"
    PYTHON="python3"
fi

# Создаем каталог логов
mkdir -p "$PROJECT_DIR/logs"
LOG_FILE="$PROJECT_DIR/logs/bot_debug.log"
ERROR_LOG="$PROJECT_DIR/logs/bot_stderr.log"

# Очищаем старые логи
echo "" > "$LOG_FILE"
echo "" > "$ERROR_LOG"

echo -e "${GREEN}[+] Запускаю бота в отладочном режиме...${NC}"
echo -e "${YELLOW}[!] Логи записываются в $LOG_FILE и $ERROR_LOG${NC}"
echo -e "${YELLOW}[!] Нажмите Ctrl+C для остановки бота${NC}"

# Устанавливаем переменные окружения для отладки
export LOG_LEVEL="DEBUG"
export ENV="development"

# Запускаем бота с отладочными выводами
$PYTHON bot.py 2> >(tee -a "$ERROR_LOG") | tee -a "$LOG_FILE" 