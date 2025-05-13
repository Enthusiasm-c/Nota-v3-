#!/usr/bin/env python3
"""
Скрипт для smoke-тестирования ядра системы без Telegram-обвязки.
Выполняет полный цикл: OCR → парсинг → матчинг и выводит результат в формате JSON.
"""

import sys
import json
import logging
from pathlib import Path

# Настройка логгирования
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Импорты компонентов системы
from app.matcher import match_positions
from app.ocr import call_openai_ocr

def smoke_test(image_path):
    """
    Выполняет полный цикл обработки изображения инвойса.
    
    Args:
        image_path: Путь к изображению инвойса
    
    Returns:
        dict: Результат обработки
    """
    try:
        logger.info(f"Начинаю обработку изображения: {image_path}")
        
        # Читаем файл изображения
        with open(image_path, "rb") as f:
            image_bytes = f.read()
            
        # Шаг 1: OCR - прямой вызов OpenAI Vision API
        logger.info("Использую OpenAI Vision API для распознавания текста...")
        ocr_result = call_openai_ocr(image_bytes)
        logger.info(f"OCR завершен успешно. Найдено {len(ocr_result.positions)} позиций.")
        
        # Шаг 2: Матчинг позиций с каталогом
        positions = [pos.model_dump() for pos in ocr_result.positions]
        matched_positions = match_positions(positions, [])  # Пустой список продуктов для демонстрации
        logger.info(f"Выполнен матчинг {len(matched_positions)} позиций")
        
        # Формируем финальный результат
        result = {
            "date": ocr_result.date.isoformat() if ocr_result.date else None,
            "supplier": ocr_result.supplier,
            "total_price": ocr_result.total_price,
            "positions": matched_positions
        }
        
        return result
        
    except Exception as e:
        logger.exception(f"Ошибка при обработке изображения: {e}")
        return {"error": str(e)}

def main():
    """Основная функция скрипта."""
    if len(sys.argv) < 2:
        print("Использование: python -m app.scripts.smoke_invoice <путь_к_изображению>")
        sys.exit(1)
    
    image_path = sys.argv[1]
    
    if not Path(image_path).exists():
        print(f"Ошибка: Файл не найден: {image_path}")
        sys.exit(1)
    
    # Запускаем функцию
    result = smoke_test(image_path)
    
    # Выводим результат в формате JSON
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main() 