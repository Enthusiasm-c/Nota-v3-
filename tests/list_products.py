#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Скрипт для получения списка продуктов из Syrve API
"""

import os
import sys
import json
import logging
import asyncio
import httpx
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

async def get_products(client, auth_token, store_id=None):
    """Получение списка продуктов из Syrve API"""
    products_url = f"{client.api_url}/resto/api/v2/entities/products/list"
    
    # Если задан ID склада, то запрашиваем остатки на этом складе
    params = {"key": auth_token}
    if store_id:
        params["storeId"] = store_id
    
    try:
        async with httpx.AsyncClient(timeout=60.0, verify=False) as http_client:
            response = await http_client.get(products_url, params=params)
            if response.status_code == 200:
                products = response.json()
                return products
            else:
                logger.error(f"Ошибка получения продуктов: статус {response.status_code}")
                logger.error(f"Ответ: {response.text}")
                return []
    except Exception as e:
        logger.error(f"Ошибка при получении продуктов: {str(e)}")
        return []

async def main():
    """Основная функция для получения списка продуктов из Syrve API"""
    
    # Получаем данные для подключения из переменных окружения
    api_url = os.getenv("SYRVE_SERVER_URL")
    login = os.getenv("SYRVE_LOGIN")
    password = os.getenv("SYRVE_PASSWORD")
    
    if not api_url or not login or not password:
        logger.error("Не заданы обязательные переменные окружения SYRVE_SERVER_URL, SYRVE_LOGIN или SYRVE_PASSWORD")
        return
    
    logger.info(f"Подключение к Syrve API: {api_url}")
    syrve_client = SyrveClient(api_url, login, password)
    
    try:
        # Авторизация в Syrve API
        logger.info("Авторизация в Syrve API...")
        auth_token = await syrve_client.auth()
        logger.info(f"Получен токен аутентификации: {auth_token[:10]}...")
        
        # ID склада для запроса продуктов
        store_id = "1239d270-1bbe-f64f-b7ea-5f00518ef508"  # Используем известный корректный ID склада
        
        # Получение списка продуктов
        logger.info(f"Запрос списка продуктов для склада {store_id}...")
        try:
            products = await get_products(syrve_client, auth_token, store_id)
            if products:
                logger.info(f"Получено {len(products)} продуктов:")
                
                # Выводим информацию о нескольких первых продуктах
                for i, product in enumerate(products[:10], 1):
                    logger.info(f"{i}. ID: {product.get('id')}, Наименование: {product.get('name')}")
                
                # Сохраняем полный ответ в JSON файл для дальнейшего анализа
                with open("products.json", "w", encoding="utf-8") as f:
                    json.dump(products, f, ensure_ascii=False, indent=2)
                    logger.info("Список продуктов сохранен в файл products.json")
            else:
                logger.error("Не удалось получить список продуктов")
        
        except Exception as e:
            logger.error(f"Ошибка при получении списка продуктов: {str(e)}")
    
    except Exception as e:
        logger.exception(f"Ошибка при выполнении скрипта: {e}")

if __name__ == "__main__":
    asyncio.run(main()) 