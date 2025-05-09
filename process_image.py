#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Скрипт для предобработки изображения накладной
Использует модуль prepare_for_ocr из проекта Nota
"""

import os
import sys
import time
import shutil
from PIL import Image
import argparse
import traceback

# Добавляем текущий каталог в путь поиска модулей
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

# Парсер аргументов командной строки
def parse_args():
    parser = argparse.ArgumentParser(description="Предобработка изображения накладной")
    parser.add_argument("input", type=str, help="Путь к исходному изображению")
    parser.add_argument("--output", "-o", type=str, help="Путь для сохранения обработанного изображения")
    parser.add_argument("--save-steps", "-s", action="store_true", help="Сохранять промежуточные шаги обработки")
    return parser.parse_args()

def main():
    args = parse_args()
    
    # Проверка существования входного файла
    if not os.path.exists(args.input):
        print(f"Ошибка: файл {args.input} не найден")
        return 1
    
    # Определение выходного пути
    output_path = args.output or args.input + ".processed.webp"
    
    # Создаем временную директорию для хранения промежуточных изображений
    tmp_dir = None
    if args.save_steps:
        tmp_dir = os.path.join(os.path.dirname(output_path), "process_steps")
        os.makedirs(tmp_dir, exist_ok=True)
        print(f"Промежуточные шаги будут сохранены в: {tmp_dir}")
    
    print(f"Исходное изображение: {args.input}")
    print(f"Обработанное изображение будет сохранено: {output_path}")
    
    try:
        # Импортируем модуль предобработки из проекта
        print("Импорт модуля предобработки...")
        
        try:
            from app.imgprep.prepare import prepare_for_ocr
            print("Модуль предобработки успешно импортирован")
        except ImportError as e:
            print(f"Ошибка импорта модуля предобработки: {e}")
            print("Убедитесь, что вы находитесь в корневой директории проекта и виртуальное окружение активировано")
            return 1
        
        # Если нужно сохранить оригинальное изображение
        if args.save_steps:
            orig_copy = os.path.join(tmp_dir, "0_original.jpg")
            shutil.copy(args.input, orig_copy)
            print(f"Копия оригинала сохранена: {orig_copy}")
        
        # Применяем предобработку
        print("Применяем предобработку...")
        start_time = time.time()
        processed_bytes = prepare_for_ocr(args.input, use_preprocessing=True)
        elapsed = time.time() - start_time
        print(f"Предобработка завершена за {elapsed:.2f} сек")
        
        # Сохраняем результат
        with open(output_path, 'wb') as f:
            f.write(processed_bytes)
        print(f"Обработанное изображение сохранено: {output_path}")
        
        # Открываем для проверки
        try:
            processed_img = Image.open(output_path)
            print(f"Размер обработанного изображения: {processed_img.width}x{processed_img.height}, режим: {processed_img.mode}")
        except Exception as img_err:
            print(f"Предупреждение: не удалось проверить обработанное изображение: {str(img_err)}")
        
        return 0
    
    except Exception as e:
        print(f"Ошибка при предобработке: {str(e)}")
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main()) 