#!/usr/bin/env python3
"""
Скрипт для демонстрации работы полного OCR-пайплайна.
"""
import json
import argparse
import logging
import sys
import os
import asyncio
from decimal import Decimal
from pathlib import Path

# Добавляем корневую директорию в путь, чтобы импорты работали как в prod
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.ocr_pipeline import OCRPipeline

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Класс для сериализации Decimal
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

def parse_args():
    parser = argparse.ArgumentParser(description='Тестирование полного OCR-пайплайна')
    parser.add_argument('--image', '-i', required=True, help='Путь к изображению накладной')
    parser.add_argument('--output', '-o', help='Путь для сохранения результатов')
    parser.add_argument('--lang', '-l', default='id,en', help='Языки для OCR (через запятую)')
    parser.add_argument('--strict', '-s', action='store_true', help='Строгий режим валидации')
    parser.add_argument('--error-percent', '-e', type=float, default=1.0, 
                      help='Максимальный процент погрешности (по умолчанию 1.0)')
    parser.add_argument('--detector', '-d', choices=['paddle'], default='paddle',
                      help='Метод детекции таблиц (по умолчанию paddle)')
    parser.add_argument('--cells-dir', '-c', help='Директория для сохранения изображений ячеек')
    return parser.parse_args()

def print_summary(result):
    """Выводит красивое резюме результатов OCR."""
    print("\n" + "=" * 50)
    print("РЕЗУЛЬТАТЫ РАСПОЗНАВАНИЯ НАКЛАДНОЙ")
    print("=" * 50)
    
    status = result.get('status', 'unknown')
    accuracy = result.get('accuracy', 0)
    lines = result.get('lines', [])
    issues = result.get('issues', [])
    
    print(f"Статус: {status}")
    print(f"Точность: {accuracy:.2%}")
    print(f"Распознано строк: {len(lines)}")
    print(f"Обнаружено проблем: {len(issues)}")
    print("-" * 50)
    
    # Выводим распознанные строки
    print("\nРАСПОЗНАННЫЕ ТОВАРЫ:")
    for i, line in enumerate(lines):
        name = line.get('name', 'Unknown')
        qty = line.get('qty', 0)
        unit = line.get('unit', '')
        price = line.get('price', 0)
        amount = line.get('amount', 0)
        auto_fixed = '[ИСПРАВЛЕНО]' if line.get('auto_fixed') else ''
        
        print(f"{i+1}. {name}: {qty} {unit} × {price} = {amount} {auto_fixed}")
    
    # Выводим проблемы
    if issues:
        print("\nПРОБЛЕМЫ:")
        for issue in issues:
            line_num = issue.get('line', '?')
            issue_type = issue.get('type', 'UNKNOWN')
            old = issue.get('old', '')
            fix = issue.get('fix', '')
            message = issue.get('message', '')
            
            if fix:
                print(f"Строка {line_num}: {issue_type} - исправлено с {old} на {fix}")
            else:
                print(f"Строка {line_num}: {issue_type} - {message}")
    
    print("=" * 50)

async def main():
    args = parse_args()
    
    # Проверяем наличие файла
    image_path = Path(args.image)
    if not image_path.exists():
        logger.error(f"Файл не найден: {image_path}")
        return 1
    
    try:
        # Загружаем изображение
        with open(image_path, 'rb') as f:
            image_bytes = f.read()
        
        logger.info(f"Загружено изображение размером {len(image_bytes)} байт")
        
        # Определяем языки
        languages = args.lang.split(',')
        
        # Создаем OCR-пайплайн
        pipeline = OCRPipeline(
            table_detector_method=args.detector,
            arithmetic_max_error=args.error_percent,
            strict_validation=args.strict
        )
        
        # Выполняем OCR
        logger.info(f"Запуск OCR-пайплайна с языками: {languages}...")
        result = await pipeline.process_image(image_bytes, lang=languages)
        
        # Выводим результаты
        print_summary(result)
        
        # Сохраняем результаты, если указан путь
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, cls=DecimalEncoder)
            logger.info(f"Результаты сохранены в {args.output}")
        
        # Сохраняем изображения ячеек, если указана директория
        if args.cells_dir:
            cells_dir = Path(args.cells_dir)
            cells_dir.mkdir(exist_ok=True, parents=True)
            
            # Здесь можно реализовать сохранение изображений ячеек
            # Но это потребует добавления соответствующего функционала в OCRPipeline
            
        return 0
    
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main())) 