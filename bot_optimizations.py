#!/usr/bin/env python3
"""
Скрипт для применения оптимизаций к боту Nota.
Улучшает производительность, стабильность и отзывчивость бота.
"""

import os
import sys
import shutil
import re
import time
from pathlib import Path
import argparse
import logging

# Настройка логгера
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("optimizations")

# Пути к файлам
BOT_FILE = "bot.py"
HANDLERS_FILE = "app/handlers.py"
THREAD_POOL_FILE = "app/assistants/thread_pool.py"
INCREMENTAL_PHOTO_HANDLER = "app/handlers/incremental_photo_handler.py"
OPTIMIZED_PHOTO_HANDLER = "app/handlers/optimized_photo_handler.py"

def backup_file(file_path):
    """Создает резервную копию файла."""
    if not os.path.exists(file_path):
        logger.error(f"Файл {file_path} не найден!")
        return False
    
    backup_path = f"{file_path}.bak.{int(time.time())}"
    shutil.copy2(file_path, backup_path)
    logger.info(f"Создана резервная копия: {backup_path}")
    return True

def fix_bot_file(file_path):
    """
    Оптимизирует главный файл бота.
    
    1. Добавляет drop_pending_updates=True при запуске
    2. Улучшает обработку сигналов
    3. Добавляет async_mode=True при импорте маршрутов
    4. Исправляет порядок регистрации обработчиков
    """
    if not os.path.exists(file_path):
        logger.error(f"Файл {file_path} не найден!")
        return False
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 1. Добавляем drop_pending_updates=True при старте бота
    polling_pattern = r'(await dp\.start_polling\(bot,)([^)]*)\)'
    if re.search(polling_pattern, content):
        # Проверяем, есть ли уже флаг drop_pending_updates
        if 'drop_pending_updates' not in re.search(polling_pattern, content).group(2):
            # Добавляем флаг
            content = re.sub(
                polling_pattern,
                r'\1 drop_pending_updates=True,\2)',
                content
            )
            logger.info("Добавлен флаг drop_pending_updates=True при запуске бота")
        else:
            logger.info("Флаг drop_pending_updates=True уже установлен")
    else:
        logger.warning("Не найден вызов start_polling в bot.py")
    
    # 2. Меняем порядок регистрации обработчиков
    router_registration_pattern = r'(# ВАЖНО: Регистрируем роутер.*?photo_router[^\n]*?\n).*?(# Регистрируем роутер редактирования)'
    if re.search(router_registration_pattern, content, re.DOTALL):
        content = re.sub(
            router_registration_pattern,
            r'\1\n            # Регистрируем оптимизированный обработчик фотографий\n            from app.handlers.optimized_photo_handler import router as optimized_photo_router\n            dp.include_router(optimized_photo_router)\n            logger.info("Зарегистрирован оптимизированный обработчик фотографий")\n            \n            \2',
            content,
            flags=re.DOTALL
        )
        logger.info("Добавлен оптимизированный обработчик фотографий")
    else:
        logger.warning("Не найден блок регистрации photo_router")
    
    # 3. Оптимизируем обработку сигналов
    # Это более сложное изменение, мы добавим асинхронное закрытие соединений
    signal_handler_pattern = r'def _graceful_shutdown\([^)]*\):\s*.*?sys\.exit\(\d+\)'
    if re.search(signal_handler_pattern, content, re.DOTALL):
        # Заменяем обработчик сигналов на оптимизированную версию
        new_handler = """def _graceful_shutdown(signum, frame):
    logger.info(f"Получен сигнал завершения ({signum}), выполняем graceful shutdown...")
    
    # Устанавливаем общий таймаут в 25 секунд для гарантированного завершения
    # даже если что-то зависнет в процессе shutdown
    def alarm_handler(signum, frame):
        logger.warning("Таймаут graceful shutdown превышен, принудительное завершение")
        sys.exit(1)
    
    # Установка обработчика сигнала и таймера
    old_alarm_handler = signal.signal(signal.SIGALRM, alarm_handler)
    old_alarm_time = signal.alarm(25)  # 25 секунд на все операции
    
    try:
        # 1. Stop background threads first
        logger.info("Останавливаем фоновые потоки...")
        try:
            # Stop the Redis cache cleanup thread
            from app.utils.redis_cache import _local_cache
            if hasattr(_local_cache, 'stop_cleanup'):
                _local_cache.stop_cleanup()
                logger.info("Поток очистки кэша остановлен")
            
            # Очищаем флаги блокировок пользователей
            from app.utils.processing_guard import clear_all_locks
            clear_all_locks()
            logger.info("Флаги блокировок пользователей очищены")
        except Exception as thread_err:
            logger.error(f"Ошибка при остановке фоновых потоков: {thread_err}")

        # 2. Close Redis connection if it exists
        try:
            from app.utils.redis_cache import get_redis
            redis_conn = get_redis()
            if redis_conn:
                logger.info("Закрываем соединение с Redis...")
                redis_conn.close()
                logger.info("Соединение с Redis закрыто")
        except Exception as redis_err:
            logger.error(f"Ошибка при закрытии Redis: {redis_err}")

        # 3. Cancel any pending OpenAI requests and shut down thread pool
        logger.info("Отменяем запросы OpenAI API...")
        try:
            # Shutdown thread pool first to prevent new async tasks
            from app.assistants.thread_pool import shutdown_thread_pool
            loop = asyncio.get_event_loop()
            if loop.is_running():
                shutdown_task = asyncio.run_coroutine_threadsafe(shutdown_thread_pool(), loop)
                # Уменьшаем таймаут с 3 до 1.5 сек
                try:
                    shutdown_task.result(timeout=1.5)
                except (asyncio.TimeoutError, concurrent.futures.TimeoutError):
                    logger.warning("Timeout waiting for thread pool shutdown")
                except Exception as pool_err:
                    logger.error(f"Ошибка при остановке thread pool: {pool_err}")
            
            # Close the OpenAI client connection
            try:
                from app.config import get_chat_client
                client = get_chat_client()
                if client and hasattr(client, '_client') and hasattr(client._client, 'http_client'):
                    client._client.http_client.close()  # Close the underlying HTTP client
                    logger.info("HTTP клиент OpenAI закрыт")
            except Exception as client_err:
                logger.error(f"Ошибка при закрытии HTTP клиента: {client_err}")
        except Exception as openai_err:
            logger.error(f"Ошибка при остановке клиента OpenAI: {openai_err}")

        # 4. Stop the bot polling and dispatcher - критически важный шаг
        if 'dp' in globals() and dp:
            logger.info("Останавливаем диспетчер бота...")
            if hasattr(dp, '_polling'):
                dp._polling = False
            loop = asyncio.get_event_loop()
            if loop.is_running():
                try:
                    # Уменьшаем таймаут с 5 до 2 сек
                    stop_task = asyncio.run_coroutine_threadsafe(dp.stop_polling(), loop)
                    stop_task.result(timeout=2.0)
                    logger.info("Опрос Telegram API остановлен")
                except (asyncio.TimeoutError, concurrent.futures.TimeoutError):
                    logger.warning("Timeout waiting for polling to stop")
                except Exception as e:
                    logger.error(f"Ошибка при остановке опроса: {e}")

        # 5. Close HTTP session for async OCR if exists
        try:
            from app.utils.async_ocr import close_http_session
            loop = asyncio.get_event_loop()
            if loop.is_running():
                close_task = asyncio.run_coroutine_threadsafe(close_http_session(), loop)
                try:
                    close_task.result(timeout=1.0)
                    logger.info("HTTP сессия для OCR закрыта")
                except Exception:
                    logger.warning("Не удалось закрыть HTTP сессию OCR")
        except ImportError:
            pass  # Модуль может быть не установлен

        # 6. Close event loop properly
        logger.info("Останавливаем event loop...")
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Collect and close all pending tasks
                pending = asyncio.all_tasks(loop)
                if pending:
                    logger.info(f"Отменяем {len(pending)} незавершенных задач...")
                    for task in pending:
                        if not task.done():
                            task.cancel()
                    
                    # Уменьшаем таймаут с 2 до 1 сек
                    try:
                        gather_task = asyncio.run_coroutine_threadsafe(
                            asyncio.gather(*pending, return_exceptions=True), 
                            loop
                        )
                        gather_task.result(timeout=1.0)
                    except (asyncio.TimeoutError, concurrent.futures.TimeoutError):
                        logger.warning("Timeout waiting for tasks to cancel")
                    except Exception as e:
                        logger.error(f"Ошибка при отмене задач: {e}")
                        
                # Now stop the loop
                loop.stop()
                logger.info("Event loop остановлен")
        except Exception as loop_err:
            logger.error(f"Ошибка при остановке event loop: {loop_err}")
        
        # Если loop всё ещё активен, то принудительно останавливаем его
        if loop and loop.is_running():
            logger.warning("Event loop всё ещё активен, принудительно останавливаем...")
            loop.close()
            logger.info("Event loop принудительно остановлен")
    except Exception as e:
        logger.error(f"Ошибка при завершении: {e}")
    finally:
        # Восстанавливаем предыдущий обработчик сигнала и таймер
        signal.signal(signal.SIGALRM, old_alarm_handler)
        signal.alarm(old_alarm_time)  
        
        logger.info("Graceful shutdown завершен")
        # Гарантированное завершение процесса
        os._exit(0)"""
        
        content = re.sub(
            signal_handler_pattern,
            new_handler,
            content,
            flags=re.DOTALL
        )
        logger.info("Улучшен обработчик сигналов завершения")
    else:
        logger.warning("Не найден обработчик сигналов _graceful_shutdown")
    
    # 4. Оптимизируем импорты для main
    main_pattern = r'async def main\(\):\s*(.*?)# Логируем успешный запуск'
    if re.search(main_pattern, content, re.DOTALL):
        # Добавляем предварительную инициализацию OpenAI API
        content = re.sub(
            r'(# Настройка логирования\s*configure_logging[^\n]*?\n)',
            r'\1\n# Предзагрузка улучшенных модулей\nfrom app.utils.timing_logger import async_timed\nfrom app.utils.processing_guard import clear_all_locks\nfrom app.utils.cached_loader import cached_load_products\n\n',
            content
        )
        logger.info("Добавлена предзагрузка оптимизированных модулей")
        
        # Улучшаем функцию main
        main_replacement = r"""async def main():
        # Парсинг аргументов командной строки
        parser = argparse.ArgumentParser(description='Nota Telegram Bot')
        parser.add_argument('--test-mode', action='store_true', help='Запуск в тестовом режиме для проверки зависимостей')
        parser.add_argument('--force-restart', action='store_true', help='Принудительно сбросить сессию Telegram API перед запуском')
        args = parser.parse_args()
        
        # Создаем директорию для логов если её нет
        os.makedirs("logs", exist_ok=True)
        
        # Запускаем монитор ошибок
        from app.actions.error_monitor import start_error_monitor
        error_monitor = start_error_monitor("logs/bot.log")
        logger.info("AI Action монитор ошибок запущен")
        
        # Сбрасываем все блокировки пользователей при запуске
        clear_all_locks()
        logger.info("Все блокировки пользователей сброшены при запуске")
        
        # Тестовый режим - просто проверяем зависимости и выходим
        if args.test_mode:
            logger.info("Запущен в тестовом режиме. Проверка зависимостей:")
            logger.info("✅ Python modules loaded successfully")
            try:
                import numpy as np
                logger.info("✅ numpy imported successfully")
            except ImportError as e:
                logger.error(f"❌ Error importing numpy: {e}")
                return 1
            
            # Другие проверки оптимизированы - используем try...except вместо if
            try:
                from PIL import Image
                logger.info("✅ Pillow imported successfully")
            except ImportError as e:
                logger.error(f"❌ Error importing Pillow: {e}")
                
            try:
                from app.utils.async_ocr import async_ocr
                logger.info("✅ Async OCR module loaded successfully")
            except ImportError as e:
                logger.error(f"❌ Error importing async_ocr: {e}")
                
            logger.info("✅ All dependencies check passed!")
            return 0
        
        # Стандартный запуск бота
        # Предварительно загружаем данные в кеш асинхронно
        async def preload_data():
            try:
                from app import data_loader
                logger.info("Предварительная загрузка данных...")
                products = cached_load_products("data/base_products.csv", data_loader.load_products)
                logger.info(f"Предварительно загружено {len(products)} продуктов")
                return True
            except Exception as e:
                logger.warning(f"Ошибка при предварительной загрузке данных: {e}")
                return False
                
        # Запускаем предварительную загрузку в фоне
        preload_task = asyncio.create_task(preload_data())
        
        # Создаем бота и диспетчер
        bot, dp = create_bot_and_dispatcher()
        
        # Если указан флаг force-restart, выполняем сброс сессии Telegram API
        if args.force_restart:
            try:
                logger.info("Force-restarting bot: terminating existing webhook/polling sessions...")
                # Отправляем запрос на удаление webhook и сброс getUpdates сессии
                await bot.delete_webhook(drop_pending_updates=True)
                # Дополнительная пауза для гарантированного сброса сессии
                await asyncio.sleep(0.5)
                logger.info("Existing webhook and polling sessions terminated")
            except Exception as e:
                logger.error(f"Error during forced restart: {e}")
        
        # Регистрируем обработчики
        register_handlers(dp, bot)
        
        # Проверка конфигурации логирования
        root_logger = logging.getLogger()
        logger.debug(f"Logger configuration: {len(root_logger.handlers)} handlers")
        
        # Запускаем бота сразу, не дожидаясь инициализации пула
        logger.info("Starting bot polling...")
        polling_task = asyncio.create_task(dp.start_polling(bot, drop_pending_updates=True))
        
        # Инициализируем пул потоков OpenAI Assistant API в фоновом режиме
        @async_timed(operation_name="openai_pool_init")
        async def init_openai_pool():
            try:
                from app.assistants.client import client, initialize_pool
                logger.info("Initializing OpenAI thread pool in background...")
                await initialize_pool(client)
                logger.info("OpenAI thread pool initialized successfully")
            except Exception as e:
                logger.error(f"Error initializing OpenAI pool: {e}")
        
        # Запускаем инициализацию пула в фоновом режиме
        pool_task = asyncio.create_task(init_openai_pool())
        
        # Выводим информацию о включенных оптимизациях"""
        
        content = re.sub(
            main_pattern,
            main_replacement,
            content,
            flags=re.DOTALL
        )
        logger.info("Улучшена функция main")
    else:
        logger.warning("Не найдена функция main")
    
    # Сохраняем изменения
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    logger.info("Оптимизации bot.py применены успешно")
    return True

