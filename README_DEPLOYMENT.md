# Инструкция по развертыванию бота на сервере Digital Ocean

Данная инструкция описывает процесс развертывания Telegram-бота на сервере Digital Ocean с автоматическим перезапуском в случае сбоев и подробным логированием.

## Подготовка сервера

1. Создайте дроплет на Digital Ocean с Ubuntu 20.04 или более новой версией
2. Подключитесь к серверу по SSH:
   ```
   ssh root@YOUR_SERVER_IP
   ```

3. Обновите систему:
   ```
   apt update && apt upgrade -y
   ```

4. Установите необходимые пакеты:
   ```
   apt install -y python3 python3-pip python3-venv git
   ```

## Загрузка и установка бота

1. Создайте директорию для бота:
   ```
   mkdir -p /opt/nota-optimized
   ```

2. Клонируйте репозиторий (или загрузите код другим способом):
   ```
   git clone YOUR_REPOSITORY_URL /opt/nota-optimized
   ```

   Альтернативно, вы можете загрузить файлы на сервер через SCP или SFTP:
   ```
   # С локального компьютера
   scp -r /path/to/nota-optimized root@YOUR_SERVER_IP:/opt/
   ```

3. Перейдите в директорию проекта:
   ```
   cd /opt/nota-optimized
   ```

4. Создайте виртуальное окружение Python и установите зависимости:
   ```
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

## Настройка скриптов запуска

В проекте есть два скрипта для автоматизации запуска:

1. `launch_bot.sh` - скрипт для запуска, мониторинга и перезапуска бота
2. `setup-bot-service.sh` - скрипт для настройки systemd-сервиса

Сделайте скрипты исполняемыми:
```
chmod +x launch_bot.sh setup-bot-service.sh
```

## Настройка переменных окружения

Если ваш бот использует переменные окружения (например, токен Telegram), создайте файл `.env` в директории проекта:
```
nano /opt/nota-optimized/.env
```

Добавьте необходимые переменные, например:
```
TELEGRAM_TOKEN=your_telegram_token
```

## Запуск бота

### Вариант 1: Запуск с помощью скрипта запуска

Этот вариант подходит для ручного управления ботом:

```
cd /opt/nota-optimized
./launch_bot.sh monitor
```

Доступные команды:
- `./launch_bot.sh start` - запуск бота
- `./launch_bot.sh stop` - остановка бота
- `./launch_bot.sh restart` - перезапуск бота
- `./launch_bot.sh status` - проверка статуса
- `./launch_bot.sh monitor` - запуск с мониторингом и автоматическим перезапуском

### Вариант 2: Установка как системный сервис (рекомендуется)

Для автоматического запуска бота при загрузке системы:

```
cd /opt/nota-optimized
sudo ./setup-bot-service.sh
```

Скрипт создаст и запустит systemd-сервис, который будет автоматически запускать бота при старте системы и перезапускать его в случае сбоев.

Управление сервисом:
```
sudo systemctl status nota-bot.service  # Проверка статуса
sudo systemctl start nota-bot.service   # Запуск
sudo systemctl stop nota-bot.service    # Остановка
sudo systemctl restart nota-bot.service # Перезапуск
```

## Просмотр логов

### Логи бота

Логи бота доступны в директории `/opt/nota-optimized/logs/`:

```
tail -f /opt/nota-optimized/logs/bot_monitor.log  # Общий лог мониторинга
tail -f /opt/nota-optimized/logs/bot_errors.log   # Лог ошибок
tail -f /opt/nota-optimized/logs/bot_restarts.log # Лог перезапусков
tail -f /opt/nota-optimized/logs/bot_stdout.log   # Стандартный вывод бота
tail -f /opt/nota-optimized/logs/bot_stderr.log   # Стандартные ошибки бота
```

### Логи системного сервиса

Если бот запущен как системный сервис:

```
sudo journalctl -u nota-bot.service       # Все логи сервиса
sudo journalctl -u nota-bot.service -f    # Следить за логами в реальном времени
sudo journalctl -u nota-bot.service -n 50 # Последние 50 записей логов
```

## Обновление бота

Для обновления бота:

1. Остановите бота или сервис:
   ```
   sudo systemctl stop nota-bot.service
   ```

2. Обновите код:
   ```
   cd /opt/nota-optimized
   git pull  # если используете git
   ```
   
   Или загрузите новые файлы через SCP/SFTP

3. Обновите зависимости, если необходимо:
   ```
   source venv/bin/activate
   pip install -r requirements.txt
   ```

4. Запустите бота снова:
   ```
   sudo systemctl start nota-bot.service
   ```

## Дополнительные настройки

### Ротация логов

Чтобы логи не занимали слишком много места, рекомендуется настроить logrotate:

```
cat > /etc/logrotate.d/nota-bot << EOF
/opt/nota-optimized/logs/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 root root
}
EOF
```

### Проверка дискового пространства

Регулярно проверяйте доступное дисковое пространство:

```
df -h
```

### Резервное копирование

Настройте регулярное резервное копирование данных бота, например, с помощью cron:

```
crontab -e
```

Добавьте строку для ежедневного резервного копирования:

```
0 2 * * * tar -czf /backup/nota-bot-$(date +\%Y\%m\%d).tar.gz /opt/nota-optimized
```

---

В случае возникновения проблем, проверьте логи бота и системные логи для выявления причин ошибок. 