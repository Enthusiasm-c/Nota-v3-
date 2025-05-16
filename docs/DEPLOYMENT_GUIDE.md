# Руководство по развертыванию Nota AI

## Требования к серверу

Для стабильной работы бота рекомендуется VPS со следующими характеристиками:
- **CPU**: 1+ vCPU
- **RAM**: 1+ GB
- **Диск**: 5+ GB SSD
- **ОС**: Ubuntu 20.04+ или Debian 11+
- **Сеть**: Статический IP-адрес
- **Software**: Python 3.10+, Docker (опционально)

## Подготовка сервера

### Базовая настройка

1. **Обновление пакетов**:
   ```bash
   sudo apt update && sudo apt upgrade -y
   ```

2. **Установка зависимостей**:
   ```bash
   sudo apt install -y python3-pip python3-venv git nginx
   ```

3. **Создание пользователя для бота**:
   ```bash
   sudo useradd -m -s /bin/bash notabot
   sudo usermod -aG sudo notabot
   ```

### Настройка брандмауэра

```bash
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

## Установка проекта

### Получение кода

1. **Клонирование репозитория**:
   ```bash
   sudo -i -u notabot
   cd /home/notabot
   git clone https://github.com/username/nota-optimized.git
   cd nota-optimized
   ```

2. **Настройка виртуального окружения**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

### Настройка переменных окружения

1. **Создание файла .env**:
   ```bash
   cp .env.example .env
   nano .env
   ```

2. **Необходимые переменные**:
   ```
   TELEGRAM_TOKEN=YOUR_TELEGRAM_BOT_TOKEN
   OPENAI_OCR_KEY=YOUR_OPENAI_API_KEY
   OPENAI_CHAT_KEY=YOUR_OPENAI_API_KEY
   USE_OPENAI_OCR=1
   CACHE_TTL=3600
   DATA_DIR=data
   SYRVE_API_URL=https://api.syrve.com  # Опционально
   SYRVE_LOGIN=api_user                  # Опционально
   SYRVE_PASSWORD=password               # Опционально
   ```

## Настройка systemd сервиса

1. **Создание файла сервиса**:
   ```bash
   sudo nano /etc/systemd/system/nota-bot.service
   ```

2. **Содержимое файла сервиса**:
   ```ini
   [Unit]
   Description=Nota AI Telegram Bot
   After=network.target

   [Service]
   Type=simple
   User=notabot
   WorkingDirectory=/home/notabot/nota-optimized
   ExecStart=/home/notabot/nota-optimized/venv/bin/python bot.py
   Restart=always
   RestartSec=5
   Environment=PYTHONUNBUFFERED=1

   [Install]
   WantedBy=multi-user.target
   ```

3. **Включение и запуск сервиса**:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable nota-bot.service
   sudo systemctl start nota-bot.service
   ```

## Использование скриптов автоматизации

Проект включает скрипты для упрощения деплоя и обслуживания:

### 1. Быстрая установка (скрипт setup-bot-service.sh)

```bash
cd /home/notabot/nota-optimized
chmod +x setup-bot-service.sh
./setup-bot-service.sh
```

Этот скрипт автоматически:
- Создает виртуальное окружение
- Устанавливает зависимости
- Настраивает systemd-сервис
- Запускает бота

### 2. Управление ботом (launch_bot.sh)

Скрипт для запуска, мониторинга и управления ботом:

```bash
cd /home/notabot/nota-optimized
chmod +x launch_bot.sh

# Запуск бота
./launch_bot.sh start

# Проверка статуса
./launch_bot.sh status

# Просмотр логов
./launch_bot.sh logs

# Остановка бота
./launch_bot.sh stop

# Перезапуск бота
./launch_bot.sh restart
```

## Настройка ротации логов

1. **Создание конфигурации logrotate**:
   ```bash
   sudo nano /etc/logrotate.d/nota-bot
   ```

2. **Содержимое файла**:
   ```
   /home/notabot/nota-optimized/logs/*.log {
       daily
       rotate 7
       compress
       delaycompress
       missingok
       notifempty
       create 0640 notabot notabot
   }
   ```

## Мониторинг и обслуживание

### Проверка работоспособности

```bash
# Проверка статуса сервиса
sudo systemctl status nota-bot.service

# Просмотр последних логов
sudo journalctl -u nota-bot.service -n 50 --no-pager

# Просмотр логов в реальном времени
sudo journalctl -u nota-bot.service -f
```

### Обновление бота

```bash
cd /home/notabot/nota-optimized
sudo systemctl stop nota-bot.service
git pull
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl start nota-bot.service
```

## Резервное копирование

Регулярно создавайте резервные копии важных данных:

```bash
# Скрипт для создания бэкапа
mkdir -p /home/notabot/backups
cd /home/notabot/nota-optimized
tar -czf /home/notabot/backups/nota-data-$(date +%Y%m%d).tar.gz data/
```

## Решение проблем

### Бот не запускается

1. **Проверьте логи**:
   ```bash
   sudo journalctl -u nota-bot.service -n 100
   ```

2. **Проверьте переменные окружения**:
   ```bash
   sudo systemctl cat nota-bot.service
   nano /home/notabot/nota-optimized/.env
   ```

3. **Проверьте права доступа**:
   ```bash
   sudo chown -R notabot:notabot /home/notabot/nota-optimized
   sudo chmod +x /home/notabot/nota-optimized/bot.py
   ```

### Ошибки OpenAI API

1. **Проверьте ключ API**:
   ```bash
   nano /home/notabot/nota-optimized/.env
   # Убедитесь, что OPENAI_OCR_KEY и OPENAI_CHAT_KEY корректны
   ```

2. **Проверьте доступность API**:
   ```bash
   curl -s https://api.openai.com/v1/models \
     -H "Authorization: Bearer $OPENAI_KEY" | jq
   ```

## Оптимизация производительности

### Настройка кэширования

Увеличьте время кэширования для повторного использования результатов OCR:

```bash
# В файле .env:
CACHE_TTL=7200  # 2 часа
```

### Ограничение потребления памяти

```bash
# В файле /etc/systemd/system/nota-bot.service добавьте:
[Service]
...
MemoryHigh=500M
MemoryMax=800M
```

## Безопасность

1. **Обновление системы**:
   ```bash
   sudo apt update && sudo apt upgrade -y
   ```

2. **Настройка автоматических обновлений**:
   ```bash
   sudo apt install unattended-upgrades
   sudo dpkg-reconfigure -plow unattended-upgrades
   ```

3. **Защита .env файла**:
   ```bash
   chmod 600 /home/notabot/nota-optimized/.env
   ``` 