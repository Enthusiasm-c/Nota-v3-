#!/bin/bash

# fix_dependencies.sh - Скрипт для диагностики и исправления проблем с зависимостями
# Решает проблемы с запуском бота

# Цвета для лучшей читаемости
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

# Определяем директорию проекта
PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$PROJECT_DIR"

LOG_DIR="$PROJECT_DIR/logs"
DEBUG_LOG="$LOG_DIR/fix_dependencies.log"
mkdir -p "$LOG_DIR"

echo -e "${GREEN}[+] Начинаю диагностику и исправление зависимостей${NC}" | tee -a "$DEBUG_LOG"
echo -e "[+] Текущая директория: $PROJECT_DIR" | tee -a "$DEBUG_LOG"

# Вывод ошибок из логов
echo -e "\n${YELLOW}[*] Проверяю логи на наличие ошибок...${NC}" | tee -a "$DEBUG_LOG"
if [ -f "$LOG_DIR/bot_stderr.log" ]; then
    echo -e "${YELLOW}[*] Содержимое последних 20 строк лога ошибок:${NC}" | tee -a "$DEBUG_LOG"
    tail -n 20 "$LOG_DIR/bot_stderr.log" | tee -a "$DEBUG_LOG"
else
    echo -e "${YELLOW}[*] Лог ошибок не найден${NC}" | tee -a "$DEBUG_LOG"
fi

# Проверка виртуального окружения
echo -e "\n${YELLOW}[*] Проверка виртуального окружения...${NC}" | tee -a "$DEBUG_LOG"
if [ -d "$PROJECT_DIR/venv" ]; then
    echo -e "[+] Обнаружено виртуальное окружение, активирую..." | tee -a "$DEBUG_LOG"
    source "$PROJECT_DIR/venv/bin/activate"
    PIP="$PROJECT_DIR/venv/bin/pip"
    PYTHON="$PROJECT_DIR/venv/bin/python"
else
    echo -e "[+] Виртуальное окружение не найдено, использую системный Python" | tee -a "$DEBUG_LOG"
    PIP="pip3"
    PYTHON="python3"
    
    # Создаем виртуальное окружение
    echo -e "${YELLOW}[*] Создаю новое виртуальное окружение...${NC}" | tee -a "$DEBUG_LOG"
    $PYTHON -m venv venv
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}[+] Виртуальное окружение успешно создано${NC}" | tee -a "$DEBUG_LOG"
        source "$PROJECT_DIR/venv/bin/activate"
        PIP="$PROJECT_DIR/venv/bin/pip"
        PYTHON="$PROJECT_DIR/venv/bin/python"
    else
        echo -e "${RED}[-] Не удалось создать виртуальное окружение${NC}" | tee -a "$DEBUG_LOG"
    fi
fi

# Обновление pip
echo -e "\n${YELLOW}[*] Обновляю pip...${NC}" | tee -a "$DEBUG_LOG"
$PIP install --upgrade pip | tee -a "$DEBUG_LOG"

# Установка основных зависимостей
echo -e "\n${YELLOW}[*] Устанавливаю основные зависимости...${NC}" | tee -a "$DEBUG_LOG"
$PIP install -r requirements.txt | tee -a "$DEBUG_LOG"

# Дополнительно устанавливаем критические пакеты
echo -e "\n${YELLOW}[*] Устанавливаю критические пакеты отдельно...${NC}" | tee -a "$DEBUG_LOG"
$PIP install numpy opencv-python Pillow | tee -a "$DEBUG_LOG"

# Проверка установки numpy
echo -e "\n${YELLOW}[*] Проверяю установку numpy...${NC}" | tee -a "$DEBUG_LOG"
if $PYTHON -c "import numpy" 2>/dev/null; then
    echo -e "${GREEN}[+] numpy успешно установлен${NC}" | tee -a "$DEBUG_LOG"
else
    echo -e "${RED}[-] Не удалось импортировать numpy. Пробую принудительно переустановить...${NC}" | tee -a "$DEBUG_LOG"
    $PIP uninstall -y numpy | tee -a "$DEBUG_LOG"
    $PIP install numpy | tee -a "$DEBUG_LOG"
    
    if $PYTHON -c "import numpy" 2>/dev/null; then
        echo -e "${GREEN}[+] numpy успешно переустановлен${NC}" | tee -a "$DEBUG_LOG"
    else
        echo -e "${RED}[-] Не удалось установить numpy. Возможно проблема с системными зависимостями${NC}" | tee -a "$DEBUG_LOG"
    fi
fi

# Проверка установки OpenCV
echo -e "\n${YELLOW}[*] Проверяю установку OpenCV...${NC}" | tee -a "$DEBUG_LOG"
if $PYTHON -c "import cv2" 2>/dev/null; then
    echo -e "${GREEN}[+] OpenCV успешно установлен${NC}" | tee -a "$DEBUG_LOG"
