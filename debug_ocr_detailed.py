#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Подробный диагностический скрипт для анализа процесса OCR по шагам
Сохраняет промежуточные результаты на каждом этапе обработки
"""

import os
import sys
import time
import json
import base64
import argparse
import asyncio
import logging
import traceback
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime, date
import shutil

# Настройка логирования
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Включаем полное логирование HTTP и API
logging.getLogger("openai").setLevel(logging.DEBUG)
logging.getLogger("httpx").setLevel(logging.DEBUG)
logging.getLogger("app.ocr").setLevel(logging.DEBUG)

# Функция сериализации для JSON
def json_serialize(obj):
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")

def create_debug_dir():
    """Создает директорию для отладочных файлов с временной меткой"""
    timestamp = int(time.time())
    debug_dir = f"debug_ocr_{timestamp}"
    os.makedirs(debug_dir, exist_ok=True)
    logger.info(f"Создана директория для отладки: {debug_dir}")
    return debug_dir

def parse_args():
    parser = argparse.ArgumentParser(description="Подробная диагностика OCR процесса")
    parser.add_argument("--image", "-i", type=str, required=True, help="Путь к изображению накладной")
    parser.add_argument("--timeout", "-t", type=int, default=120, help="Таймаут в секундах")
    parser.add_argument("--debug-dir", "-d", type=str, help="Директория для отладочных файлов")
    return parser.parse_args()

async def run_step_by_step_debug(image_path, debug_dir, timeout=120):
    """Пошаговая отладка процесса OCR с сохранением результатов"""
    try:
        logger.info("ЭТАП 1: Проверка входного изображения")
        if not os.path.exists(image_path):
            logger.error(f"❌ ОШИБКА: Файл {image_path} не существует")
            return False
        orig_image_path = os.path.join(debug_dir, "1_original_image.jpg")
        shutil.copy(image_path, orig_image_path)
        logger.info(f"✅ Исходное изображение сохранено: {orig_image_path}")
        try:
            with Image.open(image_path) as img:
                width, height = img.size
                format = img.format
                mode = img.mode
                logger.info(f"✅ Информация об изображении: {width}x{height}, формат: {format}, режим: {mode}")
        except Exception as img_err:
            logger.error(f"❌ ОШИБКА при анализе изображения: {str(img_err)}")
        with open(image_path, 'rb') as f:
            image_bytes = f.read()
        
        logger.info("ЭТАП 4: Подготовка запроса к Vision API")
        # Кодируем изображение в base64
        try:
            b64_image = base64.b64encode(image_bytes).decode('utf-8')
            logger.info(f"✅ Изображение закодировано в base64, размер: {len(b64_image)} символов")
            
            # Сохраняем base64 для анализа (первые 100 символов)
            b64_sample_path = os.path.join(debug_dir, "4_base64_sample.txt")
            with open(b64_sample_path, 'w') as f:
                f.write(f"Полная длина: {len(b64_image)} символов\n")
                f.write(f"Начало строки base64: {b64_image[:100]}...\n")
            logger.info(f"✅ Образец base64 сохранен: {b64_sample_path}")
        except Exception as b64_err:
            logger.error(f"❌ ОШИБКА кодирования base64: {str(b64_err)}")
            return False
        
        # Формируем запрос
        prompt = """Вы - система для оптического распознавания текста (OCR). 
