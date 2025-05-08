#!/bin/bash

# fix_bot_running.sh - Скрипт для исправления проблемы с дублирующимися процессами бота
# Останавливает все запущенные экземпляры и перезапускает службу

# Цвета для лучшей читаемости
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}[+] Начинаю проверку и исправление процессов бота${NC}"

# Останавливаем службу systemd
echo -e "${YELLOW}[*] Останавливаю службу nota-bot...${NC}"
sudo systemctl stop nota-bot

# Ищем все процессы python, связанные с ботом
echo -e "${YELLOW}[*] Ищу запущенные экземпляры бота...${NC}"
BOT_PIDS=$(ps aux | grep "[p]ython.*bot.py" | awk '{print $2}')

if [ -z "$BOT_PIDS" ]; then
    echo -e "${GREEN}[+] Активных процессов бота не найдено${NC}"
else
    # Отправляем SIGINT для корректного завершения
    echo -e "${YELLOW}[*] Найдены запущенные экземпляры бота. Отправляю SIGINT...${NC}"
    for pid in $BOT_PIDS; do
        echo -e "  - Останавливаю процесс $pid"
        kill -SIGINT $pid
    done
    
    # Даем небольшую паузу для корректного завершения
    sleep 3
    
    # Проверяем, остались ли процессы, и принудительно завершаем если нужно
    REMAINING_PIDS=$(ps aux | grep "[p]ython.*bot.py" | awk '{print $2}')
    if [ -n "$REMAINING_PIDS" ]; then
        echo -e "${YELLOW}[*] Некоторые процессы не завершились. Отправляю SIGKILL...${NC}"
        for pid in $REMAINING_PIDS; do
            echo -e "  - Принудительно останавливаю процесс $pid"
            kill -9 $pid
        done
    fi
    
    # Финальная проверка
    FINAL_CHECK=$(ps aux | grep "[p]ython.*bot.py" | awk '{print $2}')
    if [ -z "$FINAL_CHECK" ]; then
        echo -e "${GREEN}[+] Все процессы бота успешно остановлены${NC}"
    else
        echo -e "${RED}[-] Некоторые процессы все еще активны! Пожалуйста, остановите их вручную${NC}"
        ps aux | grep "[p]ython.*bot.py"
    fi
fi

# Чистим кэш Redis
echo -e "${YELLOW}[*] Очищаю кэш Redis...${NC}"
if command -v redis-cli &> /dev/null; then
    # Очищаем только ключи, относящиеся к боту
    redis-cli KEYS "nota:*" | xargs -r redis-cli DEL
    redis-cli KEYS "bot:*" | xargs -r redis-cli DEL
    echo -e "${GREEN}[+] Кэш Redis очищен${NC}"
else
    echo -e "${YELLOW}[!] redis-cli не найден, пропускаю очистку Redis${NC}"
fi

# Очищаем временные файлы
echo -e "${YELLOW}[*] Очищаю временные файлы...${NC}"
rm -rf /opt/nota-bot/tmp/*
echo -e "${GREEN}[+] Временные файлы очищены${NC}"

# Даем небольшую паузу перед запуском
sleep 2

# Перезапускаем службу
echo -e "${YELLOW}[*] Перезапускаю службу nota-bot...${NC}"
sudo systemctl daemon-reload
sudo systemctl start nota-bot
sleep 2

# Проверяем статус службы
echo -e "${YELLOW}[*] Проверяю статус службы...${NC}"
systemctl status nota-bot | head -n 3

echo -e "\n${GREEN}[+] Операции завершены. Проверьте логи бота:${NC}"
echo -e "    tail -f /opt/nota-bot/logs/bot_stderr.log"
echo -e "    journalctl -u nota-bot -f"

# Самоуничтожаемся после выполнения
rm -- "$0" 