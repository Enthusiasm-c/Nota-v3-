#!/usr/bin/env python
"""
Скрипт для генерации отчета об оптимизациях проекта Nota-v3.
Собирает и анализирует данные о производительности до и после оптимизаций.
"""

import argparse
import glob
import json
import os
import statistics
import sys
from datetime import datetime

# Добавляем путь к корню проекта
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(project_root)


def load_json_files(directory, pattern="*.json"):
    """Загружает данные из всех JSON-файлов в указанной директории"""
    results = []
    for file_path in glob.glob(os.path.join(directory, pattern)):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                results.append(data)
        except Exception as e:
            print(f"Ошибка при загрузке файла {file_path}: {e}")
    return results


def calculate_statistics(results):
    """Рассчитывает статистику на основе результатов тестов"""
    if not results:
        return {}

    # Сбор данных
    ocr_times = []
    position_counts = []
    cache_hits = 0

    for result in results:
        if "processing_time" in result:
            ocr_times.append(result["processing_time"])
        if "positions" in result:
            position_counts.append(len(result["positions"]))
        if result.get("cache_hit", False):
            cache_hits += 1

    # Расчет статистики
    stats = {
        "total_tests": len(results),
        "cache_hits": cache_hits,
        "cache_hit_rate": cache_hits / len(results) if results else 0,
    }

    # Статистика по времени OCR
    if ocr_times:
        stats["ocr_time"] = {
            "min": min(ocr_times),
            "max": max(ocr_times),
            "avg": statistics.mean(ocr_times),
            "median": statistics.median(ocr_times),
        }

    # Статистика по количеству позиций
    if position_counts:
        stats["position_counts"] = {
            "min": min(position_counts),
            "max": max(position_counts),
            "avg": statistics.mean(position_counts),
            "total": sum(position_counts),
        }

    return stats


def generate_report(before_stats, after_stats, output_file):
    """Генерирует отчет сравнения производительности до и после оптимизаций"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Расчет улучшений
    improvements = {}

    if "ocr_time" in before_stats and "ocr_time" in after_stats:
        before_avg = before_stats["ocr_time"]["avg"]
        after_avg = after_stats["ocr_time"]["avg"]
        improvement_pct = (before_avg - after_avg) / before_avg * 100 if before_avg > 0 else 0
        improvements["ocr_time"] = {
            "before": before_avg,
            "after": after_avg,
            "improvement_pct": improvement_pct,
        }

    # Создание отчета
    report = {
        "timestamp": timestamp,
        "before": before_stats,
        "after": after_stats,
        "improvements": improvements,
    }

    # Сохранение отчета
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # Вывод на экран
    print(f"Отчет об оптимизации ({timestamp}):")
    print("=" * 50)

    print("\nСравнение производительности:")
    if "ocr_time" in improvements:
        print(
            f"Среднее время OCR: {improvements['ocr_time']['before']:.2f}s → {improvements['ocr_time']['after']:.2f}s"
        )
        print(f"Улучшение: {improvements['ocr_time']['improvement_pct']:.1f}%")

    if "cache_hit_rate" in after_stats:
        print(f"Эффективность кеша: {after_stats['cache_hit_rate']*100:.1f}%")

    print("\nДополнительные метрики:")
    if "position_counts" in after_stats:
        print(f"Среднее количество позиций: {after_stats['position_counts']['avg']:.1f}")

    print(f"\nОтчет сохранен в {output_file}")


def main():
    parser = argparse.ArgumentParser(description="Генерация отчета об оптимизациях")
    parser.add_argument(
        "--before", required=True, help="Директория с результатами тестов до оптимизаций"
    )
    parser.add_argument(
        "--after", required=True, help="Директория с результатами тестов после оптимизаций"
    )
    parser.add_argument(
        "--output", default="optimization_report.json", help="Путь для сохранения отчета"
    )
    args = parser.parse_args()

    # Загрузка данных
    before_results = load_json_files(args.before)
    after_results = load_json_files(args.after)

    if not before_results or not after_results:
        print("Ошибка: недостаточно данных для анализа")
        return 1

    # Расчет статистики
    before_stats = calculate_statistics(before_results)
    after_stats = calculate_statistics(after_results)

    # Генерация отчета
    generate_report(before_stats, after_stats, args.output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
