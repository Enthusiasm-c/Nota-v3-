#!/bin/bash

# view_logs.sh - Скрипт для удобного просмотра логов бота
# Автор: Claude Assistant

# Цвета для лучшей читаемости
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Определяем директорию проекта
PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
LOG_DIR="$PROJECT_DIR/logs"

# Функция показа меню
show_menu() {
    clear
    echo -e "${CYAN}=======================================${NC}"
    echo -e "${CYAN}          NOTA BOT LOG VIEWER         ${NC}"
    echo -e "${CYAN}=======================================${NC}"
    echo -e "${YELLOW}1.${NC} Просмотр ошибок (errors.log)"
    echo -e "${YELLOW}2.${NC} Просмотр OCR логов (ocr_detailed_*.log)"
    echo -e "${YELLOW}3.${NC} Просмотр основного лога (nota.log)"
    echo -e "${YELLOW}4.${NC} Просмотр системных логов (journalctl)"
    echo -e "${YELLOW}5.${NC} Поиск ошибок в OCR логах"
    echo -e "${YELLOW}6.${NC} Статистика ошибок"
    echo -e "${YELLOW}q.${NC} Выход"
    echo -e "${CYAN}=======================================${NC}"
    echo -ne "Выберите опцию: "
}

# Функция просмотра лога с пагинацией
view_log() {
    local log_file=$1
    local lines=${2:-100}

    if [ -f "$log_file" ]; then
        echo -e "${GREEN}[+] Просмотр последних $lines строк файла ${log_file}${NC}"
        echo -e "${CYAN}=======================================${NC}"
        echo -e "${YELLOW}Нажмите 'q' для выхода${NC}"
        echo -e "${CYAN}=======================================${NC}"
        tail -n $lines "$log_file" | less -R
    else
        echo -e "${RED}[-] Файл $log_file не найден${NC}"
        read -n 1 -s -r -p "Нажмите любую клавишу для продолжения..."
    fi
}

# Функция поиска в логах
search_logs() {
    local pattern=$1
    local log_file=$2
    
    if [ -f "$log_file" ]; then
        echo -e "${GREEN}[+] Поиск '$pattern' в файле ${log_file}${NC}"
        echo -e "${CYAN}=======================================${NC}"
        echo -e "${YELLOW}Нажмите 'q' для выхода${NC}"
        echo -e "${CYAN}=======================================${NC}"
        grep -i --color=always "$pattern" "$log_file" | less -R
    else
        echo -e "${RED}[-] Файл $log_file не найден${NC}"
        read -n 1 -s -r -p "Нажмите любую клавишу для продолжения..."
    fi
}

# Основной цикл
while true; do
    show_menu
    read -n 1 option
    echo ""
    
    case $option in
        1)
            view_log "$LOG_DIR/errors.log"
            ;;
        2)
            # Поиск самого свежего OCR лога
            ocr_log=$(ls -t $LOG_DIR/ocr_detailed_*.log 2>/dev/null | head -1)
            if [ -z "$ocr_log" ]; then
                echo -e "${RED}[-] OCR логи не найдены${NC}"
                read -n 1 -s -r -p "Нажмите любую клавишу для продолжения..."
            else
                view_log "$ocr_log"
            fi
            ;;
        3)
            view_log "$LOG_DIR/nota.log"
            ;;
        4)
            echo -e "${GREEN}[+] Просмотр системных логов службы nota-bot${NC}"
            echo -e "${CYAN}=======================================${NC}"
            echo -e "${YELLOW}Нажмите Ctrl+C для выхода${NC}"
            echo -e "${CYAN}=======================================${NC}"
            sudo journalctl -u nota-bot -f
            ;;
        5)
            echo -e "${YELLOW}Введите паттерн для поиска (например, 'error', 'timeout', 'exception'):${NC}"
            read search_pattern
            # Поиск самого свежего OCR лога
            ocr_log=$(ls -t $LOG_DIR/ocr_detailed_*.log 2>/dev/null | head -1)
            if [ -z "$ocr_log" ]; then
                echo -e "${RED}[-] OCR логи не найдены${NC}"
                read -n 1 -s -r -p "Нажмите любую клавишу для продолжения..."
            else
                search_logs "$search_pattern" "$ocr_log"
            fi
            ;;
        6)
            echo -e "${GREEN}[+] Статистика ошибок${NC}"
            echo -e "${CYAN}=======================================${NC}"
            echo -e "${YELLOW}Количество ошибок по типам:${NC}"
            if [ -f "$LOG_DIR/errors.log" ]; then
                grep -o "RuntimeError: [^)]*" "$LOG_DIR/errors.log" | sort | uniq -c | sort -nr
            else
                echo -e "${RED}[-] Файл логов ошибок не найден${NC}"
            fi
            echo -e "${CYAN}=======================================${NC}"
            read -n 1 -s -r -p "Нажмите любую клавишу для продолжения..."
            ;;
        q|Q)
            echo -e "${GREEN}Выход из программы.${NC}"
            exit 0
            ;;
        *)
            echo -e "${RED}[-] Неверный выбор!${NC}"
            read -n 1 -s -r -p "Нажмите любую клавишу для продолжения..."
            ;;
    esac
done 