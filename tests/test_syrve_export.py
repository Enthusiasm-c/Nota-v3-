#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Тестовый скрипт для отправки накладной в Syrve API
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime

import httpx
from dotenv import load_dotenv

# Добавляем корневую директорию проекта в PYTHONPATH
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from openai import AsyncOpenAI

from app.syrve_client import SyrveClient, generate_invoice_xml

# Настройка логирования
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()

# Тестовые данные накладной
TEST_INVOICE_DATA = {
    "supplier": "Redhot Trading",
    "supplier_id": "598d46cf-e2fe-c9ea-0158-9c914bff9e27",  # ID реального поставщика из Syrve
    "date": datetime.now().strftime("%Y-%m-%d"),
    "number": f"TEST-{datetime.now().strftime('%Y%m%d')}-001",
    "positions": [
        {
            "name": "Chicken Breast",  # Должно соответствовать товару в Syrve
            "qty": 2.5,
            "unit": "kg",
            "price": 120000,
            "amount": 300000,
            "product_id": "ae9cd179-5037-8af0-0193-799561626edd",  # ID продукта из base_products.csv
        },
        {
            "name": "Ribeye Steak",  # Должно соответствовать товару в Syrve
            "qty": 1.5,
            "unit": "kg",
            "price": 250000,
            "amount": 375000,
            "product_id": "e4ce95c7-dd89-a700-0194-ef09ea1e3d8e",  # ID продукта из base_products.csv
        },
    ],
}


# Функция для подготовки данных накладной в формате для Syrve
def prepare_invoice_data(invoice):
    """Подготовка данных накладной для генерации XML"""

    invoice_id = invoice.get("number", f"TEST-{datetime.now().strftime('%Y%m%d')}-001")
    invoice_date = invoice.get("date", datetime.now().strftime("%Y-%m-%d"))

    # Get real configuration IDs
    conception_id = os.getenv("SYRVE_CONCEPTION_ID", "2609b25f-2180-bf98-5c1c-967664eea837")
    store_id = os.getenv("SYRVE_STORE_ID", "1239d270-c24d-430c-b7ea-62d23a34f276")
    supplier_id = os.getenv("SYRVE_DEFAULT_SUPPLIER_ID", "ec062e5a-b44a-46e5-ba58-d7e05960a184")

    # Обработка позиций
    items = []
    for position in invoice.get("positions", []):
        # Используем ID продукта из тестовых данных
        product_id = position.get("product_id")
        if not product_id:
            logger.warning(f"Пропускаем позицию без ID продукта: {position.get('name')}")
            continue

        items.append(
            {
                "product_id": product_id,
                "quantity": float(position.get("qty", 0)),
                "price": float(position.get("price", 0))
                / 1000,  # Конвертируем из миллиединиц в рубли
            }
        )

    return {
        "invoice_number": invoice_id,
        "invoice_date": invoice_date,
        "conception_id": conception_id,
        "supplier_id": supplier_id,
        "store_id": store_id,
        "items": items,
    }


async def get_store_id(syrve_client, auth_token):
    """Получение ID склада из Syrve API"""
    try:
        url = f"{syrve_client.api_url}/resto/api/corporation/stores"
        async with httpx.AsyncClient(timeout=60.0, verify=False) as client:
            response = await client.get(url, params={"key": auth_token})
            response.raise_for_status()
            stores = response.json()
            if stores and len(stores) > 0:
                # Берем первый склад из списка
                store_id = stores[0].get("id")
                logger.info(f"Получен ID склада: {store_id}")
                return store_id
            else:
                logger.warning("Список складов пуст")
                return None
    except Exception as e:
        logger.error(f"Ошибка при получении складов: {str(e)}")
        return None


async def get_conception_id(syrve_client, auth_token):
    """Получение ID концепции из Syrve API"""
    # Берем ID концепции из настроек ресторана
    try:
        url = f"{syrve_client.api_url}/resto/api/settings/restaurantSettings"
        async with httpx.AsyncClient(timeout=60.0, verify=False) as client:
            response = await client.get(url, params={"key": auth_token})
            response.raise_for_status()
            settings = response.json()
            conception_id = settings.get("corporation", {}).get("id")
            if conception_id:
                logger.info(f"Получен ID концепции: {conception_id}")
            else:
                # Если не нашли в настройках, используем реальное значение по умолчанию
                conception_id = "2609b25f-2180-bf98-5c1c-967664eea837"
                logger.warning(
                    f"ID концепции не найден, используем значение по умолчанию: {conception_id}"
                )
            return conception_id
    except Exception as e:
        logger.error(f"Ошибка при получении настроек: {str(e)}")
        # Возвращаем реальное значение по умолчанию
        return "2609b25f-2180-bf98-5c1c-967664eea837"