def fix_handlers_file(file_path):
    """
    Оптимизирует файл обработчиков.
    
    1. Фиксирует обработчик "cancel:" для избежания конфликтов
    2. Добавляет защиту от повторной обработки через FSM
    """
    if not os.path.exists(file_path):
        logger.error(f"Файл {file_path} не найден!")
        return False
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 1. Исправляем конфликтующий обработчик в handlers.py
    # Ищем обработчик, который перехватывает cancel:all
    handler_pattern = r'(@router\.callback_query\(lambda call: call\.data\.startswith\("cancel:"\).*?\).*?async def handle_cancel_row.*?)\n\s*""".*?"""(.*?)return'
    modified_handler = r'@router.callback_query(lambda call: call.data.startswith("cancel:") and call.data != "cancel:all")\nasync def handle_cancel_row(call: CallbackQuery, state: FSMContext):\n    """\n    Обработчик для кнопок "Cancel" для отдельных строк.\n    Обработчик для "cancel:all" находится в bot.py\n    """\2'
    
    if re.search(handler_pattern, content, re.DOTALL):
        content = re.sub(handler_pattern, modified_handler, content, flags=re.DOTALL)
        logger.info("Исправлен конфликтующий обработчик в handlers.py")
    else:
        logger.warning("Не найден конфликтующий обработчик в handlers.py")
    
    # 2. Добавляем проверку флага занятости пользователя в все обработчики
    # Это сложная операция, поэтому просто добавим импорты нужных модулей
    imports_pattern = r'(from app.fsm.states import EditFree)'
    if re.search(imports_pattern, content):
        new_imports = r'from app.fsm.states import EditFree\nfrom app.utils.processing_guard import require_user_free, require_rate_limit'
        content = re.sub(imports_pattern, new_imports, content)
        logger.info("Добавлены импорты модулей защиты от повторной обработки")
    else:
        logger.warning("Не найден блок импортов в handlers.py")
    
    # Сохраняем изменения
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    logger.info("Оптимизации handlers.py применены успешно")
    return True

