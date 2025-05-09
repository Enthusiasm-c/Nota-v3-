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
import base64
import traceback
import httpx

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

# Настраиваем подробное логирование HTTP-запросов (добавляем httpx логгер)
httpx_logger = logging.getLogger("httpx")
httpx_logger.setLevel(logging.DEBUG)
httpx_logger.propagate = True

# Настраиваем подробное логирование HTTP
def configure_http_debug_logging():
    try:
        import http.client as http_client
        http_client.HTTPConnection.debuglevel = 1
        
        requests_log = logging.getLogger("requests.packages.urllib3")
        requests_log.setLevel(logging.DEBUG)
        requests_log.propagate = True
        
        logger.info("Включено подробное логирование HTTP-трафика")
    except ImportError:
        logger.warning("Не удалось настроить подробное логирование HTTP")

configure_http_debug_logging()

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
    parser.add_argument("--raw_vision", "-r", action="store_true", help="Запустить распознавание сырого текста без структурирования")
    return parser.parse_args()

# Функция для асинхронного запуска OCR
async def test_ocr(image_path, timeout=90, verbose=False, save_intermediate=False):
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

async def test_raw_vision(image_path, timeout=90):
    """
    Отправляет изображение в Vision API для распознавания сырого текста без структурирования.
    Позволяет сравнить, что именно видит модель на изображении до интерпретации.
    
    Args:
        image_path: Путь к файлу изображения
        timeout: Таймаут в секундах
        
    Returns:
        True если успешно, False если ошибка
    """
    try:
        logger.info(f"Загружаю тестовое изображение: {image_path}")
        
        # Проверка существования файла
        if not os.path.exists(image_path):
            logger.error(f"Файл {image_path} не найден")
            return False
        
        # Получаем клиент OpenAI
        try:
            from app.config import get_ocr_client
            client = get_ocr_client()
            if not client:
                logger.error("Не удалось получить OpenAI клиент")
                return False
        except Exception as e:
            logger.error(f"Ошибка импорта OpenAI: {str(e)}")
            return False
            
        # Загружаем и при необходимости обрабатываем изображение
        with open(image_path, 'rb') as f:
            image_bytes = f.read()
            logger.info(f"Изображение загружено, размер: {len(image_bytes)} байт")
        
        # Кодируем изображение в base64
        b64_image = base64.b64encode(image_bytes).decode('utf-8')
        
        # Создаем простой запрос без функциональной схемы, только для получения текста
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Пожалуйста, опиши подробно всё, что ты видишь на этом изображении накладной. Прочитай все тексты, числа, таблицы. Не пропускай никакие детали."},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_image}", "detail": "high"}}
                ]
            }
        ]
        
        # Отправляем запрос
        logger.info("Отправляю запрос в OpenAI Vision API...")
        
        # Логируем запрос в более читаемом виде
        logger.info("Запрос к API:")
        for msg in messages:
            if msg["role"] == "user":
                content = msg["content"]
                for item in content:
                    if item["type"] == "text":
                        logger.info(f"Текст запроса: {item['text']}")
                    elif item["type"] == "image_url":
                        logger.info("Изображение: [данные изображения опущены]")
        
        try:
            # Устанавливаем таймаут и логируем HTTP-заголовки
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                max_tokens=4096,
                temperature=0.0,
                timeout=timeout
            )
            
            # Логируем успешный ответ
            logger.info(f"Получен ответ от API: {response.model}")
            logger.info(f"ID запроса: {response.id}")
            logger.info(f"Использовано токенов: {response.usage.total_tokens}")
            
            # Выводим сырой текстовый ответ
            raw_text = response.choices[0].message.content
            logger.info("Получен ответ от Vision API:")
            logger.info("-" * 80)
            print(raw_text)
            logger.info("-" * 80)
            
            # Сохраняем результат в файл для дальнейшего анализа
            output_file = f"raw_vision_result_{int(time.time())}.txt"
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(raw_text)
            logger.info(f"Результат сохранен в файл: {output_file}")
            
            # Сохраняем полный ответ API в JSON для диагностики
            if hasattr(response, "model_dump"):
                full_response_file = f"raw_vision_full_response_{int(time.time())}.json"
                with open(full_response_file, "w", encoding="utf-8") as f:
                    json.dump(response.model_dump(), f, indent=2, ensure_ascii=False, default=json_serialize)
                logger.info(f"Полный ответ API сохранен в: {full_response_file}")
            
            return True
        except Exception as api_error:
            logger.error(f"Ошибка при вызове API: {str(api_error)}")
            logger.error(f"Тип ошибки: {type(api_error).__name__}")
            
            # Пытаемся извлечь больше информации об ошибке
            error_details = {}
            if hasattr(api_error, "response"):
                try:
                    error_details["status_code"] = api_error.response.status_code
                    error_details["headers"] = dict(api_error.response.headers)
                    error_details["text"] = api_error.response.text
                except:
                    pass
            
            if error_details:
                logger.error(f"Детали ошибки API: {json.dumps(error_details, indent=2)}")
            
            raise
    except Exception as e:
        logger.error(f"❌ Распознавание сырого текста завершилось с ошибкой: {str(e)}")
        traceback.print_exc()
        return False

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
    
    # Запуск тестирования
    logger.info(f"Запуск тестирования на {test_image}")
    logger.info(f"Таймаут: {args.timeout} сек")
    logger.info(f"Режим подробного логирования: {'Включен' if args.verbose else 'Выключен'}")
    
    # Если выбран режим сырого распознавания
    if args.raw_vision:
        logger.info("Запуск распознавания сырого текста...")
        success = await test_raw_vision(test_image, timeout=args.timeout)
        if success:
            logger.info("✅ Распознавание сырого текста успешно выполнено")
        else:
            logger.error("❌ Распознавание сырого текста завершилось с ошибкой")
        return
    
    # Обычное тестирование OCR
    logger.info(f"Используемая модель: {args.model}")
    
    success = await test_ocr(test_image, timeout=args.timeout, verbose=args.verbose, save_intermediate=args.save_intermediate)
    if success:
        logger.info("✅ Тест OCR успешно выполнен")
    else:
        logger.error("❌ Тест OCR завершился с ошибкой")

if __name__ == "__main__":
    asyncio.run(main()) 