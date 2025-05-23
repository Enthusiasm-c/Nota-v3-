#!/usr/bin/env python3
"""
Скрипт для тестирования каскадного OCR-пайплайна.
Выводит детальную статистику по использованию PaddleOCR и GPT-4o.
"""
import argparse
import asyncio
import json
import logging
import os
import sys
import time
from decimal import Decimal
from pathlib import Path

# Добавляем корневую директорию в путь, чтобы импорты работали как в prod
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.ocr_pipeline import OCRPipeline

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


# Класс для сериализации Decimal
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)


def parse_args():
    parser = argparse.ArgumentParser(description="Тестирование каскадного OCR-пайплайна")
    parser.add_argument("--image", "-i", required=True, help="Путь к изображению накладной")
    parser.add_argument("--output", "-o", help="Путь для сохранения результатов")
    parser.add_argument("--stats", "-s", help="Путь для сохранения статистики")
    parser.add_argument(
        "--threshold",
        "-t",
        type=float,
        default=0.7,
        help="Порог уверенности для GPT-4o (по умолчанию 0.7)",
    )
    parser.add_argument("--lang", "-l", default="id,en", help="Языки для OCR (через запятую)")
    parser.add_argument("--cells-dir", "-c", help="Директория для сохранения изображений ячеек")
    return parser.parse_args()


def print_summary(result):
    """Выводит красивое резюме результатов OCR."""
    print("\n" + "=" * 50)
    print("РЕЗУЛЬТАТЫ РАСПОЗНАВАНИЯ НАКЛАДНОЙ")
    print("=" * 50)

    status = result.get("status", "unknown")
    accuracy = result.get("accuracy", 0)
    lines = result.get("lines", [])
    issues = result.get("issues", [])
    gpt4o_percent = result.get("gpt4o_percent", 0)
    gpt4o_count = result.get("gpt4o_count", 0)
    total_cells = result.get("total_cells", 0)

    print(f"Статус: {status}")
    print(f"Точность: {accuracy:.2%}")
    print(f"Распознано строк: {len(lines)}")
    print(f"Обнаружено проблем: {len(issues)}")
    print(f"Использование GPT-4o: {gpt4o_percent:.1f}% ({gpt4o_count}/{total_cells} ячеек)")
    print("-" * 50)

    # Выводим распознанные строки
    print("\nРАСПОЗНАННЫЕ ТОВАРЫ:")
    for i, line in enumerate(lines):
        name = line.get("name", "Unknown")
        qty = line.get("qty", 0)
        unit = line.get("unit", "")
        price = line.get("price", 0)
        amount = line.get("amount", 0)
        auto_fixed = "[ИСПРАВЛЕНО]" if line.get("auto_fixed") else ""

        print(f"{i+1}. {name}: {qty} {unit} × {price} = {amount} {auto_fixed}")

        # Выводим информацию по ячейкам
        cells = line.get("cells", [])
        for j, cell in enumerate(cells):
            text = cell.get("text", "")
            conf = cell.get("confidence", 0)
            used_gpt = "(GPT-4o)" if cell.get("used_gpt4o") else "(PaddleOCR)"
            print(f"   Ячейка {j+1}: '{text}' [уверенность: {conf:.2f}] {used_gpt}")

    # Выводим проблемы
    if issues:
        print("\nПРОБЛЕМЫ:")
        for issue in issues:
            line_num = issue.get("line", "?")
            issue_type = issue.get("type", "UNKNOWN")
            old = issue.get("old", "")
            fix = issue.get("fix", "")
            message = issue.get("message", "")

            if fix:
                print(f"Строка {line_num}: {issue_type} - исправлено с {old} на {fix}")
            else:
                print(f"Строка {line_num}: {issue_type} - {message}")

    print("=" * 50)