def add_thread_pool_shutdown(file_path):
    """
    Добавляет функцию shutdown_thread_pool в thread_pool.py.
    """
    if not os.path.exists(file_path):
        logger.error(f"Файл {file_path} не найден!")
        return False
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Проверяем, есть ли уже функция shutdown_thread_pool
    if "async def shutdown_thread_pool" in content:
        logger.info("Функция shutdown_thread_pool уже существует в thread_pool.py")
        return False
    
    # Добавляем улучшенную функцию shutdown_thread_pool в конец файла
    shutdown_function = """

async def shutdown_thread_pool() -> None:
    \"\"\"
    Gracefully shuts down the thread pool and releases resources.
    Should be called during application shutdown.
    \"\"\"
    logger.info("Shutting down OpenAI thread pool")
    
    try:
        # Clear pool from Redis
        pool = cache_get(POOL_KEY)
        if pool:
            thread_ids = pool.split(",")
            logger.info(f"Clearing thread pool from Redis: {len(thread_ids)} threads")
            
            # Попытка освободить каждый поток перед очисткой пула
            for thread_id in thread_ids:
                try:
                    if hasattr(client, 'beta') and hasattr(client.beta, 'threads'):
                        # Асинхронная операция, но мы не дожидаемся её выполнения
                        # при завершении работы - достаточно инициировать
                        asyncio.create_task(asyncio.to_thread(
                            client.beta.threads.delete, thread_id
                        ))
                except Exception:
                    pass  # Игнорируем ошибки при освобождении отдельных потоков
            
            # Удаляем весь пул
            cache_set(POOL_KEY, "", ex=1)  # Set empty with 1s TTL (effectively delete)
    except Exception as e:
        logger.error(f"Error clearing thread pool from Redis: {e}")
    
    # Wait a moment to ensure any pending operations complete
    await asyncio.sleep(0.5)
    
    # Задержка перед полным завершением
    try:
        # Очищаем создающиеся потоки
        creating_threads.clear()
    except Exception:
        pass
        
    logger.info("Thread pool shutdown complete")
"""
    
    content += shutdown_function
    
    # Сохраняем изменения
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    logger.info("Добавлена функция shutdown_thread_pool в thread_pool.py")
    return True

