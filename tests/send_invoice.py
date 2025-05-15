#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Тестовый скрипт для отправки накладной в Syrve API
"""

import os
import sys
import json
import logging
import httpx
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom.minidom import parseString

# Добавляем корневую директорию проекта в PYTHONPATH
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.syrve_client import SyrveClient
from openai import AsyncOpenAI

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()

# Тестовые данные накладной
TEST_INVOICE_DATA = {
    "supplier": "Bali Buda",  # Имя поставщика из полученного списка
    "supplier_id": "61c65f89-d940-4153-8c07-488188e16d50",  # ID поставщика из списка
    "date": datetime.now().strftime("%Y-%m-%d"),
    "number": f"TEST-{datetime.now().strftime('%Y%m%d')}-001",
    "positions": [
        {
            "name": "Chicken Breast",  # Реальный товар из Syrve
            "qty": 2.5,
            "unit": "kg",
            "price": 120.0,  # Цена в рублях
            "amount": 300.0,
            "product_id": "61aa6384-2fe2-4d0c-aad8-73c5d5dc79c5"  # Корректный ID продукта из Syrve
        },
        {
            "name": "Tenderloin Beef",  # Реальный товар из Syrve
            "qty": 1.5,
            "unit": "kg",
            "price": 250.0,  # Цена в рублях
            "amount": 375.0,
            "product_id": "6c576c27-928b-45c0-95c4-2df6a98ecae8"  # Корректный ID продукта из Syrve
        }
    ]
}


async def get_store_id(client, auth_token):
    """Получение ID склада из Syrve API"""
    try:
        # Используем правильный ID склада
        store_id = "1239d270-1bbe-f64f-b7ea-5f00518ef508"  # Корректный ID склада
        logger.info(f"Используем корректный ID склада: {store_id}")
        return store_id
        
        # Для справки сохраняем код попытки получить список складов через API
        # url = f"{client.api_url}/resto/api/corporation/stores"
        # logger.info(f"Запрашиваем список складов: {url}")
        # async with httpx.AsyncClient(timeout=60.0, verify=False) as http_client:
        #     response = await http_client.get(url, params={"key": auth_token})
        #     if response.status_code == 200:
        #         stores = response.json()
        #         if stores and len(stores) > 0:
        #             store_id = stores[0].get("id")
        #             logger.info(f"Получен ID склада: {store_id}")
        #             logger.info(f"Все доступные склады: {json.dumps(stores, indent=2)}")
        #             return store_id
    except Exception as e:
        logger.error(f"Ошибка при получении складов: {str(e)}")
        # Возвращаем корректный ID в случае ошибки
        return "1239d270-1bbe-f64f-b7ea-5f00518ef508"


async def get_conception_id(client, auth_token):
    """Получение ID концепции из Syrve API"""
    try:
        # Используем известный ID концепции
        # Это значение было получено из работающей системы
        conception_id = "bf3c0590-b204-f634-e054-0017f63ab3e6"
        logger.info(f"Используем стандартный ID концепции: {conception_id}")
        return conception_id
        
        # Попытка получить настройки ресторана через API (может не работать)
        # url = f"{client.api_url}/resto/api/settings/restaurantSettings"
        # async with httpx.AsyncClient(timeout=60.0, verify=False) as http_client:
        #     response = await http_client.get(url, params={"key": auth_token})
        #     response.raise_for_status()
        #     settings = response.json()
        #     conception_id = settings.get("corporation", {}).get("id")
        #     if conception_id:
        #         logger.info(f"Получен ID концепции: {conception_id}")
        #     else:
        #         # Если не нашли в настройках, используем значение по умолчанию
        #         conception_id = "bf3c0590-b204-f634-e054-0017f63ab3e6"
        #         logger.warning(f"ID концепции не найден, используем значение по умолчанию: {conception_id}")
        #     return conception_id
    except Exception as e:
        logger.error(f"Ошибка при получении настроек: {str(e)}")
        # Возвращаем значение по умолчанию
        return "bf3c0590-b204-f634-e054-0017f63ab3e6"


def generate_xml(invoice_data):
    """Генерация XML строго по формату Syrve"""
    xml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    xml += '<document>\n'
    xml += '  <items>\n'
    for idx, item in enumerate(invoice_data.get("items", []), 1):
        xml += '    <item>\n'
        xml += f'      <num>{idx}</num>\n'
        xml += f'      <product>{item["product_id"]}</product>\n'
        xml += f'      <amount>{item["quantity"]:.2f}</amount>\n'
        xml += f'      <price>{item["price"]:.2f}</price>\n'
        xml += f'      <sum>{item["quantity"]*item["price"]:.2f}</sum>\n'
        xml += f'      <store>{invoice_data["store_id"]}</store>\n'
        xml += '    </item>\n'
    xml += '  </items>\n'
    xml += f'  <supplier>{invoice_data["supplier_id"]}</supplier>\n'
    xml += f'  <defaultStore>{invoice_data["store_id"]}</defaultStore>\n'
    if invoice_data.get("invoice_number"):
        xml += f'  <documentNumber>{invoice_data["invoice_number"]}</documentNumber>\n'
    if invoice_data.get("invoice_date"):
        xml += f'  <dateIncoming>{invoice_data["invoice_date"]}T08:00:00</dateIncoming>\n'
    xml += '</document>'
    return xml


def prepare_invoice_data(invoice, store_id, conception_id):
    """Подготовка данных накладной с проверкой валидности ID и форматированием чисел"""
    invoice_id = invoice.get("number", f"TEST-{datetime.now().strftime('%Y%m%d')}-001")
    invoice_date = invoice.get("date", datetime.now().strftime("%Y-%m-%d"))
    supplier_id = invoice.get("supplier_id", "")
    # Проверка валидности ID через API (заглушка, реализовать при необходимости)
    # assert check_supplier_id_exists(supplier_id), "Supplier ID not found in Syrve"
    # assert check_store_id_exists(store_id), "Store ID not found in Syrve"
    items = []
    for position in invoice.get("positions", []):
        product_id = position.get("product_id")
        if not product_id:
            logger.warning(f"Пропускаем позицию без ID продукта: {position.get('name')}")
            continue
        quantity = float(position.get("qty", 0))
        price = float(position.get("price", 0))
        # assert check_product_id_exists(product_id), f"Product ID {product_id} not found in Syrve"
        items.append({
            "product_id": product_id,
            "quantity": quantity,
            "price": price
        })
    return {
        "invoice_number": invoice_id,
        "invoice_date": invoice_date,
        "conception_id": conception_id,
        "supplier_id": supplier_id,
        "store_id": store_id,
        "comment": "Автоматический импорт из NOTA",
        "items": items
    }

    """Подготовка данных накладной для генерации XML"""
    
    invoice_id = invoice.get("number", f"TEST-{datetime.now().strftime('%Y%m%d')}-001")
    invoice_date = invoice.get("date", datetime.now().strftime("%Y-%m-%d"))
    
    # Используем переданные ID концепции и склада
    supplier_id = invoice.get("supplier_id", "")
    
    # Обработка позиций
    items = []
    for position in invoice.get("positions", []):
        product_id = position.get("product_id")
        if not product_id:
            logger.warning(f"Пропускаем позицию без ID продукта: {position.get('name')}")
            continue
            
        # Рассчитываем сумму позиции
        quantity = float(position.get("qty", 0))
        # Цена в рублях, а не в миллиединицах, т.к. XML требует большой точности
        price = float(position.get("price", 0)) / 1000
        
        items.append({
            "product_id": product_id,
            "quantity": quantity,
            "price": price
        })
    
    return {
        "invoice_number": invoice_id,
        "invoice_date": invoice_date,
        "conception_id": conception_id,
        "supplier_id": supplier_id,
        "store_id": store_id,
        "comment": "Автоматический импорт из NOTA",
        "items": items
    }


async def main():
    """Основная функция для тестирования отправки накладной в Syrve"""
    
    # Создаем клиента Syrve с данными из переменных окружения
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
        
        # Получение ID склада
        store_id = await get_store_id(syrve_client, auth_token)
        if not store_id:
            logger.error("Не удалось получить ID склада")
            return
        
        # Получение ID концепции
        conception_id = await get_conception_id(syrve_client, auth_token)
        if not conception_id:
            logger.error("Не удалось получить ID концепции")
            return
        
        # Подготовка данных накладной
        invoice_data = prepare_invoice_data(TEST_INVOICE_DATA, store_id, conception_id)
        logger.info(f"Подготовлены данные накладной: {json.dumps(invoice_data, indent=2)}")
        
        # Генерация XML
        logger.info("Генерация XML для Syrve...")
        xml = generate_xml(invoice_data)
        logger.info(f"XML сгенерирован: {xml[:200]}...")
        
        # Вывод полного XML для анализа
        logger.info(f"Полный XML для отправки:\n{xml}")
        
        # Отправка накладной в Syrve
        logger.info("Отправка накладной в Syrve...")
        result = None
        try:
            # Проверяем соединение с API
            logger.info(f"Отправка запроса на URL: {api_url}/resto/api/documents/import/incomingInvoice")
            logger.info(f"Используемый токен аутентификации: {auth_token[:10]}...")
            
            result = await syrve_client.import_invoice(auth_token, xml)
            logger.info(f"Отправленный XML:\n{xml}")
            if result.get("valid", False):
                logger.info("✅ Накладная успешно отправлена в Syrve!")
                logger.info(f"Ответ API: {result}")
            else:
                logger.error(f"❌ Ошибка при отправке накладной: {result}")
                if "errorMessage" in result:
                    logger.error(f"Сообщение об ошибке: {result.get('errorMessage')}")
                    error_msg = result.get('errorMessage', '')
                    if "User represents store, but no linked store found" in error_msg:
                        logger.error("⚠️ Ошибка связи пользователя со складом. Пользователь не имеет доступа к указанному складу.")
                    elif "product == null" in error_msg:
                        logger.error("⚠️ Товар с указанным ID не найден в системе. Проверьте ID товара.")
                    elif "Invalid key for item" in error_msg:
                        logger.error("⚠️ Неверный формат ключа товара. Проверьте формат GUID.")
                    elif "No session assigned to current thread" in error_msg:
                        logger.error("⚠️ Ошибка сессии на сервере. Попробуйте повторить запрос позже.")
                if "additionalInfo" in result:
                    logger.error(f"Дополнительная информация: {result.get('additionalInfo')}")
                if "response" in result:
                    import re
                    resp = result.get('response', '')
                    logger.info(f"Анализ ответа: {resp[:500]}...")
                    if "<valid>false</valid>" in resp:
                        logger.error("⚠️ XML не прошел валидацию. Проверьте формат и содержимое.")
                    if "<errorInfo>" in resp:
                        error_info = re.search(r'<errorInfo>(.*?)</errorInfo>', resp)
                        if error_info:
                            logger.error(f"Детали ошибки валидации: {error_info.group(1)}")

        except Exception as e:
            logger.exception(f"Исключение при отправке накладной: {e}")
            if result:
                logger.error(f"Частичный ответ API: {result}")
    
    except Exception as e:
        logger.exception(f"Ошибка при выполнении скрипта: {e}")


if __name__ == "__main__":
    asyncio.run(main())
