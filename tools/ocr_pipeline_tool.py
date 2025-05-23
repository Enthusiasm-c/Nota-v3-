#!/usr/bin/env python3
"""
Скрипт для демонстрации работы оптимизированного OCR-пайплайна.
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

# Импортируем оптимизированный пайплайн
from app.ocr_pipeline_optimized import OCRPipelineOptimized

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
    parser = argparse.ArgumentParser(description="Тестирование оптимизированного OCR-пайплайна")
    parser.add_argument("--image", "-i", required=True, help="Путь к изображению накладной")
    parser.add_argument("--output", "-o", help="Путь для сохранения результатов")
    parser.add_argument("--lang", "-l", default="ru,en", help="Языки для OCR (через запятую)")
    parser.add_argument(
        "--detector",
        "-d",
        choices=["paddle"],
        default="paddle",
        help="Метод детекции таблиц (по умолчанию paddle)",
    )
    parser.add_argument(
        "--no-cache", "-nc", action="store_true", help="Отключить использование кэша"
    )
    parser.add_argument(
        "--no-fallback",
        "-nf",
        action="store_true",
        help="Отключить использование OpenAI Vision как запасного варианта",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Подробный вывод")
    parser.add_argument(
        "--compare", "-c", help="Путь к исходному OCR-пайплайну для сравнения производительности"
    )
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
    timing = result.get("timing", {})
    metrics = result.get("metrics", {})

    print(f"Статус: {status}")
    if status == "error":
        print(f"Ошибка: {result.get('message', 'Неизвестная ошибка')}")

    print(f"Точность: {accuracy:.2%}")
    print(f"Распознано строк: {len(lines)}")
    print(f"Обнаружено проблем: {len(issues)}")

    # Выводим информацию о времени выполнения
    if timing:
        print("\nЗАМЕРЫ ВРЕМЕНИ:")
        for key, value in timing.items():
            if isinstance(value, (int, float)):
                print(f"  {key}: {value} мс")
            else:
                print(f"  {key}: {value}")

    print("-" * 50)

    # Выводим распознанные строки
    print("\nРАСПОЗНАННЫЕ ТОВАРЫ:")
    if not lines:
        print("Не найдено ни одной строки! Проверьте качество изображения.")
    for i, line in enumerate(lines):
        name = line.get("name", "Unknown")
        qty = line.get("qty", 0)
        unit = line.get("unit", "")
        price = line.get("price", 0)
        amount = line.get("amount", 0)
        auto_fixed = "[ИСПРАВЛЕНО]" if line.get("auto_fixed") else ""

        print(f"{i+1}. {name}: {qty} {unit} × {price} = {amount} {auto_fixed}")

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

    # Выводим метрики
    if metrics:
        print("\nМЕТРИКИ ПРОИЗВОДИТЕЛЬНОСТИ:")
        print(f"Общее время обработки: {metrics.get('total_processing_ms', 0)} мс")
        print(f"Детекция таблицы: {metrics.get('table_detection_ms', 0)} мс")
        print(f"Обработка ячеек: {metrics.get('cell_processing_ms', 0)} мс")
        print(f"Построение строк: {metrics.get('line_building_ms', 0)} мс")
        print(f"Валидация: {metrics.get('validation_ms', 0)} мс")

        gpt4o_percent = metrics.get("gpt4o_percent", 0)
        gpt4o_count = metrics.get("gpt4o_count", 0)
        total_cells = metrics.get("total_cells", 0)
        print(f"Доля ячеек через GPT-4o: {gpt4o_percent:.1f}% ({gpt4o_count}/{total_cells})")

        if "cache_hits" in metrics:
            print(f"Попаданий в кэш: {metrics.get('cache_hits', 0)}")

    print("=" * 50)


async def run_comparison(image_bytes, languages, verbose=False):
    """Запускает сравнение производительности между старым и оптимизированным пайплайном."""
    try:
        # Импортируем оригинальный пайплайн
        from app.ocr_pipeline import OCRPipeline

        print("\n" + "=" * 50)
        print("СРАВНЕНИЕ ПРОИЗВОДИТЕЛЬНОСТИ")
        print("=" * 50)

        # Запускаем оригинальный пайплайн
        print("Запуск оригинального OCR-пайплайна...")
        original_pipeline = OCRPipeline(table_detector_method="paddle", paddle_ocr_lang="en")

        original_start = time.time()
        original_result = await original_pipeline.process_image(image_bytes, lang=languages)
        original_time = time.time() - original_start

        # Запускаем оптимизированный пайплайн
        print("Запуск оптимизированного OCR-пайплайна...")
        optimized_pipeline = OCRPipelineOptimized(
            table_detector_method="paddle", paddle_ocr_lang="en"
        )

        optimized_start = time.time()
        optimized_result = await optimized_pipeline.process_image(
            image_bytes, lang=languages, use_cache=False
        )
        optimized_time = time.time() - optimized_start

        # Выводим результаты сравнения
        print("\nРЕЗУЛЬТАТЫ СРАВНЕНИЯ:")
        print(f"Оригинальный пайплайн: {original_time:.2f} сек")
        print(f"Оптимизированный пайплайн: {optimized_time:.2f} сек")
        print(f"Ускорение: {(original_time / optimized_time):.2f}x")

        # Сравниваем количество распознанных строк
        original_lines = len(original_result.get("lines", []))
        optimized_lines = len(optimized_result.get("lines", []))
        print(f"Оригинальный: {original_lines} строк, Оптимизированный: {optimized_lines} строк")

        if verbose:
            print("\nСРАВНЕНИЕ СОДЕРЖИМОГО:")
            max_lines = max(original_lines, optimized_lines)
            for i in range(max_lines):
                orig_line = original_result.get("lines", [])[i] if i < original_lines else {}
                opt_line = optimized_result.get("lines", [])[i] if i < optimized_lines else {}

                orig_name = orig_line.get("name", "")
                opt_name = opt_line.get("name", "")

                if orig_name == opt_name:
                    print(f"Строка {i+1}: СОВПАДАЕТ - {orig_name}")
                else:
                    print(f"Строка {i+1}: РАЗЛИЧАЕТСЯ")
                    print(f"  Оригинальный: {orig_name}")
                    print(f"  Оптимизированный: {opt_name}")

        return optimized_result

    except ImportError:
        logger.error("Не удалось импортировать оригинальный OCR-пайплайн для сравнения")
        return None
    except Exception as e:
        logger.error(f"Ошибка при сравнении пайплайнов: {e}")
        if verbose:
            import traceback

            traceback.print_exc()
        return None


async def main():
    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Проверяем наличие файла
    image_path = Path(args.image)
    if not image_path.exists():
        logger.error(f"Файл не найден: {image_path}")
        return 1

    try:
        # Загружаем изображение
        with open(image_path, "rb") as f:
            image_bytes = f.read()

        logger.info(f"Загружено изображение размером {len(image_bytes)/1024:.1f} КБ")

        # Определяем языки
        languages = args.lang.split(",")

        # Если нужно сравнение - запускаем оба пайплайна
        if args.compare:
            result = await run_comparison(image_bytes, languages, args.verbose)
            if result is None:
                return 1
        else:
            # Создаем оптимизированный OCR-пайплайн
            pipeline = OCRPipelineOptimized(
                table_detector_method=args.detector,
                paddle_ocr_lang="en",
                fallback_to_vision=not args.no_fallback,
            )

            # Выполняем OCR
            logger.info(f"Запуск оптимизированного OCR-пайплайна с языками: {languages}...")
            result = await pipeline.process_image(
                image_bytes, lang=languages, use_cache=not args.no_cache
            )

        # Выводим результаты
        print_summary(result)

        # Сохраняем результаты, если указан путь
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, cls=DecimalEncoder)
            logger.info(f"Результаты сохранены в {args.output}")

        return 0

    except Exception as e:
        logger.error(f"Ошибка: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
