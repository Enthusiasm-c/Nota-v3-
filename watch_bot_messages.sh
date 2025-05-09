#!/bin/bash

# watch_bot_messages.sh - Скрипт для мониторинга входящих сообщений бота

# Цвета для вывода
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}[*] Мониторинг входящих сообщений бота Nota${NC}"
echo -e "${BLUE}[*] Нажмите Ctrl+C для выхода${NC}"
echo ""

# Функция для отображения сообщений с подсветкой
tail -f logs/nota.log | grep --color=always -E "Received new photo|OCR completed|OCR error|Error processing photo" 