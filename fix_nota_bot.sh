#!/bin/bash
# Автоматический патч для исправления проблемы с запуском бота Nota
# Скрипт внесет необходимые изменения и сам удалится

# Цвета для вывода
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Функция для вывода с цветом
log() {
    echo -e "${BLUE}[ПАТЧ]${NC} $1"
}

error() {
    echo -e "${RED}[ОШИБКА]${NC} $1"
    exit 1
}

success() {
    echo -e "${GREEN}[УСПЕХ]${NC} $1"
}

# Проверяем права root
if [ "$EUID" -ne 0 ]; then
    error "Запустите скрипт с правами root: sudo $0"
fi

# Пути файлов
BOT_DIR="/opt/nota-bot"
BOT_FILE="$BOT_DIR/bot.py"
SERVICE_FILE="/etc/systemd/system/nota-bot.service"

# Проверяем наличие нужных файлов
if [ ! -d "$BOT_DIR" ]; then
    error "Директория бота $BOT_DIR не найдена!"
fi

if [ ! -f "$BOT_FILE" ]; then
    error "Файл бота $BOT_FILE не найден!"
fi

if [ ! -f "$SERVICE_FILE" ]; then
    error "Файл службы $SERVICE_FILE не найден!"
fi

# Создаем резервные копии
log "Создаю резервные копии..."
cp "$BOT_FILE" "${BOT_FILE}.bak"
cp "$SERVICE_FILE" "${SERVICE_FILE}.bak"
success "Резервные копии созданы"

# Модифицируем файл службы systemd
log "Обновляю файл службы systemd..."
SERVICE_CONTENT=$(cat "$SERVICE_FILE")

# Проверяем, есть ли уже KillSignal в файле
if ! grep -q "KillSignal" "$SERVICE_FILE"; then
    # Добавляем настройки остановки перед секцией [Install]
    SERVICE_CONTENT=$(echo "$SERVICE_CONTENT" | sed '/\[Install\]/i# --- Настройки быстрой остановки ---\nKillSignal=SIGINT\nTimeoutStopSec=1s\nKillMode=process\nSendSIGHUP=yes\n')
    echo "$SERVICE_CONTENT" > "$SERVICE_FILE"
    success "Файл службы обновлен"
else
    log "Настройки KillSignal уже присутствуют в файле службы"
    # Обновляем TimeoutStopSec до 1 секунды
    sed -i 's/TimeoutStopSec=.*s/TimeoutStopSec=1s/' "$SERVICE_FILE"
    success "Обновлено значение TimeoutStopSec на 1s"
fi

# Добавляем код обработчика сигналов в Python-файл
log "Добавляю обработчик сигналов в файл бота..."

# Проверяем, нет ли уже обработчика сигналов
if ! grep -q "shutdown_event = asyncio.Event()" "$BOT_FILE"; then
    # Код обработчика сигналов
    SIGNAL_HANDLER=$(cat <<'EOL'

# --------- Начало патча для обработки сигналов ---------
import signal
import sys
import asyncio

# Флаг для отслеживания состояния завершения
shutdown_event = asyncio.Event()

async def shutdown(dp, bot=None):
    """Корректное завершение работы бота и диспетчера"""
    logging.info("Начинаю корректное завершение работы бота...")
    
    try:
        # Останавливаем поллинг диспетчера (с таймаутом)
        await asyncio.wait_for(dp.stop_polling(), timeout=2.0)
        logging.info("Поллинг диспетчера остановлен")
        
        # Если бот передан, закрываем его сессию
        if bot and hasattr(bot, 'session') and bot.session:
            await bot.session.close()
            logging.info("Сессия бота закрыта")
    except Exception as e:
        logging.error(f"Ошибка при завершении работы: {str(e)}")
    finally:
        logging.info("Бот успешно остановлен")

def signal_handler(signum, frame):
    """Обработчик сигналов SIGINT/SIGTERM"""
    signal_name = signal.Signals(signum).name
    logging.info(f"Получен сигнал {signal_name}, начинаю завершение работы...")
    
    # Устанавливаем событие завершения
    if not shutdown_event.is_set():
        shutdown_event.set()
        # Выходим с кодом успешного завершения
        sys.exit(0)

# Регистрируем обработчики сигналов
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
# --------- Конец патча для обработки сигналов ---------

EOL
)

    # Вставляем код после импортов
    TEMP_FILE="${BOT_FILE}.tmp"
    awk -v signal_handler="$SIGNAL_HANDLER" '
    BEGIN { printed = 0; }
    {
        # Печатаем текущую строку
        print $0;
        
        # Если еще не вставили и это строка с импортом logging, вставляем после нее
        if (!printed && $0 ~ /import logging/) {
            print signal_handler;
            printed = 1;
        }
    }
    ' "$BOT_FILE" > "$TEMP_FILE"
    
    # Если код обработчика был вставлен, обновляем файл
    if grep -q "shutdown_event = asyncio.Event()" "$TEMP_FILE"; then
        mv "$TEMP_FILE" "$BOT_FILE"
        success "Код обработчика сигналов добавлен в файл бота"
    else
        # Если не удалось вставить после импорта logging, пробуем в начало файла
        cat <(echo "$SIGNAL_HANDLER") "$BOT_FILE" > "$TEMP_FILE"
        mv "$TEMP_FILE" "$BOT_FILE"
        success "Код обработчика сигналов добавлен в начало файла бота"
    fi
else
    log "Обработчик сигналов уже присутствует в файле бота"
fi

# Применяем изменения
log "Применяю изменения..."
systemctl daemon-reload
systemctl restart nota-bot

# Проверяем, что служба запустилась
sleep 2
if systemctl is-active --quiet nota-bot; then
    success "Служба nota-bot успешно запущена!"
else
    error "Ошибка запуска службы! Проверьте: journalctl -u nota-bot -n 50"
fi

# Выводим инструкции по отмене изменений
echo
echo -e "${YELLOW}[ИНФОРМАЦИЯ]${NC} Патч успешно применен! Бот должен теперь быстро перезапускаться."
echo -e "${YELLOW}[ИНФОРМАЦИЯ]${NC} Для проверки работы: sudo systemctl restart nota-bot"
echo -e "${YELLOW}[ИНФОРМАЦИЯ]${NC} Для просмотра логов: journalctl -fu nota-bot"
echo
echo -e "${YELLOW}[ИНФОРМАЦИЯ]${NC} В случае проблем, восстановите файлы из резервных копий:"
echo -e "sudo cp ${BOT_FILE}.bak ${BOT_FILE}"
echo -e "sudo cp ${SERVICE_FILE}.bak ${SERVICE_FILE}"
echo -e "sudo systemctl daemon-reload && sudo systemctl restart nota-bot"
echo

# Удаляем скрипт
log "Самоуничтожение скрипта через 5 секунд..."
(sleep 5 && rm -f "$0") &

success "Готово! Скрипт автоматически удалится."
exit 0 