def generate_stats(result):
    """Генерирует детальную статистику по результатам OCR."""
    lines = result.get("lines", [])
    total_cells = 0
    cells_with_gpt = 0
    confidence_stats = {
        "very_low": 0,  # <0.3
        "low": 0,  # 0.3-0.7
        "high": 0,  # 0.7-0.9
        "very_high": 0,  # >0.9
    }

    # Собираем статистику по ячейкам
    for line in lines:
        cells = line.get("cells", [])
        for cell in cells:
            total_cells += 1
            conf = cell.get("confidence", 0)

            if cell.get("used_gpt4o"):
                cells_with_gpt += 1

            if conf < 0.3:
                confidence_stats["very_low"] += 1
            elif conf < 0.7:
                confidence_stats["low"] += 1
            elif conf < 0.9:
                confidence_stats["high"] += 1
            else:
                confidence_stats["very_high"] += 1

    # Формируем итоговую статистику
    stats = {
        "timestamp": time.time(),
        "total_cells": total_cells,
        "cells_with_gpt": cells_with_gpt,
        "gpt_percent": (cells_with_gpt / total_cells * 100) if total_cells else 0,
        "paddle_percent": 100 - ((cells_with_gpt / total_cells * 100) if total_cells else 0),
        "confidence_stats": confidence_stats,
        "confidence_distribution": {
            "very_low_percent": (
                (confidence_stats["very_low"] / total_cells * 100) if total_cells else 0
            ),
            "low_percent": (confidence_stats["low"] / total_cells * 100) if total_cells else 0,
            "high_percent": (confidence_stats["high"] / total_cells * 100) if total_cells else 0,
            "very_high_percent": (
                (confidence_stats["very_high"] / total_cells * 100) if total_cells else 0
            ),
        },
        "accuracy": result.get("accuracy", 0),
        "issues_count": len(result.get("issues", [])),
        "lines_count": len(lines),
    }

    return stats


async def main():
    args = parse_args()

    # Проверяем наличие файла
    image_path = Path(args.image)
    if not image_path.exists():
        logger.error(f"Файл не найден: {image_path}")
        return 1

    try:
        # Загружаем изображение
        with open(image_path, "rb") as f:
            image_bytes = f.read()

        logger.info(f"Загружено изображение размером {len(image_bytes)} байт")

        # Определяем языки
        languages = args.lang.split(",")

        # Создаем OCR-пайплайн
        pipeline = OCRPipeline(
            table_detector_method="paddle", arithmetic_max_error=1.0, strict_validation=False
        )

        # Устанавливаем порог уверенности
        pipeline.low_conf_threshold = args.threshold
        logger.info(f"Установлен порог уверенности: {args.threshold}")

        # Выполняем OCR
        logger.info(f"Запуск OCR-пайплайна с языками: {languages}...")
        t_start = time.time()
        result = await pipeline.process_image(image_bytes, lang=languages)
        t_end = time.time()

        logger.info(f"OCR-пайплайн завершен за {t_end - t_start:.2f} сек")

        # Выводим результаты
        print_summary(result)

        # Генерируем статистику
        stats = generate_stats(result)
        stats["processing_time"] = t_end - t_start

        # Сохраняем результаты и статистику, если указаны пути
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, cls=DecimalEncoder)
            logger.info(f"Результаты сохранены в {args.output}")

        if args.stats:
            with open(args.stats, "w", encoding="utf-8") as f:
                json.dump(stats, f, indent=2, cls=DecimalEncoder)
            logger.info(f"Статистика сохранена в {args.stats}")

        # Сохраняем изображения ячеек, если указана директория
        if args.cells_dir:
            cells_dir = Path(args.cells_dir)
            cells_dir.mkdir(exist_ok=True, parents=True)

            logger.info(f"Сохранение изображений ячеек в {cells_dir}...")

            import io

            from PIL import Image

            cells_count = 0
            for i, line in enumerate(result.get("lines", [])):
                cells = line.get("cells", [])
                for j, cell in enumerate(cells):
                    if "image" in cell:
                        try:
                            img = Image.open(io.BytesIO(cell["image"]))
                            img_path = cells_dir / f"line_{i+1}_cell_{j+1}.png"
                            img.save(img_path)
                            cells_count += 1
                        except Exception as e:
                            logger.error(f"Ошибка при сохранении изображения ячейки: {e}")

            logger.info(f"Сохранено {cells_count} изображений ячеек")

        return 0

    except Exception as e:
        logger.error(f"Ошибка: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
