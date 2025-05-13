# Руководство по развертыванию Nota-v3

Это руководство описывает процесс развертывания Nota-v3 на удаленном сервере с использованием Docker и Docker Compose.

## Предварительные требования

- Сервер на базе Linux (Ubuntu 20.04 или новее рекомендуется)
- Docker и Docker Compose установлены
- Доступ к серверу через SSH
- Доменное имя (опционально, для настройки SSL)

## Шаги для развертывания

### 1. Клонирование репозитория

```bash
git clone https://github.com/Enthusiasm-c/Nota-v3-.git
cd Nota-v3-
git checkout remove-image-preprocessing
```

### 2. Настройка переменных окружения

```bash
cp .env.docker .env
```

Отредактируйте файл `.env` и укажите необходимые переменные:

- `TELEGRAM_TOKEN` - токен вашего Telegram бота (от @BotFather)
- `OPENAI_OCR_KEY` - ключ API OpenAI для OCR
- `OPENAI_CHAT_KEY` - ключ API OpenAI для чат-функций (может быть тем же, что и OCR)
- `OPENAI_ASSISTANT_ID` - ID ассистента OpenAI (если используется)
- `SYRVE_*` - данные для подключения к Syrve (если используется)
- `ADMIN_CHAT_ID` - ID чата администратора для уведомлений

### 3. Сборка и запуск контейнеров

```bash
docker-compose up -d
```

Это запустит следующие сервисы:
- `nota-bot` - основное приложение бота
- `redis` - кеш для данных и состояний
- `prometheus` - система мониторинга метрик (опционально)
- `grafana` - визуализация метрик (опционально)

### 4. Проверка работоспособности

```bash
docker-compose ps
```

Все сервисы должны иметь статус "Up".

Для просмотра логов бота:

```bash
docker-compose logs -f nota-bot
```

### 5. Доступ к мониторингу

- Prometheus: http://your-server-ip:9090
- Grafana: http://your-server-ip:3000 (логин: admin, пароль указан в .env)

## Управление сервисом

### Перезапуск бота

```bash
docker-compose restart nota-bot
```

### Обновление до новой версии

```bash
git pull
docker-compose down
docker-compose build nota-bot
docker-compose up -d
```

### Остановка всех сервисов

```bash
docker-compose down
```

## Резервное копирование

Важные данные, которые следует регулярно копировать:

- Директория `data/` - содержит базы данных CSV
- Директория `logs/` - логи работы бота
- Том Redis `redis-data` - хранит кеш

Пример скрипта резервного копирования:

```bash
#!/bin/bash
BACKUP_DIR="/backups/nota-v3-$(date +%Y%m%d)"
mkdir -p $BACKUP_DIR

# Копирование файлов
cp -r data $BACKUP_DIR/
cp -r logs $BACKUP_DIR/

# Снапшот Redis
docker-compose exec redis redis-cli SAVE
```

## Устранение неполадок

### Проблемы с подключением к Telegram API

Проверьте правильность токена бота и наличие доступа к api.telegram.org.

### Проблемы с OCR

Проверьте валидность ключа OpenAI и лимиты API.

### Недостаточно памяти/CPU

Увеличьте лимиты ресурсов в `docker-compose.yml`.

## Мониторинг и обслуживание

### Основные метрики для мониторинга

- Количество обработанных инвойсов
- Время обработки OCR
- Попадания в кеш
- Ошибки OCR и API

### Действия по обслуживанию

- Регулярная очистка старых логов
- Проверка размера данных в Redis
- Обновление зависимостей и образов Docker