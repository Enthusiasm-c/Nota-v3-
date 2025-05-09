#!/bin/bash

# check_redis.sh - Скрипт для проверки статуса Redis

# Цвета для вывода
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}[*] Проверка статуса Redis сервера${NC}"

# Проверяем, запущен ли Redis
REDIS_RUNNING=false
if command -v redis-cli &> /dev/null; then
    if redis-cli ping &> /dev/null; then
        echo -e "${GREEN}[+] Redis запущен и отвечает на команды.${NC}"
        REDIS_RUNNING=true
        
        # Получаем информацию о Redis
        echo -e "${YELLOW}[*] Информация о Redis:${NC}"
        redis-cli info | grep -E 'redis_version|connected_clients|connected_slaves|used_memory_human|total_connections_received'
    else
        echo -e "${RED}[-] Redis не отвечает на команды.${NC}"
    fi
else
    echo -e "${RED}[-] Redis-cli не найден. Возможно, Redis не установлен.${NC}"
fi

# Проверяем, установлен ли Redis
if ! $REDIS_RUNNING; then
    echo -e "${YELLOW}[!] Проверка установки Redis:${NC}"
    
    # Проверяем разные менеджеры пакетов
    if command -v brew &> /dev/null; then
        echo -e "${BLUE}[*] Проверка через Homebrew...${NC}"
        if brew list redis &> /dev/null; then
            echo -e "${GREEN}[+] Redis установлен через Homebrew.${NC}"
            echo -e "${YELLOW}[!] Попробуйте запустить: brew services start redis${NC}"
        else
            echo -e "${RED}[-] Redis не установлен через Homebrew.${NC}"
            echo -e "${YELLOW}[!] Установите: brew install redis${NC}"
        fi
    elif command -v apt &> /dev/null; then
        echo -e "${BLUE}[*] Проверка через APT...${NC}"
        if apt list --installed 2>/dev/null | grep -q redis-server; then
            echo -e "${GREEN}[+] Redis установлен через APT.${NC}"
            echo -e "${YELLOW}[!] Попробуйте запустить: sudo service redis-server start${NC}"
        else
            echo -e "${RED}[-] Redis не установлен через APT.${NC}"
            echo -e "${YELLOW}[!] Установите: sudo apt install redis-server${NC}"
        fi
    elif command -v yum &> /dev/null; then
        echo -e "${BLUE}[*] Проверка через YUM...${NC}"
        if yum list installed 2>/dev/null | grep -q redis; then
            echo -e "${GREEN}[+] Redis установлен через YUM.${NC}"
            echo -e "${YELLOW}[!] Попробуйте запустить: sudo systemctl start redis${NC}"
        else
            echo -e "${RED}[-] Redis не установлен через YUM.${NC}"
            echo -e "${YELLOW}[!] Установите: sudo yum install redis${NC}"
        fi
    else
        echo -e "${RED}[-] Не удалось определить систему управления пакетами.${NC}"
    fi
    
    echo -e "\n${BLUE}[*] Альтернативные варианты для локальной разработки:${NC}"
    echo -e "${YELLOW}1. Использовать встроенный кэш - бот автоматически переключается при недоступности Redis${NC}"
    echo -e "${YELLOW}2. Использовать fakeredis (уже установлен в зависимостях)${NC}"
    echo -e "${YELLOW}3. Использовать Docker: docker run --name nota-redis -p 6379:6379 -d redis${NC}"
fi

# Проверка совместимости с ботом
echo -e "\n${BLUE}[*] Проверка настроек Redis для бота:${NC}"

# Проверяем .env файл на наличие настроек Redis
ENV_FILE=".env"
if [ -f "$ENV_FILE" ]; then
    REDIS_HOST=$(grep -E "^REDIS_HOST=" "$ENV_FILE" | cut -d= -f2)
    REDIS_PORT=$(grep -E "^REDIS_PORT=" "$ENV_FILE" | cut -d= -f2)
    
    if [ -n "$REDIS_HOST" ] || [ -n "$REDIS_PORT" ]; then
        echo -e "${GREEN}[+] Найдены настройки Redis в .env:${NC}"
        [ -n "$REDIS_HOST" ] && echo -e "   Host: $REDIS_HOST"
        [ -n "$REDIS_PORT" ] && echo -e "   Port: $REDIS_PORT"
    else
        echo -e "${YELLOW}[!] Настройки Redis не найдены в .env файле.${NC}"
        echo -e "${YELLOW}[!] Используются настройки по умолчанию: localhost:6379${NC}"
    fi
else
    echo -e "${RED}[-] Файл .env не найден.${NC}"
    echo -e "${YELLOW}[!] Используются настройки по умолчанию: localhost:6379${NC}"
fi

# Советы по исправлению
echo -e "\n${BLUE}[*] Рекомендации:${NC}"
if ! $REDIS_RUNNING; then
    echo -e "${YELLOW}1. Запустите Redis сервер для улучшения производительности бота${NC}"
    echo -e "${YELLOW}2. Для локальной разработки бот может работать без Redis (встроенный кэш)${NC}"
    echo -e "${YELLOW}3. Если хотите полностью отключить Redis, проверьте app/utils/redis_cache.py${NC}"
else
    echo -e "${GREEN}[+] Redis запущен и работает корректно.${NC}"
fi 