else
    echo -e "${RED}[-] Не удалось импортировать OpenCV. Пробую установить другую версию...${NC}" | tee -a "$DEBUG_LOG"
    $PIP uninstall -y opencv-python opencv-python-headless | tee -a "$DEBUG_LOG"
    $PIP install opencv-python-headless | tee -a "$DEBUG_LOG"
    
    if $PYTHON -c "import cv2" 2>/dev/null; then
        echo -e "${GREEN}[+] OpenCV (headless) успешно установлен${NC}" | tee -a "$DEBUG_LOG"
    else
        echo -e "${RED}[-] Не удалось установить OpenCV. Возможно проблема с системными зависимостями${NC}" | tee -a "$DEBUG_LOG"
        echo -e "${YELLOW}[*] Пробую установить системные зависимости для OpenCV...${NC}" | tee -a "$DEBUG_LOG"
        sudo apt-get update | tee -a "$DEBUG_LOG"
        sudo apt-get install -y libgl1-mesa-glx | tee -a "$DEBUG_LOG"
        $PIP install opencv-python | tee -a "$DEBUG_LOG"
    fi
fi

# Проверка установки Pillow
echo -e "\n${YELLOW}[*] Проверяю установку Pillow...${NC}" | tee -a "$DEBUG_LOG"
if $PYTHON -c "from PIL import Image" 2>/dev/null; then
    echo -e "${GREEN}[+] Pillow успешно установлен${NC}" | tee -a "$DEBUG_LOG"
else
    echo -e "${RED}[-] Не удалось импортировать Pillow. Пробую переустановить...${NC}" | tee -a "$DEBUG_LOG"
    $PIP uninstall -y Pillow | tee -a "$DEBUG_LOG"
    $PIP install Pillow | tee -a "$DEBUG_LOG"
fi

# Пробный запуск бота для диагностики
echo -e "\n${YELLOW}[*] Тестовый запуск бота для выявления ошибок...${NC}" | tee -a "$DEBUG_LOG"
TEST_LOG="$LOG_DIR/bot_test_run.log"
$PYTHON bot.py --test-mode > "$TEST_LOG" 2>&1 &
TEST_PID=$!
sleep 5
kill -0 $TEST_PID 2>/dev/null
if [ $? -eq 0 ]; then
    echo -e "${GREEN}[+] Бот успешно запущен в тестовом режиме${NC}" | tee -a "$DEBUG_LOG"
    kill $TEST_PID
else
    echo -e "${RED}[-] Бот завершился с ошибкой при тестовом запуске${NC}" | tee -a "$DEBUG_LOG"
    echo -e "${YELLOW}[*] Вывод ошибки:${NC}" | tee -a "$DEBUG_LOG"
    cat "$TEST_LOG" | tee -a "$DEBUG_LOG"
fi

# Установка systemd service 
echo -e "\n${YELLOW}[*] Проверяю настройки systemd service...${NC}" | tee -a "$DEBUG_LOG"
if [ -f "/etc/systemd/system/nota-bot.service" ]; then
    echo -e "${GREEN}[+] Service файл найден${NC}" | tee -a "$DEBUG_LOG"
    grep "ExecStart" /etc/systemd/system/nota-bot.service | tee -a "$DEBUG_LOG"
    
    # Проверяем, что скрипт запуска существует
    SERVICE_EXEC=$(grep "ExecStart" /etc/systemd/system/nota-bot.service | sed -e 's/^.*ExecStart=//')
    if [ -f "$SERVICE_EXEC" ]; then
        echo -e "${GREEN}[+] Исполняемый файл $SERVICE_EXEC существует${NC}" | tee -a "$DEBUG_LOG"
    else
        echo -e "${RED}[-] Исполняемый файл $SERVICE_EXEC не существует!${NC}" | tee -a "$DEBUG_LOG"
        
        if [ "$SERVICE_EXEC" = "/opt/nota-bot/run_bot.sh" ]; then
            echo -e "${YELLOW}[*] Копирую run_bot.sh в нужное место...${NC}" | tee -a "$DEBUG_LOG"
            sudo cp "$PROJECT_DIR/run_bot.sh" "/opt/nota-bot/run_bot.sh"
            sudo chmod +x "/opt/nota-bot/run_bot.sh"
            echo -e "${GREEN}[+] Скрипт запуска скопирован${NC}" | tee -a "$DEBUG_LOG"
        fi
    fi
else
    echo -e "${RED}[-] Service файл не найден${NC}" | tee -a "$DEBUG_LOG"
fi

echo -e "\n${GREEN}[+] Диагностика и исправление зависимостей завершены${NC}" | tee -a "$DEBUG_LOG"
echo -e "${YELLOW}[*] Запустите бота командой: sudo systemctl restart nota-bot${NC}" | tee -a "$DEBUG_LOG"
echo -e "${YELLOW}[*] Для отладки проблем: journalctl -u nota-bot -f${NC}" | tee -a "$DEBUG_LOG" 