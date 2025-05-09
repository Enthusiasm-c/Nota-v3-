#!/usr/bin/env python
"""
Скрипт для автоматического тестирования OCR на стабильность.
Запускает OCR с разными вариантами искаженных накладных и анализирует результаты.
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from datetime import datetime

# Добавляем путь к проекту для импорта
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Импортируем модули для тестирования
from debug_ocr_direct import test_ocr
from compare_ocr_results import compare_results

async def test_variant(variant_path, reference_path, results_dir):
    """
    Тестирует OCR на конкретном варианте изображения
    
    Args:
        variant_path: путь к тестовому изображению
        reference_path: путь к эталонному JSON
        results_dir: директория для сохранения результатов
    
    Returns:
        dict: результаты тестирования
    """
    variant_name = os.path.basename(variant_path).replace('.jpg', '')
    print(f"\n[*] Тестирование варианта: {variant_name}")
    
    start_time = time.time()
    result_file = None
    error = None
    
    try:
        # Запускаем OCR на тестовом изображении
        await test_ocr(variant_path, reference_path)
        
        # Находим сохраненный результат
        result_files = [f for f in os.listdir('tmp') if f.startswith('ocr_result_') and f.endswith('.json')]
        if result_files:
            # Сортируем по времени создания (самый свежий)
            result_files.sort(key=lambda f: os.path.getmtime(os.path.join('tmp', f)), reverse=True)
            result_file = os.path.join('tmp', result_files[0])
            
            # Копируем результат в директорию результатов с именем варианта
            target_result = os.path.join(results_dir, f"result_{variant_name}.json")
            if os.path.exists(result_file):
                with open(result_file, 'r') as src:
                    result_data = json.load(src)
                    with open(target_result, 'w') as dst:
                        json.dump(result_data, dst, indent=2)
            
            # Запускаем сравнение с эталоном
            stats = compare_results(reference_path, result_file, 0.7)
            
            # Добавляем время обработки
            elapsed_time = time.time() - start_time
            if stats:
                stats["processing_time"] = elapsed_time
                stats["variant_name"] = variant_name
                stats["result_file"] = os.path.basename(target_result)
                return stats
        else:
            error = "Не найден результат OCR"
            return {
                "variant_name": variant_name,
                "error": error,
                "processing_time": time.time() - start_time,
                "success": False
            }
    except Exception as e:
        error = str(e)
        return {
            "variant_name": variant_name,
            "error": error,
            "processing_time": time.time() - start_time,
            "success": False
        }

async def run_stability_test():
    """
    Запускает тестирование OCR на всех вариантах искаженных накладных
    """
    # Создаем директории для результатов
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_dir = f"tmp/stability_test_{timestamp}"
    os.makedirs(results_dir, exist_ok=True)
    
    # Путь к эталонному JSON
    reference_path = "data/sample/invoice_reference.json"
    
    # Проверяем наличие файла
    if not os.path.exists(reference_path):
        print(f"Ошибка: эталонный JSON не найден по пути {reference_path}")
        return
    
    # Сначала создаем варианты, если они еще не созданы
    variants_dir = "tmp/test_variants"
    if not os.path.exists(variants_dir) or len(os.listdir(variants_dir)) < 4:
        print("[*] Создаем тестовые варианты накладных...")
        os.system("python test_ocr_variants.py")
    
    # Находим все варианты изображений
    variant_paths = [os.path.join(variants_dir, f) for f in os.listdir(variants_dir) if f.endswith('.jpg')]
    
    # Добавляем оригинальное изображение
    if os.path.exists("data/sample/invoice_test.jpg"):
        variant_paths.append("data/sample/invoice_test.jpg")
    
    if not variant_paths:
        print("Ошибка: не найдены тестовые варианты накладных")
        return
    
    print(f"[*] Найдено {len(variant_paths)} вариантов для тестирования")
    
    # Тестируем каждый вариант
    results = []
    for variant_path in variant_paths:
        try:
            result = await test_variant(variant_path, reference_path, results_dir)
            results.append(result)
        except Exception as e:
            print(f"[-] Ошибка при тестировании {variant_path}: {e}")
    
    # Сохраняем общие результаты
    summary_path = os.path.join(results_dir, "summary.json")
    with open(summary_path, 'w') as f:
        json.dump(results, f, indent=2)
    
    # Формируем итоговый отчет
    generate_report(results, results_dir)
    
    print(f"\n[+] Тестирование завершено. Результаты сохранены в {results_dir}")
    print(f"[+] Итоговый отчет: {os.path.join(results_dir, 'report.txt')}")

def generate_report(results, results_dir):
    """
    Генерирует отчет о результатах тестирования
    """
    report_path = os.path.join(results_dir, "report.txt")
    
    successful_tests = [r for r in results if "error" not in r or not r["error"]]
    failed_tests = [r for r in results if "error" in r and r["error"]]
    
    avg_quality = sum(r.get("quality", 0) for r in successful_tests) / len(successful_tests) if successful_tests else 0
    avg_fuzzy_quality = sum(r.get("fuzzy_quality", 0) for r in successful_tests) / len(successful_tests) if successful_tests else 0
    avg_time = sum(r.get("processing_time", 0) for r in results) / len(results) if results else 0
    
    with open(report_path, 'w') as f:
        f.write("=== Отчет о тестировании стабильности OCR ===\n\n")
        f.write(f"Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Всего тестов: {len(results)}\n")
        f.write(f"Успешных тестов: {len(successful_tests)}\n")
        f.write(f"Неудачных тестов: {len(failed_tests)}\n")
        f.write(f"Среднее качество OCR: {avg_quality:.2f}%\n")
        f.write(f"Среднее качество с нечетким сопоставлением: {avg_fuzzy_quality:.2f}%\n")
        f.write(f"Среднее время обработки: {avg_time:.2f} сек\n\n")
        
        if successful_tests:
            f.write("Детали успешных тестов:\n")
            for test in successful_tests:
                f.write(f"- {test['variant_name']}\n")
                f.write(f"  Точные совпадения: {test.get('exact_matches', 'N/A')}\n")
                f.write(f"  Частичные совпадения: {test.get('similar_matches', 'N/A')}\n")
                f.write(f"  Качество: {test.get('quality', 'N/A'):.2f}%\n")
                f.write(f"  Качество (нечеткое): {test.get('fuzzy_quality', 'N/A'):.2f}%\n")
                f.write(f"  Время: {test.get('processing_time', 'N/A'):.2f} сек\n\n")
        
        if failed_tests:
            f.write("Детали неудачных тестов:\n")
            for test in failed_tests:
                f.write(f"- {test['variant_name']}\n")
                f.write(f"  Ошибка: {test.get('error', 'Неизвестная ошибка')}\n")
                f.write(f"  Время до ошибки: {test.get('processing_time', 'N/A'):.2f} сек\n\n")
        
        f.write("=== Конец отчета ===\n")
    
    # Сокращенный вывод в консоль
    print("\n=== Итоги тестирования ===")
    print(f"Всего тестов: {len(results)}")
    print(f"Успешных: {len(successful_tests)}")
    print(f"Неудачных: {len(failed_tests)}")
    print(f"Среднее качество OCR: {avg_quality:.2f}%")
    print(f"Среднее качество (нечеткое): {avg_fuzzy_quality:.2f}%")
    print(f"Среднее время обработки: {avg_time:.2f} сек")

if __name__ == "__main__":
    asyncio.run(run_stability_test()) 