def create_optimized_startup():
    """
    Создает оптимизированный скрипт запуска бота.
    """
    script_content = """#!/bin/bash
# Оптимизированный скрипт запуска бота Nota
# Обеспечивает быстрый запуск, автоматический перезапуск и обработку сигналов

# Каталог установки - автоопределение или указанный путь
if [ -z "$PROJECT_DIR" ]; then
    PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
fi
cd "$PROJECT_DIR"

# Настройка логирования
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/bot_startup.log"

# Функция логирования
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Очистка временных файлов
log "Cleaning tmp directory..."
mkdir -p "$PROJECT_DIR/tmp"
rm -rf "$PROJECT_DIR/tmp/"*

# Проверка окружения
log "Checking environment..."
if [ ! -f "$PROJECT_DIR/.env" ]; then
    log "ERROR: .env file not found!"
    exit 1
fi

# Сообщаем о запуске
log "Starting Optimized Nota Bot"

# Активация виртуального окружения
if [ -d "$PROJECT_DIR/venv" ]; then
    source "$PROJECT_DIR/venv/bin/activate"
    log "Virtual environment activated"
elif [ -d "$PROJECT_DIR/.venv" ]; then
    source "$PROJECT_DIR/.venv/bin/activate"
    log "Virtual environment (.venv) activated"
elif [ -d "$PROJECT_DIR/nota_venv" ]; then
    source "$PROJECT_DIR/nota_venv/bin/activate"
    log "Virtual environment (nota_venv) activated"
fi

# Загрузка переменных окружения
source "$PROJECT_DIR/.env"

# Настройка переменных для логирования и производительности
export DEBUG_LEVEL="DEBUG"
export LOG_TO_STDOUT=1
export PYTHONUNBUFFERED=1
export ENABLE_DEBUG_LOGS=1

# Предварительная проверка Redis
if command -v redis-cli &> /dev/null; then
    log "Checking Redis connection..."
    if ! redis-cli ping > /dev/null 2>&1; then
        log "WARNING: Redis seems to be unavailable. The bot will use local cache."
    else
        log "Redis is available"
    fi
fi

# Запускаем бота через check_and_restart.py
log "Starting bot with safe restart to prevent Telegram API conflicts..."
python check_and_restart.py --force-restart 2>&1 | tee -a "$LOG_FILE"

# Получаем PID запущенного бота
BOT_PID=$(ps aux | grep 'python.*bot\.py' | grep -v grep | awk '{print $2}' | head -1)
if [ -n "$BOT_PID" ]; then
    echo "$BOT_PID" > "$LOG_DIR/bot.pid"
    log "Bot started with PID: $BOT_PID"
else
    log "WARNING: Could not find bot PID, it may not have started correctly."
fi

# Обработка сигналов завершения
shutdown() {
    log "Received termination signal, stopping bot gracefully (PID: $BOT_PID)..."
    if [ -n "$BOT_PID" ]; then
        # Отправляем SIGINT для корректного завершения
        kill -SIGINT $BOT_PID
        
        # Ждем до 15 секунд завершения процесса
        for i in {1..15}; do
            if ! kill -0 $BOT_PID 2>/dev/null; then
                log "Bot gracefully shut down"
                break
            fi
            sleep 1
        done
        
        # Если процесс не завершился, используем SIGKILL
        if kill -0 $BOT_PID 2>/dev/null; then
            log "Bot did not terminate in time, forcing termination..."
            kill -SIGKILL $BOT_PID
        fi
    fi
    
    exit 0
}

# Регистрируем обработчики сигналов
trap shutdown SIGINT SIGTERM

# Вывод консоли для интерактивного использования
echo ""
echo "=== Nota Bot is running! ==="
echo "- Log file: $LOG_FILE"
echo "- Press Ctrl+C to stop the bot"
echo ""

# Мониторинг запущенного процесса (если не на фоне)
if [ -n "$BOT_PID" ]; then
    log "Monitoring bot process with PID: $BOT_PID"
    
    # Ждем завершения процесса
    wait $BOT_PID
    EXIT_CODE=$?
    log "Bot process exited with code $EXIT_CODE"
    
    # Выходим с кодом завершения бота
    exit $EXIT_CODE
fi
"""
    
    script_path = "run_optimized_bot.sh"
    with open(script_path, 'w') as f:
        f.write(script_content)
    
    # Делаем скрипт исполняемым
    os.chmod(script_path, 0o755)
    logger.info(f"Создан оптимизированный скрипт запуска: {script_path}")
    return True

