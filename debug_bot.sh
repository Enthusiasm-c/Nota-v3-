#!/bin/bash

# debug_bot.sh - Скрипт для отладки и диагностики бота
# Запускает бота с подробными логами и мониторит его работу

# Цвета для лучшей читаемости
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Определяем директорию проекта
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${PROJECT_DIR}"

# Проверка существования виртуального окружения
if [ -d "${PROJECT_DIR}/venv" ]; then
    echo -e "${GREEN}[+] Обнаружено виртуальное окружение, активирую...${NC}"
    source "${PROJECT_DIR}/venv/bin/activate"
    PYTHON="${PROJECT_DIR}/venv/bin/python"
else
    echo -e "${YELLOW}[!] Виртуальное окружение не найдено, использую системный Python${NC}"
    PYTHON="python3"
fi

# Создаем каталог логов
mkdir -p "${PROJECT_DIR}/logs"
LOG_FILE="${PROJECT_DIR}/logs/bot_debug.log"
ERROR_LOG="${PROJECT_DIR}/logs/bot_stderr.log"
STARTUP_LOG="${PROJECT_DIR}/logs/startup_trace.log"

# Очищаем старые логи
echo "" > "${LOG_FILE}"
echo "" > "${ERROR_LOG}"
echo "=== ЗАПУСК БОТА $(date) ===" > "${STARTUP_LOG}"

echo -e "${GREEN}[+] Запускаю бота в отладочном режиме...${NC}"
echo -e "${YELLOW}[!] Логи записываются в ${LOG_FILE} и ${ERROR_LOG}${NC}"
echo -e "${YELLOW}[!] Трассировка запуска в ${STARTUP_LOG}${NC}"
echo -e "${YELLOW}[!] Нажмите Ctrl+C для остановки бота${NC}"

# Устанавливаем переменные окружения для отладки
export LOG_LEVEL="DEBUG"
export ENV="development"
export PYTHONVERBOSE=1

# Подготавливаем файл с патчем для трассировки
cat > "${PROJECT_DIR}/trace_patch.py" << 'EOF'
# Патч для отслеживания инициализации бота
import sys
import time
import logging
from functools import wraps

logger = logging.getLogger("startup_trace")
handler = logging.FileHandler("logs/startup_trace.log")
handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)

# Декоратор для трассировки функций
def trace_func(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        logger.debug(f"СТАРТ: {func.__module__}.{func.__name__}")
        try:
            result = func(*args, **kwargs)
            end_time = time.time()
            logger.debug(f"ЗАВЕРШЕНО: {func.__module__}.{func.__name__} за {end_time - start_time:.2f}с")
            return result
        except Exception as e:
            end_time = time.time()
            logger.error(f"ОШИБКА: {func.__module__}.{func.__name__} - {str(e)} за {end_time - start_time:.2f}с")
            raise
    return wrapper

# Патчим критичные функции в bot.py
try:
    import bot
    
    # Патчим create_bot_and_dispatcher
    original_create_bot = bot.create_bot_and_dispatcher
    bot.create_bot_and_dispatcher = trace_func(original_create_bot)
    
    # Патчим main
    if hasattr(bot, 'main'):
        original_main = bot.main
        bot.main = trace_func(original_main)
    
    # Патчим register_handlers
    original_register = bot.register_handlers
    bot.register_handlers = trace_func(original_register)
    
    # Трассируем API-клиенты
    try:
        import app.config
        from app.config import get_ocr_client, get_chat_client
        
        app.config.get_ocr_client = trace_func(get_ocr_client)
        app.config.get_chat_client = trace_func(get_chat_client)
        
        logger.debug("Успешно добавлена трассировка к API клиентам")
    except Exception as e:
        logger.error(f"Ошибка при патче API клиентов: {str(e)}")
    
    logger.debug("Успешно добавлена трассировка к ключевым функциям")
except Exception as e:
    logger.error(f"Ошибка добавления трассировки: {str(e)}")
EOF

# Запускаем бота с трассировкой и отладочными выводами
echo -e "${BLUE}[*] $(date +%H:%M:%S) - Запуск бота с трассировкой...${NC}" | tee -a "${STARTUP_LOG}"
PYTHONPATH="${PROJECT_DIR}" "${PYTHON}" -c "import trace_patch" 2>> "${STARTUP_LOG}"
echo -e "${BLUE}[*] $(date +%H:%M:%S) - Патч трассировки установлен${NC}" | tee -a "${STARTUP_LOG}"

echo -e "${BLUE}[*] $(date +%H:%M:%S) - Запуск основного процесса...${NC}" | tee -a "${STARTUP_LOG}"
"${PYTHON}" -X dev bot.py 2>&1 | tee -a "${LOG_FILE}" "${ERROR_LOG}" 