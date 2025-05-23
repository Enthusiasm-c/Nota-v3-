#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Скрипт для получения списка поставщиков из Syrve API
"""

import os
import sys
import json
import logging
import asyncio
from dotenv import load_dotenv

# Добавляем корневую директорию проекта в PYTHONPATH
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.syrve_client import SyrveClient

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()

async def main():
    """Основная функция для получения списка поставщиков из Syrve API"""
    
    # Получаем данные для подключения из переменных окружения
    api_url = os.getenv("SYRVE_SERVER_URL")
    login = os.getenv("SYRVE_LOGIN")
    password = os.getenv("SYRVE_PASSWORD")
    
    if not api_url or not login or not password:
        logger.error("Не заданы обязательные переменные окружения SYRVE_SERVER_URL, SYRVE_LOGIN или SYRVE_PASSWORD")
        return
    
    logger.info(f"Подключение к Syrve API: {api_url}, пользователь: {login}")
    syrve_client = SyrveClient(api_url, login, password)
    
    try:
        # Авторизация в Syrve API
        logger.info("Авторизация в Syrve API...")
        auth_token = await syrve_client.auth()
        logger.info(f"Получен токен аутентификации: {auth_token[:10]}...")
        
        # Получение списка поставщиков
        logger.info("Запрос списка поставщиков...")
        try:
            suppliers = await syrve_client.get_suppliers(auth_token)
            logger.info(f"Получено {len(suppliers)} поставщиков:")
            
            # Выводим информацию о поставщиках
            for i, supplier in enumerate(suppliers, 1):
                logger.info(f"{i}. ID: {supplier.get('id')}, Имя: {supplier.get('name')}")
            
            # Сохраняем полный ответ в JSON файл для дальнейшего анализа
            with open("suppliers.json", "w", encoding="utf-8") as f:
                json.dump(suppliers, f, ensure_ascii=False, indent=2)
                logger.info("Список поставщиков сохранен в файл suppliers.json")
        
        except Exception as e:
            logger.error(f"Ошибка при получении списка поставщиков: {str(e)}")
    
    except Exception as e:
        logger.exception(f"Ошибка при выполнении скрипта: {e}")

if __name__ == "__main__":
    asyncio.run(main()) 