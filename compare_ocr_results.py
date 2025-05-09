#!/usr/bin/env python
"""
Скрипт для сравнения результатов OCR с эталонными данными
с использованием нечеткого сопоставления (fuzzy matching).
"""

import json
import os
import sys
from difflib import SequenceMatcher

def string_similarity(a, b):
    """
    Вычисляет сходство между двумя строками по алгоритму SequenceMatcher.
    
    Args:
        a, b: Строки для сравнения
        
    Returns:
        Значение сходства от 0 до 1
    """
    a = a.lower().strip()
    b = b.lower().strip()
    
    # Быстрая проверка на идентичность
    if a == b:
        return 1.0
    
    # Вычисляем сходство
    return SequenceMatcher(None, a, b).ratio()

def compare_results(reference_path, result_path, similarity_threshold=0.8):
    """
    Сравнивает результаты OCR с эталоном с использованием нечеткого сопоставления.
    
    Args:
        reference_path: Путь к эталонному JSON
        result_path: Путь к JSON с результатами OCR
        similarity_threshold: Порог сходства для нечеткого сопоставления (0.0-1.0)
        
    Returns:
        Статистика сравнения
    """
    print(f"[*] Сравнение результатов OCR с эталоном:")
    print(f"    Эталон:   {reference_path}")
    print(f"    Результат: {result_path}")
    print(f"    Порог сходства: {similarity_threshold:.2f}")
    
    # Загружаем данные
    try:
        with open(reference_path, 'r') as f:
            reference = json.load(f)
        
        with open(result_path, 'r') as f:
            result = json.load(f)
    except Exception as e:
        print(f"[-] Ошибка загрузки файлов: {e}")
        return
    
    # Базовое сравнение метаданных
    if reference.get("supplier") == result.get("supplier"):
        print(f"[+] Поставщик: {reference.get('supplier')} ✓")
    else:
        similarity = string_similarity(str(reference.get('supplier', '')), str(result.get('supplier', '')))
        if similarity >= similarity_threshold:
            print(f"[~] Поставщик: {reference.get('supplier')} ≈ {result.get('supplier')} ({similarity:.2f})")
        else:
            print(f"[-] Поставщик: {reference.get('supplier')} ≠ {result.get('supplier')} ✗")
    
    if reference.get("date") == result.get("date"):
        print(f"[+] Дата: {reference.get('date')} ✓")
    else:
        print(f"[-] Дата: {reference.get('date')} ≠ {result.get('date')} ✗")
    
    # Сравнение позиций
    ref_positions = reference.get("positions", [])
    result_positions = result.get("positions", [])
    
    print(f"[*] Сравнение позиций: эталон {len(ref_positions)}, результат {len(result_positions)}")
    
    # Создаем матрицу сходства для фаззи-сопоставления
    matches = []
    for ref_idx, ref_pos in enumerate(ref_positions):
        ref_name = ref_pos["name"].lower()
        
        for res_idx, res_pos in enumerate(result_positions):
            res_name = res_pos["name"].lower()
            
            # Вычисляем сходство
            similarity = string_similarity(ref_name, res_name)
            
            if similarity >= similarity_threshold:
                matches.append({
                    "ref_idx": ref_idx,
                    "res_idx": res_idx,
                    "similarity": similarity,
                    "ref": ref_pos,
                    "res": res_pos
                })
    
    # Сортируем совпадения по убыванию схожести
    matches.sort(key=lambda x: x["similarity"], reverse=True)
    
    # Выбираем лучшие совпадения (жадный алгоритм)
    used_ref = set()
    used_res = set()
    best_matches = []
    
    for match in matches:
        ref_idx = match["ref_idx"]
        res_idx = match["res_idx"]
        
        if ref_idx not in used_ref and res_idx not in used_res:
            best_matches.append(match)
            used_ref.add(ref_idx)
            used_res.add(res_idx)
    
    # Анализируем результаты
    exact_matches = []
    similar_matches = []
    missing_items = []
    extra_items = []
    
    # Обработка совпадений
    for match in best_matches:
        ref_pos = match["ref"]
        res_pos = match["res"]
        similarity = match["similarity"]
        
        # Проверяем на точное совпадение всех полей
        if (ref_pos["qty"] == res_pos["qty"] and
            ref_pos["price"] == res_pos["price"] and
            ref_pos["total_price"] == res_pos["total_price"] and
            similarity == 1.0):
            exact_matches.append(match)
        else:
            similar_matches.append(match)
    
    # Поиск отсутствующих позиций
    for i, ref_pos in enumerate(ref_positions):
        if i not in used_ref:
            missing_items.append(ref_pos)
    
    # Поиск лишних позиций
    for i, res_pos in enumerate(result_positions):
        if i not in used_res:
            extra_items.append(res_pos)
    
    # Выводим детальные результаты
    print(f"\n[*] Детальный анализ результатов:")
    
    if similar_matches:
        print(f"\n[*] Частично совпадающие позиции ({len(similar_matches)}):")
        for match in similar_matches:
            ref_pos = match["ref"]
            res_pos = match["res"]
            similarity = match["similarity"]
            
            print(f"  [~] '{ref_pos['name']}' ≈ '{res_pos['name']}' ({similarity:.2f})")
            print(f"      Эталон:   кол-во: {ref_pos['qty']}, цена: {ref_pos['price']}, сумма: {ref_pos['total_price']}")
            print(f"      Результат: кол-во: {res_pos['qty']}, цена: {res_pos['price']}, сумма: {res_pos['total_price']}")
    
    if missing_items:
        print(f"\n[-] Отсутствующие позиции ({len(missing_items)}):")
        for item in missing_items:
            print(f"  [-] '{item['name']}' (кол-во: {item['qty']}, цена: {item['price']}, сумма: {item['total_price']})")
    
    if extra_items:
        print(f"\n[!] Лишние позиции ({len(extra_items)}):")
        for item in extra_items:
            print(f"  [!] '{item['name']}' (кол-во: {item['qty']}, цена: {item['price']}, сумма: {item['total_price']})")
    
    # Итоговая статистика
    print(f"\n[*] Итоги сравнения:")
    print(f"    Всего позиций в эталоне: {len(ref_positions)}")
    print(f"    Точные совпадения: {len(exact_matches)}")
    print(f"    Частичные совпадения: {len(similar_matches)}")
    print(f"    Отсутствующие позиции: {len(missing_items)}")
    print(f"    Лишние позиции: {len(extra_items)}")
    
    # Расчет коэффициента качества с учетом нечеткого сопоставления
    quality = 0.0
    if len(ref_positions) > 0:
        weighted_matches = len(exact_matches) + len(similar_matches) * 0.5
        weighted_count = len(ref_positions)
        quality = (weighted_matches / weighted_count) * 100
    
    print(f"[*] Общая оценка качества OCR: {quality:.1f}%")
    
    # Расчет коэффициента качества с учетом нечеткого сопоставления и качества совпадений
    fuzzy_quality = 0.0
    if len(ref_positions) > 0:
        # Учитываем качество каждого нечеткого совпадения на основе схожести
        fuzzy_score = len(exact_matches)
        for match in similar_matches:
            fuzzy_score += match["similarity"] * 0.5
        
        fuzzy_quality = (fuzzy_score / len(ref_positions)) * 100
    
    print(f"[*] Улучшенная оценка с учетом нечеткого сопоставления: {fuzzy_quality:.1f}%")
    
    return {
        "exact_matches": len(exact_matches),
        "similar_matches": len(similar_matches),
        "missing_items": len(missing_items),
        "extra_items": len(extra_items),
        "quality": quality,
        "fuzzy_quality": fuzzy_quality
    }

def main():
    """
    Основная функция скрипта
    """
    if len(sys.argv) < 3:
        print(f"Использование: {sys.argv[0]} <эталонный_json> <результат_json> [порог_сходства]")
        print(f"Пример: {sys.argv[0]} data/sample/invoice_reference.json tmp/ocr_result_1234567890.json 0.8")
        return
    
    reference_path = sys.argv[1]
    result_path = sys.argv[2]
    similarity_threshold = float(sys.argv[3]) if len(sys.argv) > 3 else 0.8
    
    # Проверяем наличие файлов
    if not os.path.exists(reference_path):
        print(f"[-] Эталонный файл не найден: {reference_path}")
        return
    
    if not os.path.exists(result_path):
        print(f"[-] Файл с результатами не найден: {result_path}")
        return
    
    # Запускаем сравнение
    compare_results(reference_path, result_path, similarity_threshold)

if __name__ == "__main__":
    main() 