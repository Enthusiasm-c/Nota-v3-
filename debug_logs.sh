#!/bin/bash
# debug_logs.sh - Скрипт для анализа и мониторинга логов бота
# Выводит логи с подсветкой ошибок и предупреждений

# Цвета для подсветки
RED='\033[0;31m'
YELLOW='\033[0;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Директория с логами
LOG_DIR="logs"
mkdir -p "$LOG_DIR"

# Функция для вывода справки
show_help() {
    echo "Использование: $0 [ОПЦИИ]"
    echo ""
    echo "Опции:"
    echo "  -f, --file FILE    Анализировать конкретный файл лога"
    echo "  -l, --live         Мониторинг логов в реальном времени (tail -f)"
    echo "  -e, --errors       Показать только ошибки"
    echo "  -w, --warnings     Показать только предупреждения"
    echo "  -g, --grep PATTERN Поиск по шаблону"
    echo "  -h, --help         Показать эту справку"
    echo ""
    echo "Примеры:"
    echo "  $0 -l              # Мониторинг последнего лога в реальном времени"
    echo "  $0 -f logs/bot.log # Анализ конкретного файла"
    echo "  $0 -e -l           # Мониторинг только ошибок в реальном времени"
    echo ""
}

# Функция для выделения и подсветки важных сообщений в логах
highlight_log() {
    # Подсветка различных типов сообщений
    sed -e "s/\(.*ERROR.*\)/${RED}\\1${NC}/g" \
        -e "s/\(.*CRITICAL.*\)/${RED}${BOLD}\\1${NC}/g" \
        -e "s/\(.*WARNING.*\)/${YELLOW}\\1${NC}/g" \
        -e "s/\(.*INFO.*\)/${GREEN}\\1${NC}/g" \
        -e "s/\(.*DEBUG.*\)/${BLUE}\\1${NC}/g" \
        -e "s/\(.*OCR.*\)/${CYAN}\\1${NC}/g" \
        -e "s/\(.*Exception.*\)/${RED}${BOLD}\\1${NC}/g" \
        -e "s/\(.*Traceback.*\)/${RED}${BOLD}\\1${NC}/g" \
        -e "s/\(.*error.*\)/${RED}\\1${NC}/g" \
        -e "s/\(.*failed.*\)/${RED}\\1${NC}/g" \
        -e "s/\(.*success.*\)/${GREEN}\\1${NC}/g" \
        -e "s/\(.*successfully.*\)/${GREEN}\\1${NC}/g"
}

# Функция для фильтрации логов
filter_log() {
    local content="$1"
    local filter_type="$2"
    
    case "$filter_type" in
        "errors")
            echo "$content" | grep -E "ERROR|CRITICAL|Exception|Traceback|error|failed"
            ;;
        "warnings")
            echo "$content" | grep -E "WARNING|WARN"
            ;;
        *)
            echo "$content"
            ;;
    esac
}

# Ищем самый свежий файл лога бота
get_latest_log() {
    find "$LOG_DIR" -type f -name "bot*.log" -o -name "debug*.log" | sort -r | head -n 1
}

# Обработка параметров командной строки
LOG_FILE=""
LIVE_MODE=false
FILTER_TYPE=""
GREP_PATTERN=""

# Если нет параметров, показываем справку
if [ $# -eq 0 ]; then
    show_help
    exit 0
fi

# Разбор параметров
while [[ $# -gt 0 ]]; do
    case "$1" in
        -f|--file)
            LOG_FILE="$2"
            shift 2
            ;;
        -l|--live)
            LIVE_MODE=true
            shift
            ;;
        -e|--errors)
            FILTER_TYPE="errors"
            shift
            ;;
        -w|--warnings)
            FILTER_TYPE="warnings"
            shift
            ;;
        -g|--grep)
            GREP_PATTERN="$2"
            shift 2
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            echo "Неизвестный параметр: $1"
            show_help
            exit 1
            ;;
    esac
done

# Если файл не указан, используем самый свежий
if [ -z "$LOG_FILE" ]; then
    LOG_FILE=$(get_latest_log)
    if [ -z "$LOG_FILE" ]; then
        echo -e "${RED}Ошибка: Не найдены файлы логов в директории $LOG_DIR${NC}"
        exit 1
    fi
fi

echo -e "${BOLD}Анализ лога:${NC} $LOG_FILE"
echo ""

# Проверка существования файла
if [ ! -f "$LOG_FILE" ]; then
    echo -e "${RED}Ошибка: Файл $LOG_FILE не существует${NC}"
    exit 1
fi

# Выполнение анализа лога
if [ "$LIVE_MODE" = true ]; then
    # Режим мониторинга в реальном времени
    echo -e "${BOLD}Запущен мониторинг лога в реальном времени. Нажмите Ctrl+C для остановки.${NC}"
    echo ""
    
    if [ -n "$GREP_PATTERN" ]; then
        # Мониторинг с фильтрацией по шаблону
        tail -f "$LOG_FILE" | grep --color=always -E "$GREP_PATTERN" | highlight_log
    elif [ -n "$FILTER_TYPE" ]; then
        # Мониторинг с фильтрацией по типу сообщений
        tail -f "$LOG_FILE" | filter_log /dev/stdin "$FILTER_TYPE" | highlight_log
    else
        # Обычный мониторинг
        tail -f "$LOG_FILE" | highlight_log
    fi
else
    # Режим однократного анализа
    if [ -n "$GREP_PATTERN" ]; then
        # Анализ с фильтрацией по шаблону
        cat "$LOG_FILE" | grep --color=always -E "$GREP_PATTERN" | highlight_log
    elif [ -n "$FILTER_TYPE" ]; then
        # Анализ с фильтрацией по типу сообщений
        cat "$LOG_FILE" | filter_log /dev/stdin "$FILTER_TYPE" | highlight_log
    else
        # Обычный анализ
        cat "$LOG_FILE" | highlight_log
    fi
fi

exit 0 