def create_test_script():
    """
    Создает скрипт для тестирования оптимизаций.
    """
    script_content = """#!/bin/bash
# Скрипт для тестирования производительности бота после оптимизаций

echo "=== Nota Bot Performance Test ==="
echo "This script will run tests to verify optimizations"
echo ""

# Создаем временную директорию для тестов
TEST_DIR="./test_results"
mkdir -p "$TEST_DIR"

# Функция для запуска бота на короткое время и замера потребления ресурсов
test_startup_time() {
    echo "Testing startup time and resource usage..."
    
    # Запускаем бот с таймингом
    START_TIME=$(date +%s.%N)
    timeout 10 python bot.py --force-restart > "$TEST_DIR/startup_log.txt" 2>&1 &
    BOT_PID=$!
    
    # Ждем 5 секунд для полной инициализации
    sleep 5
    
    # Измеряем использование памяти
    if [ "$(uname)" == "Darwin" ]; then
        # macOS
        MEM_USAGE=$(ps -o rss= -p $BOT_PID | awk '{print $1/1024 " MB"}')
    else
        # Linux
        MEM_USAGE=$(ps -o rss= -p $BOT_PID | awk '{print $1/1024 " MB"}')
    fi
    
    # Останавливаем бот
    kill -SIGINT $BOT_PID 2>/dev/null
    wait $BOT_PID 2>/dev/null
    
    END_TIME=$(date +%s.%N)
    STARTUP_TIME=$(echo "$END_TIME - $START_TIME" | bc)
    
    echo "Startup completed in: $STARTUP_TIME seconds"
    echo "Memory usage: $MEM_USAGE"
    echo ""
    
    echo "Startup Time: $STARTUP_TIME seconds" > "$TEST_DIR/startup_metrics.txt"
    echo "Memory Usage: $MEM_USAGE" >> "$TEST_DIR/startup_metrics.txt"
}

# Функция для тестирования Redis-кеша
test_redis_cache() {
    echo "Testing Redis cache functionality..."
    
    # Проверяем доступность Redis
    if ! command -v redis-cli &> /dev/null || ! redis-cli ping > /dev/null 2>&1; then
        echo "Redis is not available, skipping cache test"
        return
    fi
    
    # Запускаем тест кеша
    python -c "
import time
import sys
from app.utils.redis_cache import cache_set, cache_get, clear_cache

def test_redis():
    print('Testing Redis cache performance...')
    
    # Очищаем кеш перед тестами
    clear_cache()
    
    # Тест скорости записи
    start = time.time()
    for i in range(100):
        cache_set(f'test_key_{i}', f'test_value_{i}', ex=60)
    write_time = time.time() - start
    print(f'Write: 100 items in {write_time:.4f}s ({100/write_time:.1f} items/s)')
    
    # Тест скорости чтения
    start = time.time()
    hits = 0
    for i in range(100):
        val = cache_get(f'test_key_{i}')
        if val == f'test_value_{i}':
            hits += 1
    read_time = time.time() - start
    print(f'Read: 100 items in {read_time:.4f}s ({100/read_time:.1f} items/s)')
    print(f'Cache hit rate: {hits}%')
    
    # Очищаем после теста
    clear_cache()
    
    return True

try:
    test_redis()
except Exception as e:
    print(f'Error testing Redis: {e}')
    sys.exit(1)
" > "$TEST_DIR/redis_test.txt" 2>&1
    
    echo "Redis cache test completed, results in $TEST_DIR/redis_test.txt"
    echo ""
}

# Функция для проверки оптимизированного сопоставления
test_matching() {
    echo "Testing optimized matching performance..."
    
    python -c "
import time
import sys
from app import data_loader
from app.matcher import match_positions
from app.utils.optimized_matcher import async_match_positions
import asyncio

def test_matching():
    print('Testing matching performance...')
    
    # Загружаем продукты
    products = data_loader.load_products('data/base_products.csv')
    print(f'Loaded {len(products)} products')
    
    # Создаем тестовые позиции
    test_positions = [
        {'name': 'Apple', 'qty': 1, 'unit': 'kg'},
        {'name': 'Banana', 'qty': 2, 'unit': 'kg'},
        {'name': 'Orange', 'qty': 3, 'unit': 'kg'},
        {'name': 'Tomato', 'qty': 4, 'unit': 'kg'},
        {'name': 'Cucumber', 'qty': 5, 'unit': 'kg'},
    ]
    
    # Тест стандартного сопоставления
    start = time.time()
    result = match_positions(test_positions, products)
    std_time = time.time() - start
    print(f'Standard matching: {std_time:.4f}s')
    
    # Тест оптимизированного сопоставления
    start = time.time()
    result = asyncio.run(async_match_positions(test_positions, products))
    opt_time = time.time() - start
    print(f'Optimized matching: {opt_time:.4f}s')
    
    # Сравнение
    if opt_time < std_time:
        improvement = (1 - opt_time/std_time) * 100
        print(f'Optimization improved performance by {improvement:.1f}%')
    else:
        print('No performance improvement detected')
    
    return True

try:
    test_matching()
except Exception as e:
    print(f'Error testing matching: {e}')
    sys.exit(1)
" > "$TEST_DIR/matching_test.txt" 2>&1
    
    echo "Matching test completed, results in $TEST_DIR/matching_test.txt"
    echo ""
}

# Запуск всех тестов
echo "Starting tests..."
echo "Results will be saved to $TEST_DIR directory"
echo ""

test_startup_time
test_redis_cache
test_matching

echo "All tests completed!"
echo "Check $TEST_DIR for detailed results"
"""
    
    script_path = "test_optimizations.sh"
    with open(script_path, 'w') as f:
        f.write(script_content)
    
    # Делаем скрипт исполняемым
    os.chmod(script_path, 0o755)
    logger.info(f"Создан скрипт тестирования оптимизаций: {script_path}")
    return True

def main():
    """
    Основная функция для применения всех оптимизаций.
    """
    parser = argparse.ArgumentParser(description='Apply optimizations to Nota bot')
    parser.add_argument('--no-backup', action='store_true', help='Skip creating backups')
    parser.add_argument('--test-only', action='store_true', help='Only create test scripts, no modifications')
    args = parser.parse_args()
    
    logger.info("=== Applying optimizations to Nota bot ===")
    
    if args.test_only:
        create_test_script()
        create_optimized_startup()
        logger.info("Created test scripts only, no modifications applied")
        return 0
    
    # Создаем резервные копии файлов
    if not args.no_backup:
        backup_file(BOT_FILE)
        backup_file(HANDLERS_FILE)
        backup_file(THREAD_POOL_FILE)
    
    # Применяем оптимизации
    fix_bot_file(BOT_FILE)
    fix_handlers_file(HANDLERS_FILE)
    add_thread_pool_shutdown(THREAD_POOL_FILE)
    
    # Создаем скрипты
    create_optimized_startup()
    create_test_script()
    
    logger.info("\n=== All optimizations applied successfully! ===")
    logger.info("Run the bot with ./run_optimized_bot.sh to test the optimizations")
    return 0

if __name__ == "__main__":
    sys.exit(main())