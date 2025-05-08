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
import argparse
from pathlib import Path
from datetime import date, datetime
import shutil

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

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

# Создаем парсер аргументов командной строки
def parse_args():
    parser = argparse.ArgumentParser(description="Диагностика OCR модуля")
    parser.add_argument("--image", "-i", type=str, help="Путь к тестовому изображению")
    parser.add_argument("--timeout", "-t", type=int, default=90, help="Таймаут OCR в секундах (по умолчанию 90)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Включить подробное логирование")
    parser.add_argument("--model", "-m", type=str, default="gpt-4o", help="Модель OpenAI (по умолчанию gpt-4o)")
    parser.add_argument("--save_intermediate", "-s", action="store_true", help="Сохранять промежуточные изображения")
    parser.add_argument("--no_preprocessing", "-n", action="store_true", help="Отключить предобработку изображения")
    return parser.parse_args()

# Функция для асинхронного запуска OCR
async def test_ocr(image_path, timeout=90, verbose=False, save_intermediate=False, no_preprocessing=False):
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
            from app import ocr
            logger.info("Модуль OCR успешно импортирован")
        except ImportError as import_err:
            logger.error(f"Ошибка импорта модуля OCR: {import_err}")
            logger.error(f"Детали ошибки: {import_err.__class__.__name__}")
            return False
        
        # Проверка конфигурации
        logger.info("Проверяю конфигурацию...")
        from app.config import settings
        
        # Если включен verbose режим, включаем отладочные логи API
        if verbose:
            import logging
            logging.getLogger("openai").setLevel(logging.DEBUG)
            logging.getLogger("httpx").setLevel(logging.DEBUG)
        
        missing_vars = []
        if not getattr(settings, "OPENAI_OCR_KEY", None):
            missing_vars.append("OPENAI_OCR_KEY")
        
        if missing_vars:
            logger.error(f"Отсутствуют обязательные переменные: {', '.join(missing_vars)}")
            return False
        
        logger.info("Запускаю OCR с использованием прямого вызова Vision API...")
        
        # Запускаем OCR
        start_time = time.time()
        
        # Предобработка изображения (если используется)
        if hasattr(ocr, 'prepare_for_ocr') and not no_preprocessing:
            tmp_path = f"/tmp/nota_ocr_debug_{int(time.time())}.jpg"
            shutil.copy(image_path, tmp_path)
            processed_bytes = ocr.prepare_for_ocr(tmp_path, use_preprocessing=True)
            if save_intermediate:
                with open(tmp_path + '.webp', 'wb') as f:
                    f.write(processed_bytes)
                logger.info(f"Промежуточное изображение после предобработки сохранено: {tmp_path + '.webp'}")
            image_bytes = processed_bytes
            logger.info("Изображение обработано с предобработкой")
        else:
            if no_preprocessing:
                logger.info("Предобработка изображения отключена")
        
        # Запуск с перехватом всех возможных исключений
        try:
            result = await asyncio.to_thread(ocr.call_openai_ocr, image_bytes)
            duration = time.time() - start_time
            logger.info(f"OCR успешно завершен за {duration:.2f} сек")
            logger.info(f"Результат: {len(result.positions)} позиций найдено")
            
            # Выводим производительность
            print(f"\n{'='*50}")
            print(f"СТАТИСТИКА ПРОИЗВОДИТЕЛЬНОСТИ OCR:")
            print(f"Время обработки: {duration:.2f} сек")
            print(f"Найдено позиций: {len(result.positions)}")
            print(f"Размер изображения: {len(image_bytes)/1024:.1f} KB")
            print(f"{'='*50}\n")
            
            # Выводим результат в JSON для проверки
            print("\nРезультат OCR (JSON):")
            print(json.dumps(result.model_dump(), indent=2, ensure_ascii=False, default=json_serialize))
            return True
            
        except Exception as ocr_err:
            elapsed = time.time() - start_time
            logger.error(f"Ошибка OCR после {elapsed:.2f} сек: {str(ocr_err)}")
            logger.error(f"Тип ошибки: {ocr_err.__class__.__name__}")
            
            # Попытка получить корень ошибки
            if hasattr(ocr_err, "__cause__") and ocr_err.__cause__ is not None:
                cause = ocr_err.__cause__
                logger.error(f"Причина ошибки: {cause.__class__.__name__}: {str(cause)}")
                
                # Проверка на наличие вложенной причины
                if hasattr(cause, "__cause__") and cause.__cause__ is not None:
                    root_cause = cause.__cause__
                    logger.error(f"Корневая причина: {root_cause.__class__.__name__}: {str(root_cause)}")
            
            return False
    
    except Exception as e:
        logger.error(f"Неожиданная ошибка: {str(e)}")
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
    args = parse_args()
    logger.info("Запуск диагностики OCR...")
    
    # Получение тестового изображения
    test_image = args.image or get_test_image()
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
    logger.info(f"Запуск тестирования OCR на {test_image}")
    logger.info(f"Таймаут: {args.timeout} сек")
    logger.info(f"Режим подробного логирования: {'Включен' if args.verbose else 'Выключен'}")
    logger.info(f"Используемая модель: {args.model}")
    
    success = await test_ocr(test_image, timeout=args.timeout, verbose=args.verbose, save_intermediate=args.save_intermediate, no_preprocessing=args.no_preprocessing)
    if success:
        logger.info("✅ Тест OCR успешно выполнен")
    else:
        logger.error("❌ Тест OCR завершился с ошибкой")

if __name__ == "__main__":
    asyncio.run(main()) 