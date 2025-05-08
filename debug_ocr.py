#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Диагностический скрипт для тестирования OCR
Запускает OCR на тестовом изображении и выводит подробные логи и информацию об ошибках
"""

import sys
import os
import logging
import time
import json
import asyncio
from pathlib import Path
from datetime import date, datetime

# Настройка логирования
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("ocr-debug")

# Включаем отладочные логи для всех модулей OpenAI и HTTP
logging.getLogger("openai").setLevel(logging.DEBUG)
logging.getLogger("httpx").setLevel(logging.DEBUG)
logging.getLogger("app.ocr").setLevel(logging.DEBUG)
logging.getLogger("app.utils.api_decorators").setLevel(logging.DEBUG)

# Функция сериализации для даты
def json_serialize(obj):
    """
    Функция-сериализатор для преобразования объектов в JSON.
    Обрабатывает типы date и datetime.
    """
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")

# Функция для асинхронного запуска OCR
async def test_ocr(image_path):
    try:
        logger.info(f"Загружаю тестовое изображение: {image_path}")
        
        # Проверка существования файла
        if not os.path.exists(image_path):
            logger.error(f"Файл не найден: {image_path}")
            return False
        
        # Загрузка изображения
        with open(image_path, "rb") as img_file:
            image_bytes = img_file.read()
            logger.info(f"Изображение загружено, размер: {len(image_bytes)} байт")
        
        # Импорт OCR модуля
        logger.info("Импортирую модуль OCR...")
        try:
            from app.ocr import call_openai_ocr
            logger.info("Модуль OCR успешно импортирован")
        except ImportError as import_err:
            logger.error(f"Ошибка импорта модуля OCR: {import_err}")
            logger.error(f"Детали ошибки: {import_err.__class__.__name__}")
            return False
        
        # Проверка конфигурации
        logger.info("Проверяю конфигурацию...")
        from app.config import settings
        
        missing_vars = []
        for var in ["OPENAI_OCR_KEY", "OPENAI_VISION_ASSISTANT_ID"]:
            if not getattr(settings, var, None):
                missing_vars.append(var)
        
        if missing_vars:
            logger.error(f"Отсутствуют обязательные переменные: {', '.join(missing_vars)}")
            return False
        
        logger.info(f"Используем ассистента: {settings.OPENAI_VISION_ASSISTANT_ID}")
        
        # Запускаем OCR
        logger.info("Запускаю OCR...")
        start_time = time.time()
        
        # Запуск с перехватом всех возможных исключений
        try:
            result = await asyncio.to_thread(call_openai_ocr, image_bytes)
            duration = time.time() - start_time
            logger.info(f"OCR успешно завершен за {duration:.2f} сек")
            logger.info(f"Результат: {len(result.positions)} позиций найдено")
            
            # Выводим результат в JSON для проверки
            print("\nРезультат OCR (JSON):")
            print(json.dumps(result.model_dump(), indent=2, ensure_ascii=False, default=json_serialize))
            return True
        except Exception as ocr_err:
            duration = time.time() - start_time
            logger.error(f"OCR завершился с ошибкой через {duration:.2f} сек")
            logger.error(f"Тип ошибки: {ocr_err.__class__.__name__}")
            logger.error(f"Сообщение ошибки: {str(ocr_err)}")
            
            # Получаем доступ к исходной ошибке через __cause__
            if hasattr(ocr_err, '__cause__') and ocr_err.__cause__:
                cause = ocr_err.__cause__
                logger.error(f"Исходная ошибка: {cause.__class__.__name__}: {str(cause)}")
                
                # Если у исходной ошибки тоже есть причина, показываем и её
                if hasattr(cause, '__cause__') and cause.__cause__:
                    root_cause = cause.__cause__
                    logger.error(f"Корневая причина: {root_cause.__class__.__name__}: {str(root_cause)}")
            
            # Подробная диагностика
            import traceback
            logger.error("Полный стек вызовов:")
            traceback.print_exc()
            
            return False
    
    except Exception as e:
        logger.error(f"Необработанная ошибка: {e}")
        import traceback
        logger.error("Полный стек вызовов:")
        traceback.print_exc()
        return False

# Получение тестового изображения
def get_test_image():
    # Пробуем несколько возможных мест
    candidates = [
        "data/sample/invoice1.jpg",
        "data/sample/sample.jpg",
        "tmp/test_image.jpg"
    ]
    
    for path in candidates:
        if os.path.exists(path):
            return path
    
    # Проверяем каталог tmp
    tmp_dir = Path("tmp")
    if tmp_dir.exists():
        # Ищем первое jpg/png изображение
        for file in tmp_dir.glob("*.jpg"):
            return str(file)
        for file in tmp_dir.glob("*.png"):
            return str(file)
    
    # Проверяем каталог data
    data_dir = Path("data")
    if data_dir.exists():
        # Ищем любое изображение рекурсивно
        for ext in ["jpg", "png", "jpeg"]:
            for file in data_dir.glob(f"**/*.{ext}"):
                return str(file)
    
    return None

async def main():
    logger.info("Запуск диагностики OCR...")
    
    # Получение тестового изображения
    test_image = get_test_image()
    if not test_image:
        logger.error("Тестовое изображение не найдено!")
        logger.info("Создаю простое тестовое изображение...")
        
        try:
            # Создаем простое тестовое изображение
            from PIL import Image, ImageDraw, ImageFont
            import numpy as np
            
            # Создаем изображение
            img = Image.new('RGB', (800, 600), color=(255, 255, 255))
            d = ImageDraw.Draw(img)
            
            # Добавляем текст
            d.text((50, 50), "TEST INVOICE", fill=(0, 0, 0))
            d.text((50, 100), "Date: 2023-01-01", fill=(0, 0, 0))
            d.text((50, 150), "Supplier: Test Company", fill=(0, 0, 0))
            d.text((50, 200), "Products:", fill=(0, 0, 0))
            d.text((70, 250), "1. Bread - 2 pcs - $5.00", fill=(0, 0, 0))
            d.text((70, 300), "2. Milk - 1 liter - $3.50", fill=(0, 0, 0))
            d.text((70, 350), "3. Eggs - 10 pcs - $4.00", fill=(0, 0, 0))
            d.text((50, 450), "Total: $12.50", fill=(0, 0, 0))
            
            # Сохраняем изображение
            os.makedirs("tmp", exist_ok=True)
            test_image = "tmp/test_invoice.jpg"
            img.save(test_image)
            logger.info(f"Тестовое изображение создано: {test_image}")
        except Exception as img_err:
            logger.error(f"Не удалось создать тестовое изображение: {img_err}")
            return
    
    # Запуск тестирования OCR
    logger.info(f"Использую тестовое изображение: {test_image}")
    success = await test_ocr(test_image)
    
    if success:
        logger.info("Тест OCR успешно завершен!")
    else:
        logger.error("Тест OCR завершился с ошибками!")

if __name__ == "__main__":
    asyncio.run(main()) 