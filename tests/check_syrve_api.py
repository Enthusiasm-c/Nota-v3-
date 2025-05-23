#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Проверка доступности различных эндпоинтов Syrve API
"""

import asyncio
import logging
import os
import sys

import httpx

# Добавляем корневую директорию проекта в PYTHONPATH
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.syrve_client import SyrveClient

# Настройка логирования
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def check_endpoint(client, auth_token, endpoint, description):
    """Проверка доступности эндпоинта Syrve API"""
    url = f"{client.api_url}/resto/api/{endpoint}"
    logger.info(f"Проверка {description}: {url}")

    try:
        async with httpx.AsyncClient(timeout=30.0, verify=False) as http_client:
            response = await http_client.get(url, params={"key": auth_token})

            if response.status_code == 200:
                logger.info(f"✅ {description} доступен. Статус: {response.status_code}")
                # Печатаем начало ответа для понимания формата данных
                try:
                    data = response.json()
                    logger.info(
                        f"Получено объектов: {len(data) if isinstance(data, list) else 'Не список'}"
                    )
                    logger.info(f"Пример данных: {str(data)[:150]}...")
                except Exception as e:
                    logger.info(f"Ответ не JSON: {response.text[:150]}... (ошибка: {e})")
            else:
                logger.error(f"❌ {description} недоступен. Статус: {response.status_code}")
                logger.error(f"Текст ошибки: {response.text[:200]}")
    except Exception as e:
        logger.error(f"❌ Ошибка при проверке {description}: {str(e)}")


async def main():
    """Основная функция для проверки доступности Syrve API"""

    # Создаем клиента Syrve
    api_url = os.getenv("SYRVE_SERVER_URL", "https://eggstra-cafe.syrve.online:443")
    login = os.getenv("SYRVE_LOGIN", "Spotandchoosbali")
    password = os.getenv("SYRVE_PASSWORD", "Redriver1993")

    syrve_client = SyrveClient(api_url, login, password)

    try:
        # Авторизация в Syrve API
        logger.info("Авторизация в Syrve API...")
        auth_token = await syrve_client.auth()
        logger.info(f"Получен токен аутентификации: {auth_token[:10]}...")

        # Проверка различных эндпоинтов
        await check_endpoint(syrve_client, auth_token, "products", "Список товаров")
        await check_endpoint(syrve_client, auth_token, "suppliers", "Список поставщиков")
        await check_endpoint(syrve_client, auth_token, "departments", "Список подразделений")
        await check_endpoint(syrve_client, auth_token, "corporation/stores", "Список складов")
        await check_endpoint(
            syrve_client, auth_token, "settings/restaurantSettings", "Настройки ресторана"
        )

        # Проверка эндпоинта для получения накладных (не для импорта)
        date_range = "from=2025-01-01&to=2025-05-11"
        await check_endpoint(
            syrve_client,
            auth_token,
            f"documents/export/incomingInvoice?{date_range}",
            "Экспорт накладных",
        )

    except Exception as e:
        logger.exception(f"Ошибка при выполнении скрипта: {e}")


if __name__ == "__main__":
    asyncio.run(main())
