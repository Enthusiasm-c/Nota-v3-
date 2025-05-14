#!/usr/bin/env python3
"""
Скрипт для полного сброса состояния бота и удаления временных файлов.
Запускать перед стартом бота для очистки всех старых состояний.
"""
import os
import shutil
import glob
import time
import json
import logging
import argparse
from pathlib import Path

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('reset_bot')

def clean_temp_files():
    """Очищает все временные файлы"""
    temp_dirs = [
        'tmp',
        os.path.join(os.path.expanduser('~'), '.cache', 'nota-bot'),
        '/tmp/nota'
    ]
    
    files_removed = 0
    
    for temp_dir in temp_dirs:
        if os.path.exists(temp_dir):
            logger.info(f"Cleaning temp directory: {temp_dir}")
            try:
                # Удаляем все файлы, но сохраняем саму директорию
                for item in os.listdir(temp_dir):
                    item_path = os.path.join(temp_dir, item)
                    if os.path.isfile(item_path):
                        os.unlink(item_path)
                        files_removed += 1
                    elif os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                        files_removed += 1
                logger.info(f"Temp directory cleaned: {temp_dir}")
            except Exception as e:
                logger.error(f"Error cleaning temp directory {temp_dir}: {e}")
        else:
            # Создаем директорию если она не существует
            try:
                os.makedirs(temp_dir, exist_ok=True)
                logger.info(f"Created temp directory: {temp_dir}")
            except Exception as e:
                logger.error(f"Error creating temp directory {temp_dir}: {e}")
                
    return files_removed

def reset_redis_cache():
    """Сбрасывает кеш Redis если он используется"""
    try:
        import redis
        from app.config import settings
        
        # Проверяем, используется ли Redis
        if hasattr(settings, 'REDIS_URL') and settings.REDIS_URL:
            logger.info(f"Connecting to Redis at {settings.REDIS_URL}")
            r = redis.from_url(settings.REDIS_URL)
            
            # Очищаем только ключи, связанные с ботом
            keys_to_delete = []
            
            # Находим все ключи, которые относятся к боту
            for pattern in ['nota:*', 'fsm:*', 'ocr:*', 'cache:*', 'lock:*']:
                keys = r.keys(pattern)
                keys_to_delete.extend(keys)
            
            # Удаляем найденные ключи
            if keys_to_delete:
                r.delete(*keys_to_delete)
                logger.info(f"Deleted {len(keys_to_delete)} Redis keys")
            else:
                logger.info("No Redis keys found to delete")
                
            return len(keys_to_delete)
        else:
            logger.info("Redis not configured, skipping cache reset")
            return 0
    except ImportError:
        logger.info("Redis package not installed, skipping cache reset")
        return 0
    except Exception as e:
        logger.error(f"Error resetting Redis cache: {e}")
        return 0

def reset_memory_storage():
    """Удаляет файлы хранилища состояний FSM"""
    storage_patterns = [
        'fsm_*.json',
        'storage_*.json',
        '*.state'
    ]
    
    files_removed = 0
    
    for pattern in storage_patterns:
        for file_path in glob.glob(pattern):
            try:
                os.unlink(file_path)
                logger.info(f"Removed state file: {file_path}")
                files_removed += 1
            except Exception as e:
                logger.error(f"Error removing state file {file_path}: {e}")
                
    return files_removed

def kill_running_bots():
    """Завершает все процессы бота, которые могут быть запущены"""
    import subprocess
    
    processes_killed = 0
    
    try:
        # Находим процессы Python, которые запускают bot.py
        result = subprocess.run(
            ['ps', 'aux'], 
            capture_output=True, 
            text=True
        )
        
        for line in result.stdout.splitlines():
            if 'python' in line and 'bot.py' in line and 'nota-optimized' in line:
                # Получаем PID процесса
                pid = int(line.split()[1])
                
                logger.info(f"Killing bot process with PID {pid}")
                
                try:
                    # Отправляем SIGKILL для гарантированного завершения
                    os.kill(pid, 9)
                    processes_killed += 1
                    logger.info(f"Process {pid} killed")
                except ProcessLookupError:
                    logger.info(f"Process {pid} not found")
                except Exception as e:
                    logger.error(f"Error killing process {pid}: {e}")
    except Exception as e:
        logger.error(f"Error finding bot processes: {e}")
        
    return processes_killed

