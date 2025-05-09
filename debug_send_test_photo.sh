#!/bin/bash

# debug_send_test_photo.sh - Скрипт для отправки тестовой фотографии боту

# Цвета для вывода
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Проверяем наличие .env файла
if [ ! -f ".env" ]; then
    echo -e "${RED}[!] Файл .env не найден.${NC}"
    exit 1
fi

# Загружаем переменные окружения
source .env

# Проверяем, что TELEGRAM_BOT_TOKEN установлен
if [ -z "$TELEGRAM_BOT_TOKEN" ]; then
    echo -e "${RED}[!] TELEGRAM_BOT_TOKEN не найден в .env файле.${NC}"
    exit 1
fi

# Проверяем, что указан тестовый файл
if [ -z "$1" ]; then
    echo -e "${YELLOW}[!] Необходимо указать путь к тестовому изображению${NC}"
    echo -e "${YELLOW}[*] Пример использования: $0 path/to/image.jpg${NC}"
    exit 1
else
    TEST_IMAGE="$1"
    if [ ! -f "$TEST_IMAGE" ]; then
        echo -e "${RED}[!] Файл $TEST_IMAGE не найден.${NC}"
        exit 1
    fi
fi

# Проверяем, есть ли ID чата для отправки
if [ -z "$CHAT_ID" ]; then
    read -p "Введите ID чата для отправки тестового изображения: " CHAT_ID
fi

echo -e "${BLUE}[*] Отправка тестового изображения $TEST_IMAGE в чат $CHAT_ID${NC}"

# Отправляем фото с помощью Telegram Bot API
curl -s -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendPhoto" \
    -F "chat_id=$CHAT_ID" \
    -F "photo=@$TEST_IMAGE" \
    -F "caption=Тестовое изображение для проверки работы OCR" > /dev/null

echo -e "${GREEN}[+] Фото отправлено! Проверьте логи бота для отслеживания обработки.${NC}"
echo -e "${YELLOW}[*] Для мониторинга обработки запустите:${NC} ./watch_bot_messages.sh" 