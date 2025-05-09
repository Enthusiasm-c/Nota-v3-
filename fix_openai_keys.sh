#!/bin/bash

# fix_openai_keys.sh - Скрипт для обновления ключей API OpenAI

# Цвета для вывода
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Определяем директорию проекта
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${PROJECT_DIR}"

echo -e "${BLUE}[*] Утилита для обновления ключей API OpenAI${NC}"
echo -e "${BLUE}[*] Проверка текущих настроек...${NC}"

# Проверка существования .env файла
if [ ! -f "${PROJECT_DIR}/.env" ]; then
    echo -e "${RED}[!] Файл .env не найден. Создаю новый файл.${NC}"
    touch "${PROJECT_DIR}/.env"
fi

# Вывод текущих ключей (замаскированных)
function mask_key() {
    local key=$1
    if [ -z "$key" ]; then
        echo "(не задан)"
    else
        local masked="${key:0:4}...${key: -4}"
        echo "$masked"
    fi
}

# Текущие значения
CURRENT_OCR_KEY=$(grep -E "^OPENAI_OCR_KEY=" "${PROJECT_DIR}/.env" | cut -d= -f2)
CURRENT_CHAT_KEY=$(grep -E "^OPENAI_CHAT_KEY=" "${PROJECT_DIR}/.env" | cut -d= -f2)
CURRENT_ASSISTANT_ID=$(grep -E "^OPENAI_ASSISTANT_ID=" "${PROJECT_DIR}/.env" | cut -d= -f2)
CURRENT_VISION_ASSISTANT_ID=$(grep -E "^OPENAI_VISION_ASSISTANT_ID=" "${PROJECT_DIR}/.env" | cut -d= -f2)

echo -e "${YELLOW}Текущие настройки:${NC}"
echo -e "OPENAI_OCR_KEY = $(mask_key "$CURRENT_OCR_KEY")"
echo -e "OPENAI_CHAT_KEY = $(mask_key "$CURRENT_CHAT_KEY")"
echo -e "OPENAI_ASSISTANT_ID = $CURRENT_ASSISTANT_ID"
echo -e "OPENAI_VISION_ASSISTANT_ID = $CURRENT_VISION_ASSISTANT_ID"
echo ""

# Запрос новых значений
echo -e "${GREEN}Введите новые значения (или нажмите Enter для сохранения текущих):${NC}"
read -p "OPENAI_OCR_KEY = " NEW_OCR_KEY
read -p "OPENAI_CHAT_KEY = " NEW_CHAT_KEY
read -p "OPENAI_ASSISTANT_ID = " NEW_ASSISTANT_ID
read -p "OPENAI_VISION_ASSISTANT_ID = " NEW_VISION_ASSISTANT_ID

# Используем текущие значения, если новые не предоставлены
NEW_OCR_KEY=${NEW_OCR_KEY:-$CURRENT_OCR_KEY}
NEW_CHAT_KEY=${NEW_CHAT_KEY:-$CURRENT_CHAT_KEY}
NEW_ASSISTANT_ID=${NEW_ASSISTANT_ID:-$CURRENT_ASSISTANT_ID}
NEW_VISION_ASSISTANT_ID=${NEW_VISION_ASSISTANT_ID:-$CURRENT_VISION_ASSISTANT_ID}

# Создаем временный файл
TMP_ENV=$(mktemp)

# Копируем содержимое .env без строк, которые мы будем менять
grep -v -E "^(OPENAI_OCR_KEY|OPENAI_CHAT_KEY|OPENAI_ASSISTANT_ID|OPENAI_VISION_ASSISTANT_ID)=" "${PROJECT_DIR}/.env" > "$TMP_ENV" 2>/dev/null

# Добавляем новые значения
echo "OPENAI_OCR_KEY=$NEW_OCR_KEY" >> "$TMP_ENV"
echo "OPENAI_CHAT_KEY=$NEW_CHAT_KEY" >> "$TMP_ENV"
echo "OPENAI_ASSISTANT_ID=$NEW_ASSISTANT_ID" >> "$TMP_ENV"
echo "OPENAI_VISION_ASSISTANT_ID=$NEW_VISION_ASSISTANT_ID" >> "$TMP_ENV"

# Заменяем .env
mv "$TMP_ENV" "${PROJECT_DIR}/.env"

echo -e "${GREEN}[+] Настройки OpenAI обновлены.${NC}"
echo -e "${YELLOW}[!] Теперь перезапустите бота для применения изменений.${NC}" 