def create_webhook_reset_script():
    """Создает скрипт для сброса webhook"""
    script_path = 'reset_webhook.py'
    
    script_content = """#!/usr/bin/env python3
import asyncio
from aiogram import Bot
from dotenv import load_dotenv
import os

load_dotenv()
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

async def reset_webhook():
    if not TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN not found in environment")
        return
        
    bot = Bot(token=TOKEN)
    
    print("Deleting webhook and dropping pending updates...")
    await bot.delete_webhook(drop_pending_updates=True)
    print("Webhook deleted successfully")
    
    # Закрываем сессию бота
    await bot.session.close()
    print("Done!")

if __name__ == "__main__":
    asyncio.run(reset_webhook())
"""
    
    with open(script_path, 'w') as f:
        f.write(script_content)
        
    os.chmod(script_path, 0o755)  # Делаем скрипт исполняемым
    
    logger.info(f"Created webhook reset script: {script_path}")
    return script_path

def reset_webhook():
    """Выполняет сброс webhook"""
    import subprocess
    
    script_path = create_webhook_reset_script()
    
    try:
        logger.info("Resetting Telegram webhook...")
        result = subprocess.run(
            ['python3', script_path], 
            capture_output=True, 
            text=True
        )
        
        if result.returncode == 0:
            logger.info("Webhook reset successfully")
            logger.debug(result.stdout)
        else:
            logger.error(f"Error resetting webhook: {result.stderr}")
            
        return result.returncode == 0
    except Exception as e:
        logger.error(f"Error executing webhook reset script: {e}")
        return False

def main():
    """Основная функция для сброса состояния бота"""
    parser = argparse.ArgumentParser(description='Reset bot state and clean temporary files')
    parser.add_argument('--no-redis', action='store_true', help='Skip Redis cache reset')
    parser.add_argument('--no-temp', action='store_true', help='Skip temporary files cleanup')
    parser.add_argument('--no-kill', action='store_true', help='Skip killing running bot processes')
    parser.add_argument('--no-webhook', action='store_true', help='Skip webhook reset')
    
    args = parser.parse_args()
    
    logger.info("Starting bot state reset")
    
    # Убиваем запущенные процессы бота
    if not args.no_kill:
        processes_killed = kill_running_bots()
        logger.info(f"Killed {processes_killed} bot processes")
    
    # Сбрасываем webhook
    if not args.no_webhook:
        reset_webhook()
    
    # Очищаем временные файлы
    if not args.no_temp:
        files_removed = clean_temp_files()
        logger.info(f"Removed {files_removed} temporary files")
    
    # Сбрасываем кеш Redis
    if not args.no_redis:
        keys_deleted = reset_redis_cache()
        logger.info(f"Deleted {keys_deleted} Redis keys")
    
    # Сбрасываем хранилище состояний
    states_removed = reset_memory_storage()
    logger.info(f"Removed {states_removed} state files")
    
    logger.info("Bot state reset completed")
    
    print("\nBOT STATE RESET COMPLETED\n")
    print(f"- Processes killed: {0 if args.no_kill else processes_killed}")
    print(f"- Webhook reset: {'Skipped' if args.no_webhook else 'Done'}")
    print(f"- Temporary files removed: {0 if args.no_temp else files_removed}")
    print(f"- Redis keys deleted: {0 if args.no_redis else keys_deleted}")
    print(f"- State files removed: {states_removed}")
    print("\nYou can now safely start the bot with:\n")
    print("python3 bot.py")

if __name__ == "__main__":
    main()