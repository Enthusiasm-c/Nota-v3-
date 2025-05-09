#!/usr/bin/env python3
"""
Скрипт для тестирования детектора таблиц.
"""
import argparse
import logging
import sys
import os
from pathlib import Path
from PIL import Image, ImageDraw
import io

# Добавляем корневую директорию в путь, чтобы импорты работали как в prod
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.detectors.table.factory import get_detector

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def parse_args():
    parser = argparse.ArgumentParser(description='Тестирование детектора таблиц')
    parser.add_argument('--image', '-i', required=True, help='Путь к тестовому изображению')
    parser.add_argument('--output', '-o', help='Путь для сохранения визуализации')
    parser.add_argument('--cells-dir', '-c', help='Директория для сохранения ячеек')
    parser.add_argument('--method', '-m', default='paddle', choices=['paddle'], help='Метод детекции')
    return parser.parse_args()

def visualize_results(image_bytes, detect_result, output_path=None):
    """Визуализирует результаты детекции таблиц и ячеек."""
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    draw = ImageDraw.Draw(image)
    
    tables = detect_result.get('tables', [])
    for i, table in enumerate(tables):
        bbox = table.get('bbox')
        if bbox:
            # Рисуем рамку таблицы красным цветом
            draw.rectangle(bbox, outline='red', width=3)
            draw.text((bbox[0], bbox[1] - 20), f"Table {i+1}", fill='red')
        
        cells = table.get('cells', [])
        for j, cell in enumerate(cells):
            cell_bbox = cell.get('bbox')
            if cell_bbox:
                # Рисуем рамки ячеек синим цветом
                draw.rectangle(cell_bbox, outline='blue', width=2)
                # Добавляем номер ячейки
                center_x = (cell_bbox[0] + cell_bbox[2]) // 2
                center_y = (cell_bbox[1] + cell_bbox[3]) // 2
                draw.text((center_x, center_y), f"{j+1}", fill='blue')
    
    if output_path:
        logger.info(f"Сохраняем визуализацию в {output_path}")
        image.save(output_path)
    else:
        # Показываем изображение, если доступно
        try:
            image.show()
        except Exception as e:
            logger.error(f"Не удалось показать изображение: {e}")
    
    return image

def save_cells(cells, output_dir):
    """Сохраняет изображения ячеек в отдельные файлы."""
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    for i, cell in enumerate(cells):
        if 'image' in cell:
            # Сохраняем изображение ячейки
            cell_path = os.path.join(output_dir, f"cell_{i+1}.png")
            with open(cell_path, 'wb') as f:
                f.write(cell['image'])
            
            # Сохраняем текст ячейки, если есть
            if 'text' in cell and cell['text']:
                text_path = os.path.join(output_dir, f"cell_{i+1}.txt")
                with open(text_path, 'w', encoding='utf-8') as f:
                    f.write(cell['text'])
            
            logger.info(f"Ячейка {i+1} сохранена в {cell_path}")

def main():
    args = parse_args()
    
    # Проверяем наличие файла
    image_path = Path(args.image)
    if not image_path.exists():
        logger.error(f"Файл не найден: {image_path}")
        return 1
    
    # Загружаем изображение
    with open(image_path, 'rb') as f:
        image_bytes = f.read()
    
    logger.info(f"Загружено изображение размером {len(image_bytes)} байт")
    
    # Получаем детектор
    detector = get_detector(method=args.method)
    
    # Выполняем детекцию таблиц
    logger.info("Запуск детекции таблиц...")
    try:
        detect_result = detector.detect(image_bytes)
        
        # Выводим результаты
        tables = detect_result.get('tables', [])
        logger.info(f"Обнаружено таблиц: {len(tables)}")
        
        for i, table in enumerate(tables):
            cells = table.get('cells', [])
            logger.info(f"Таблица {i+1}: обнаружено ячеек: {len(cells)}")
        
        # Визуализируем результаты
        output_path = args.output if args.output else None
        visualize_results(image_bytes, detect_result, output_path)
        
        # Извлекаем отдельные ячейки
        logger.info("Извлечение ячеек...")
        cells = detector.extract_cells(image_bytes)
        logger.info(f"Извлечено ячеек: {len(cells)}")
        
        # Сохраняем ячейки, если указана директория
        if args.cells_dir:
            save_cells(cells, args.cells_dir)
        
        return 0
    except Exception as e:
        logger.error(f"Ошибка при детекции таблиц: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main()) 