def generate_manual_xml(invoice_data):
    """Ручная генерация XML для Syrve, если модель OpenAI не справляется"""

    # Создаем XML с помощью стандартной библиотеки для XML
    from xml.dom.minidom import parseString
    from xml.etree.ElementTree import Element, SubElement, tostring

    # Корневой элемент
    root = Element("document")

    # Добавляем основные поля
    doc_number = SubElement(root, "documentNumber")
    doc_number.text = invoice_data.get("invoice_number", "")

    date = SubElement(root, "dateIncoming")
    date.text = invoice_data.get("invoice_date", "")

    conception = SubElement(root, "conception")
    conception.text = invoice_data.get("conception_id", "")

    supplier = SubElement(root, "supplier")
    supplier.text = invoice_data.get("supplier_id", "")

    store = SubElement(root, "defaultStore")
    store.text = invoice_data.get("store_id", "")

    # Добавляем позиции
    items = SubElement(root, "items")

    for item_data in invoice_data.get("items", []):
        item = SubElement(items, "item")

        product = SubElement(item, "product")
        product.text = item_data.get("product_id", "")

        size = SubElement(item, "size")
        size.text = str(item_data.get("quantity", 0))

        price = SubElement(item, "price")
        price.text = str(item_data.get("price", 0))

    # Преобразуем XML в строку с красивым форматированием
    rough_string = tostring(root, "utf-8")
    reparsed = parseString(rough_string)

    # Добавляем XML-декларацию вручную
    xml_declaration = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    pretty_xml = reparsed.toprettyxml(indent="  ")
    # Удаляем первую строку (стандартный заголовок minidom)
    xml_content = "\n".join(pretty_xml.split("\n")[1:])
    # Собираем итоговый XML с нашим заголовком
    formatted_xml = xml_declaration + "\n" + xml_content

    return formatted_xml


async def main():
    """Основная функция для тестирования отправки накладной в Syrve"""

    # Создаем клиента Syrve
    syrve_client = SyrveClient(
        api_url=os.getenv("SYRVE_SERVER_URL", "https://eggstra-cafe.syrve.online:443"),
        login=os.getenv("SYRVE_LOGIN", "Spotandchoosbali"),
        password=os.getenv("SYRVE_PASSWORD", "Redriver1993"),
    )

    # Initialize OpenAI client
    ocr_key = os.getenv("OPENAI_OCR_KEY", "")
    if not ocr_key:
        ocr_key = os.getenv("OPENAI_API_KEY", "")
    openai_client = AsyncOpenAI(api_key=ocr_key)

    try:
        # Получаем токен аутентификации
        logger.info("Авторизация в Syrve API...")
        auth_token = await syrve_client.auth()
        logger.info(f"Получен токен аутентификации: {auth_token[:10]}...")

        # Подготавливаем данные накладной
        invoice_data = prepare_invoice_data(TEST_INVOICE_DATA)
        logger.info(
            f"Подготовлены данные накладной: {json.dumps(invoice_data, indent=2, ensure_ascii=False)}"
        )

        # Генерируем XML для Syrve
        logger.info("Генерация XML для Syrve...")
        xml = await generate_invoice_xml(invoice_data, openai_client)
        logger.info(f"XML сгенерирован: {xml[:200]}...")

        # Отправляем накладную в Syrve
        logger.info("Отправка накладной в Syrve...")
        result = await syrve_client.import_invoice(auth_token, xml)

        # Проверяем результат
        if result.get("valid", False):
            logger.info("Накладная успешно отправлена в Syrve!")
            logger.info(f"Ответ API: {result}")
        else:
            logger.error(f"Ошибка при отправке накладной: {result}")

    except Exception as e:
        logger.exception(f"Ошибка при выполнении теста: {e}")


if __name__ == "__main__":
    asyncio.run(main())
