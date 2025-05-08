#!/bin/bash

# fix_dependencies.sh - Скрипт для установки недостающих зависимостей
# Исправляет ошибку "ModuleNotFoundError: No module named 'numpy'"
# и проверяет другие критические зависимости

# Цвета для лучшей читаемости
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

# Определяем директорию проекта
PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$PROJECT_DIR"

echo -e "${GREEN}[+] Начинаю проверку и установку зависимостей${NC}"
echo -e "[+] Текущая директория: $PROJECT_DIR"

# Проверка существования virtualenv
if [ -d "$PROJECT_DIR/venv" ]; then
    echo -e "[+] Обнаружено виртуальное окружение, активирую..."
    source "$PROJECT_DIR/venv/bin/activate"
    PYTHON="$PROJECT_DIR/venv/bin/python3"
    PIP="$PROJECT_DIR/venv/bin/pip"
else
    echo -e "${YELLOW}[!] Виртуальное окружение не найдено, использую системный Python${NC}"
    PYTHON="python3"
    PIP="pip3"
fi

# Проверяем версию Python
PYTHON_VERSION=$($PYTHON --version 2>&1)
echo -e "[+] Используется: $PYTHON_VERSION"

# Создаем файл лога
LOG_FILE="$PROJECT_DIR/logs/dependency_fix.log"
mkdir -p "$PROJECT_DIR/logs"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Запуск скрипта fix_dependencies.sh" > "$LOG_FILE"

# Проверяем requirements.txt
if [ ! -f "$PROJECT_DIR/requirements.txt" ]; then
    echo -e "${RED}[-] Файл requirements.txt не найден!${NC}" | tee -a "$LOG_FILE"
    echo -e "${YELLOW}[!] Создаю базовый requirements.txt с необходимыми зависимостями${NC}"
    
    # Создаем базовый requirements.txt с обязательными зависимостями
    cat > "$PROJECT_DIR/requirements.txt" << EOF
numpy
Pillow
opencv-python
aiogram>=3.0.0
openai>=1.0.0
python-dotenv
redis
pydantic
EOF
    echo -e "${GREEN}[+] Создан базовый requirements.txt${NC}"
fi

# Проверяем наличие numpy в requirements.txt
if ! grep -q "numpy" "$PROJECT_DIR/requirements.txt"; then
    echo -e "${YELLOW}[!] numpy не найден в requirements.txt, добавляю...${NC}" | tee -a "$LOG_FILE"
    echo "numpy" >> "$PROJECT_DIR/requirements.txt"
    echo -e "${GREEN}[+] numpy добавлен в requirements.txt${NC}"
fi

# Обновляем pip
echo -e "[+] Обновляю pip до последней версии..." | tee -a "$LOG_FILE"
$PIP install --upgrade pip >> "$LOG_FILE" 2>&1
if [ $? -ne 0 ]; then
    echo -e "${RED}[-] Ошибка при обновлении pip${NC}" | tee -a "$LOG_FILE"
else
    echo -e "${GREEN}[+] pip успешно обновлен${NC}"
fi

# Устанавливаем numpy (основная причина ошибки)
echo -e "[+] Устанавливаю numpy..." | tee -a "$LOG_FILE"
$PIP install numpy >> "$LOG_FILE" 2>&1
if [ $? -ne 0 ]; then
    echo -e "${RED}[-] Ошибка при установке numpy${NC}" | tee -a "$LOG_FILE"
else
    echo -e "${GREEN}[+] numpy успешно установлен${NC}"
fi

# Устанавливаем все зависимости из requirements.txt
echo -e "[+] Устанавливаю все зависимости из requirements.txt..." | tee -a "$LOG_FILE"
$PIP install -r "$PROJECT_DIR/requirements.txt" >> "$LOG_FILE" 2>&1
if [ $? -ne 0 ]; then
    echo -e "${RED}[-] Ошибка при установке зависимостей${NC}" | tee -a "$LOG_FILE"
    echo -e "${YELLOW}[!] Проверьте лог для деталей: $LOG_FILE${NC}"
else
    echo -e "${GREEN}[+] Все зависимости успешно установлены${NC}"
fi

# Проверяем критические зависимости
echo -e "[+] Проверяю критические зависимости..."
MISSING=0

check_module() {
    MODULE="$1"
    echo -e "  - Проверка $MODULE..." | tee -a "$LOG_FILE"
    $PYTHON -c "import $MODULE" >> "$LOG_FILE" 2>&1
    if [ $? -ne 0 ]; then
        echo -e "${RED}[-] $MODULE не найден, устанавливаю...${NC}" | tee -a "$LOG_FILE"
        $PIP install $MODULE >> "$LOG_FILE" 2>&1
        if [ $? -ne 0 ]; then
            echo -e "${RED}[-] Ошибка при установке $MODULE${NC}" | tee -a "$LOG_FILE"
            MISSING=$((MISSING+1))
        else
            echo -e "${GREEN}[+] $MODULE успешно установлен${NC}"
        fi
    else
        echo -e "${GREEN}[+] $MODULE найден${NC}"
    fi
}

# Проверяем основные модули, используемые в ошибке
check_module "numpy"
check_module "PIL"
check_module "aiogram"
check_module "openai"
check_module "redis"

# Проверяем .env файл
if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo -e "${YELLOW}[!] Файл .env не найден!${NC}" | tee -a "$LOG_FILE"
    if [ -f "$PROJECT_DIR/.env.example" ]; then
        echo -e "${YELLOW}[!] Найден .env.example, копирую как .env${NC}"
        cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
        echo -e "${YELLOW}[!] Не забудьте отредактировать .env и добавить правильные API ключи${NC}"
    else
        echo -e "${YELLOW}[!] Создаю базовый .env файл (требует редактирования)${NC}"
        cat > "$PROJECT_DIR/.env" << EOF
# Основные API ключи
TELEGRAM_BOT_TOKEN=
OPENAI_OCR_KEY=
OPENAI_CHAT_KEY=
OPENAI_ASSISTANT_ID=

# Redis настройки (если используется)
REDIS_URL=redis://localhost:6379/0

# Уровень логирования 
LOG_LEVEL=INFO
ENV=production
EOF
        echo -e "${RED}[!] ВАЖНО: Отредактируйте .env файл и добавьте нужные ключи API${NC}"
    fi
fi

# Проверяем наличие каталога tmp
if [ ! -d "$PROJECT_DIR/tmp" ]; then
    echo -e "${YELLOW}[!] Создаю директорию tmp...${NC}" | tee -a "$LOG_FILE"
    mkdir -p "$PROJECT_DIR/tmp"
fi

# Итог
if [ $MISSING -eq 0 ]; then
    echo -e "\n${GREEN}[+] Все зависимости успешно установлены!${NC}"
    echo -e "${GREEN}[+] Теперь бот должен запуститься без ошибок${NC}"
    echo -e "[+] Запустите бота командой: systemctl restart nota-bot"
else
    echo -e "\n${YELLOW}[!] Некоторые зависимости ($MISSING) не удалось установить${NC}"
    echo -e "${YELLOW}[!] Проверьте лог для деталей: $LOG_FILE${NC}"
fi

echo -e "[+] Скрипт завершил работу в $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$LOG_FILE" 