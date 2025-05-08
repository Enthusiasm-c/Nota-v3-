# Обновление логирования на сервере

Для улучшения логирования и диагностики ошибок на сервере были внесены следующие изменения:

1. Обновлен скрипт `run_bot.sh` для перенаправления логов в journald
2. Обновлен файл `json_trace_logger.py` для расширенного логирования 
3. Изменен файл `nota-bot.service.override.conf` для настройки systemd
4. Добавлен скрипт `view_logs.sh` для удобного просмотра всех логов

## Инструкции по обновлению

### 1. Обновите файлы

```bash
# Скопируйте обновленные файлы на сервер
scp run_bot.sh user@server:/opt/nota-bot/
scp json_trace_logger.py user@server:/opt/nota-bot/
scp nota-bot.service.override.conf user@server:/etc/systemd/system/nota-bot.service.d/override.conf
scp view_logs.sh user@server:/opt/nota-bot/
```

### 2. Установите права на скрипты

```bash
# Подключитесь к серверу
ssh user@server

# Установите права на исполнение
chmod +x /opt/nota-bot/run_bot.sh
chmod +x /opt/nota-bot/view_logs.sh

# Перезагрузите конфигурацию systemd
sudo systemctl daemon-reload
```

### 3. Перезапустите бота

```bash
sudo systemctl restart nota-bot
```

## Просмотр логов

Теперь у вас есть несколько способов просмотра логов:

1. Используйте новый скрипт просмотра логов:
   ```bash
   sudo ./view_logs.sh
   ```

2. Просмотр логов в реальном времени через journalctl:
   ```bash
   sudo journalctl -u nota-bot -f
   ```

3. Просмотр только файлов логов (без journalctl):
   ```bash
   sudo ./view_logs.sh -l
   ```

4. Просмотр логов за последние N дней:
   ```bash
   sudo ./view_logs.sh -d 3  # логи за последние 3 дня
   ```

## Структура логов

После обновления, логи будут содержать больше информации:

- Трассировка исключений (тип и сообщение об ошибке)
- Файл, строка и функция, где произошла ошибка
- Идентификатор трассировки для связи логов одного запроса
- Цветное форматирование в консоли для лучшей читаемости

Все ошибки и предупреждения будут видны как в файлах логов, так и в journald, что сделает отладку бота намного проще. 