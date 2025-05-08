#!/bin/bash

# fix_ocr.sh - Скрипт для диагностики и исправления проблем с OCR сервисом
# Запускает тест OCR и собирает подробные логи для анализа проблемы

# Цвета для лучшей читаемости
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$PROJECT_DIR"

echo -e "${GREEN}[+] Запускаю диагностику и исправление OCR...${NC}"

# Создаем директорию для логов
mkdir -p "$PROJECT_DIR/logs"
LOG_FILE="$PROJECT_DIR/logs/ocr_debug_$(date '+%Y%m%d_%H%M%S').log"

# Проверяем наличие .env файла
if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo -e "${RED}[-] Файл .env не найден!${NC}"
    exit 1
fi

# Проверяем наличие API ключей и ID ассистента в .env
echo -e "${YELLOW}[*] Проверяю конфигурацию OCR...${NC}"
if grep -q "OPENAI_OCR_KEY" "$PROJECT_DIR/.env" && grep -q "OPENAI_VISION_ASSISTANT_ID" "$PROJECT_DIR/.env"; then
    echo -e "${GREEN}[+] Ключи API и ID ассистента найдены в .env${NC}"
else
    echo -e "${RED}[-] Отсутствуют необходимые переменные в .env!${NC}"
    echo -e "${YELLOW}[*] Необходимо добавить OPENAI_OCR_KEY и OPENAI_VISION_ASSISTANT_ID${NC}"
    exit 1
fi

# Активируем виртуальное окружение если есть
if [ -d "$PROJECT_DIR/venv" ]; then
    echo -e "${YELLOW}[*] Активирую виртуальное окружение...${NC}"
    source "$PROJECT_DIR/venv/bin/activate"
    PYTHON="$PROJECT_DIR/venv/bin/python"
else
    PYTHON="python3"
fi

# Проверяем наличие необходимых библиотек
echo -e "${YELLOW}[*] Проверяю наличие необходимых библиотек...${NC}"
$PYTHON -c "import openai" 2>/dev/null
if [ $? -ne 0 ]; then
    echo -e "${RED}[-] Библиотека openai не установлена!${NC}"
    echo -e "${YELLOW}[*] Устанавливаю openai...${NC}"
    pip install openai
fi

$PYTHON -c "from PIL import Image" 2>/dev/null
if [ $? -ne 0 ]; then
    echo -e "${RED}[-] Библиотека Pillow не установлена!${NC}"
    echo -e "${YELLOW}[*] Устанавливаю Pillow...${NC}"
    pip install Pillow
fi

# Запускаем диагностический скрипт
echo -e "${YELLOW}[*] Запускаю диагностический скрипт OCR...${NC}"
$PYTHON debug_ocr.py | tee "$LOG_FILE"

# Анализируем результаты
if grep -q "Тест OCR успешно завершен" "$LOG_FILE"; then
    echo -e "\n${GREEN}[+] Тест OCR успешно завершен!${NC}"
    echo -e "${GREEN}[+] OCR работает корректно.${NC}"
else
    echo -e "\n${RED}[-] Тест OCR завершился с ошибками!${NC}"
    
    # Анализ возможных причин
    if grep -q "Invalid content type. image_url is only supported by certain models" "$LOG_FILE"; then
        echo -e "${YELLOW}[!] Обнаружена ошибка совместимости модели с image_url. Исправлено в последней версии кода.${NC}"
    fi
    
    if grep -q "Отсутствуют обязательные переменные" "$LOG_FILE"; then
        echo -e "${RED}[-] Отсутствуют необходимые переменные окружения!${NC}"
        echo -e "${YELLOW}[*] Проверьте файл .env и наличие в нём OPENAI_OCR_KEY и OPENAI_VISION_ASSISTANT_ID${NC}"
    fi
    
    if grep -q "OPENAI_VISION_ASSISTANT_ID" "$LOG_FILE"; then
        ASSISTANT_ID=$(grep -oP "Используем ассистента: \K[^\"]*" "$LOG_FILE" | head -1)
        if [ -n "$ASSISTANT_ID" ]; then
            echo -e "${YELLOW}[*] Используется ID ассистента: $ASSISTANT_ID${NC}"
            echo -e "${YELLOW}[*] Проверьте, что этот ассистент существует и настроен правильно в OpenAI.${NC}"
        fi
    fi
    
    # Проверка на таймаут
    if grep -q "Превышен таймаут ожидания" "$LOG_FILE"; then
        echo -e "${YELLOW}[!] Обнаружен таймаут при ожидании ответа от OpenAI.${NC}"
        echo -e "${YELLOW}[*] Возможно, сервер OpenAI перегружен или у вас медленное соединение.${NC}"
        echo -e "${YELLOW}[*] Попробуйте увеличить таймаут в коде или повторить позже.${NC}"
    fi
    
    echo -e "${YELLOW}[*] Логи сохранены в файл: $LOG_FILE${NC}"
    echo -e "${YELLOW}[*] Отправьте этот файл разработчику для дальнейшего анализа.${NC}"
fi

echo -e "\n${GREEN}[+] Диагностика OCR завершена.${NC}" 