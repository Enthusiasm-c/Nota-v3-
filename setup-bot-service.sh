#!/bin/bash

# Путь к директории приложения (будет заменен на фактический при установке)
APP_DIR="/opt/nota-optimized"
USER="root"

# Функция для создания systemd-сервиса
create_systemd_service() {
    echo "Создание systemd-сервиса для бота..."
    
    # Создание файла службы
    cat > /tmp/nota-bot.service << EOF
[Unit]
Description=Nota Telegram Bot Service
After=network.target
StartLimitIntervalSec=0

[Service]
Type=simple
User=${USER}
WorkingDirectory=${APP_DIR}
ExecStart=${APP_DIR}/launch_bot.sh monitor
Restart=always
RestartSec=10
StandardOutput=append:/var/log/nota-bot.log
StandardError=append:/var/log/nota-bot-error.log

[Install]
WantedBy=multi-user.target
EOF

    # Копирование файла службы в systemd
    sudo mv /tmp/nota-bot.service /etc/systemd/system/
    
    # Перезагрузка systemd для обнаружения нового сервиса
    sudo systemctl daemon-reload
    
    echo "Systemd-сервис создан: /etc/systemd/system/nota-bot.service"
}

# Установка службы и запуск при загрузке
install_service() {
    create_systemd_service
    
    echo "Включение автозапуска бота при загрузке системы..."
    sudo systemctl enable nota-bot.service
    
    echo "Запуск бота..."
    sudo systemctl start nota-bot.service
    
    echo "Проверка статуса..."
    sudo systemctl status nota-bot.service
    
    echo ""
    echo "==================================================="
    echo "Бот успешно установлен и запущен как systemd-сервис"
    echo "Полезные команды:"
    echo "  sudo systemctl status nota-bot.service  - проверить статус"
    echo "  sudo systemctl start nota-bot.service   - запустить бот"
    echo "  sudo systemctl stop nota-bot.service    - остановить бот"
    echo "  sudo systemctl restart nota-bot.service - перезапустить бот"
    echo "  sudo journalctl -u nota-bot.service     - просмотр логов"
    echo "==================================================="
}

# Главная функция
main() {
    echo "Начало установки бота как системного сервиса..."
    
    # Проверка прав root
    if [ "$EUID" -ne 0 ]; then
        echo "Для установки сервиса необходимы привилегии root!"
        echo "Запустите скрипт с sudo: sudo $0"
        exit 1
    fi
    
    # Проверка наличия systemd
    if ! command -v systemctl &> /dev/null; then
        echo "Systemd не обнаружен! Этот скрипт предназначен для систем с systemd."
        exit 1
    fi
    
    # Проверка наличия файла launch_bot.sh
    if [ ! -f "${APP_DIR}/launch_bot.sh" ]; then
        echo "Ошибка: файл ${APP_DIR}/launch_bot.sh не найден!"
        echo "Убедитесь, что вы указали правильный путь к директории приложения."
        exit 1
    fi
    
    # Проверка, что скрипт запуска исполняемый
    if [ ! -x "${APP_DIR}/launch_bot.sh" ]; then
        echo "Установка разрешения на исполнение для ${APP_DIR}/launch_bot.sh"
        chmod +x "${APP_DIR}/launch_bot.sh"
    fi
    
    # Установка службы
    install_service
}

# Запуск главной функции
main

exit 0 