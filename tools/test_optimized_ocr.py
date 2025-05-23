#!/usr/bin/env python
"""
Скрипт для тестирования оптимизированного OCR с предобработкой изображений.
Позволяет оценить эффективность предобработки и кеширования.

Использование:
  python test_optimized_ocr.py --image путь/к/изображению.jpg [--no-cache] [--no-preprocess]
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

from app.imgprep import prepare_for_ocr
from app.ocr import call_openai_ocr

# Add project root to Python path
project_root = str(Path(__file__).parent.parent)
sys.path.append(project_root)


def main():
    parser = argparse.ArgumentParser(description="Тестирование оптимизированного OCR")
    parser.add_argument("--image", "-i", required=True, help="Путь к файлу изображения")
    parser.add_argument("--no-cache", action="store_true", help="Отключить кеширование")
    parser.add_argument("--no-preprocess", action="store_true", help="Отключить предобработку")
    parser.add_argument(
        "--repeat", "-r", type=int, default=1, help="Количество повторов для тестирования кеша"
    )
    parser.add_argument("--output", "-o", help="Путь для сохранения результата в JSON")
    args = parser.parse_args()

    # Проверяем наличие файла
    image_path = Path(args.image)
    if not image_path.exists():
        print(f"Ошибка: файл {image_path} не существует")
        return 1

    # Читаем изображение
    with open(image_path, "rb") as f:
        original_image = f.read()
        print(f"Размер исходного изображения: {len(original_image) / 1024:.1f} KB")

    # Применяем предобработку, если включена
    if not args.no_preprocess:
        t0 = time.time()
        processed_image = prepare_for_ocr(original_image)
        preprocess_time = time.time() - t0
        print(f"Размер после предобработки: {len(processed_image) / 1024:.1f} KB")
        print(f"Время предобработки: {preprocess_time:.2f} сек")
        print(f"Степень сжатия: {len(original_image) / len(processed_image):.2f}x")
    else:
        processed_image = original_image
        print("Предобработка отключена, используем исходное изображение")

    # Создаем директорию для результатов, если нужно
    results_dir = os.path.join(project_root, "tmp", "ocr_results")
    os.makedirs(results_dir, exist_ok=True)

    # Выполняем OCR нужное количество раз
    for i in range(args.repeat):
        print(f"\nЗапуск OCR #{i+1}:")
        t0 = time.time()
        try:
            result = call_openai_ocr(processed_image, use_cache=not args.no_cache)
            ocr_time = time.time() - t0

            # Выводим результаты
            print(f"Время OCR: {ocr_time:.2f} сек")
            print(f"Поставщик: {result.supplier}")
            print(f"Дата: {result.date}")
            print(f"Количество позиций: {len(result.positions)}")
            print(f"Итоговая сумма: {result.total_price}")

            # Сохраняем результат, если указан путь
            if args.output or i == 0:
                output_path = args.output or os.path.join(
                    results_dir, f"ocr_result_{int(time.time())}.json"
                )
                with open(output_path, "w", encoding="utf-8") as f:
                    # Используем .dict() для сериализации Pydantic модели
                    result_dict = result.dict()
                    # Конвертируем date в строку, если это объект datetime
                    if result.date and not isinstance(result.date, str):
                        result_dict["date"] = result.date.isoformat()
                    json.dump(result_dict, f, ensure_ascii=False, indent=2)
                print(f"Результат сохранен в {output_path}")

        except Exception as e:
            print(f"Ошибка при выполнении OCR: {e}")
            return 1

    return 0


if __name__ == "__main__":