Распознайте весь текст с изображения накладной, сохраняя числа, даты, названия товаров и структуру документа.
Старайтесь точно передать то, что видите, не интерпретируя и не добавляя информацию."""
        
        messages = [
            {
                "role": "system",
                "content": prompt
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Распознайте все тексты, числа и таблицы с изображения накладной."},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_image}", "detail": "high"}}
                ]
            }
        ]
        
        # Сохраняем промпт
        prompt_path = os.path.join(debug_dir, "4_api_prompt.json")
        with open(prompt_path, 'w', encoding='utf-8') as f:
            # Сохраняем редактированную копию без base64 данных для читаемости
            messages_copy = json.loads(json.dumps(messages))
            if len(messages_copy) > 1 and "content" in messages_copy[1]:
                for item in messages_copy[1]["content"]:
                    if item.get("type") == "image_url":
                        item["image_url"]["url"] = "[BASE64 DATA]"
            json.dump(messages_copy, f, indent=2, ensure_ascii=False)
        logger.info(f"✅ Промпт API сохранен: {prompt_path}")
        
        logger.info("ЭТАП 5: Отправка запроса в Vision API")
        # Отправляем запрос
        try:
            start_time = time.time()
            logger.info("Отправка запроса в API...")
            
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                max_tokens=4096,
                temperature=0.0,
                timeout=timeout
            )
            
            api_time = time.time() - start_time
            logger.info(f"✅ Получен ответ от API за {api_time:.2f} сек")
            logger.info(f"✅ Модель: {response.model}, Токенов: {response.usage.total_tokens}")
            
            # Сохраняем полный ответ API
            response_path = os.path.join(debug_dir, "5_api_full_response.json")
            if hasattr(response, "model_dump"):
                with open(response_path, 'w', encoding='utf-8') as f:
                    json.dump(response.model_dump(), f, indent=2, ensure_ascii=False, default=json_serialize)
                logger.info(f"✅ Полный ответ API сохранен: {response_path}")
            
            # Извлекаем и сохраняем текстовый ответ
            text_response = response.choices[0].message.content
            text_path = os.path.join(debug_dir, "5_api_text_response.txt")
            with open(text_path, 'w', encoding='utf-8') as f:
                f.write(text_response)
            logger.info(f"✅ Текстовый ответ API сохранен: {text_path}")
            
            # Выводим начало текстового ответа
            print("\n" + "=" * 40)
            print("ТЕКСТОВЫЙ ОТВЕТ VISION API (начало):")
            print("-" * 40)
            print(text_response[:500] + "..." if len(text_response) > 500 else text_response)
            print("=" * 40 + "\n")
            
        except Exception as api_err:
            logger.error(f"❌ ОШИБКА вызова API: {str(api_err)}")
            
            # Сохраняем информацию об ошибке
            error_path = os.path.join(debug_dir, "5_api_error.txt")
            with open(error_path, 'w', encoding='utf-8') as f:
                f.write(f"Ошибка API: {str(api_err)}\n\n")
                f.write(f"Трассировка:\n{traceback.format_exc()}")
                
                # Пытаемся извлечь больше информации
                if hasattr(api_err, "response"):
                    try:
                        f.write("\n\nОтвет сервера:\n")
                        f.write(f"Статус: {api_err.response.status_code}\n")
                        f.write(f"Заголовки: {dict(api_err.response.headers)}\n")
                        f.write(f"Текст: {api_err.response.text}\n")
                    except:
                        f.write("\nНе удалось извлечь информацию об ответе")
            
            logger.error(f"❌ Информация об ошибке сохранена: {error_path}")
            return False
        
        logger.info("ЭТАП 6: Анализ результатов")
        # Предварительный анализ текстового результата
        try:
            text_lines = text_response.strip().split('\n')
            significant_lines = [line for line in text_lines if line.strip()]
            
            analysis_path = os.path.join(debug_dir, "6_result_analysis.txt")
            with open(analysis_path, 'w', encoding='utf-8') as f:
                f.write(f"Общая длина текста: {len(text_response)} символов\n")
                f.write(f"Количество строк: {len(text_lines)}\n")
                f.write(f"Количество непустых строк: {len(significant_lines)}\n\n")
                
                # Анализ структуры
                f.write("АНАЛИЗ СТРУКТУРЫ:\n")
                f.write(f"Первые 5 строк:\n")
                for i, line in enumerate(text_lines[:5]):
                    f.write(f"{i+1}. {line[:100]}\n")
                
                # Поиск таблицы или списка позиций
                f.write("\nПОИСК ПОЗИЦИЙ:\n")
                position_candidates = []
                for i, line in enumerate(text_lines):
                    if any(keyword in line.lower() for keyword in ["qty", "quantity", "pcs", "шт", "кг", "kg", "pc"]):
                        position_candidates.append((i, line))
                
                f.write(f"Найдено {len(position_candidates)} потенциальных позиций\n")
                for i, (line_num, line) in enumerate(position_candidates[:10]):
                    f.write(f"{i+1}. Строка {line_num+1}: {line[:100]}\n")
            
            logger.info(f"✅ Анализ результатов сохранен: {analysis_path}")
        except Exception as analysis_err:
            logger.error(f"❌ ОШИБКА анализа: {str(analysis_err)}")
        
        logger.info("ЗАВЕРШЕНИЕ ОТЛАДКИ")
        logger.info(f"✅ Все результаты сохранены в директории: {debug_dir}")
        
        return True
    
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка в процессе отладки: {str(e)}")
        traceback.print_exc()
        return False

async def main():
    args = parse_args()
    
    # Создаем директорию для отладки
    debug_dir = args.debug_dir or create_debug_dir()
    
    logger.info(f"Запуск подробной диагностики OCR...")
    logger.info(f"Тестовое изображение: {args.image}")
    logger.info(f"Директория для отладки: {debug_dir}")
    
    # Запускаем пошаговую отладку
    success = await run_step_by_step_debug(
        args.image, 
        debug_dir, 
        timeout=args.timeout
    )
    
    if success:
        logger.info(f"✅ Диагностика завершена успешно. Результаты в: {debug_dir}")
    else:
        logger.error(f"❌ Диагностика завершилась с ошибками. Частичные результаты в: {debug_dir}")
    
    logger.info("-" * 70)
    logger.info(f"ПУТЬ К РЕЗУЛЬТАТАМ: {os.path.abspath(debug_dir)}")
    logger.info("-" * 70)

if __name__ == "__main__":
    asyncio.run(main()) 