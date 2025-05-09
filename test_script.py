#!/usr/bin/env python
"""
Тестовый скрипт для проверки улучшенного мэтчинга товаров
"""

import json
import os
from app import data_loader, matcher
from app.postprocessing import normalize_units, postprocess_parsed_data
from app.models import ParsedData, Position

def test_product_normalization():
    """Тестирование нормализации названий продуктов"""
    print("=== Тестирование нормализации названий продуктов ===")
    
    test_cases = [
        "romaine", 
        "Romana", 
        "tomato", 
        "Tomato", 
        "tomatoes",
        "chickpeas", 
        "chick peas", 
        "green bean", 
        "green beans",
        "eggplant",
        "aubergine"
    ]
    
    for name in test_cases:
        normalized = matcher.normalize_product_name(name)
        print(f"{name:15} → {normalized}")
    
    print()

def test_unit_normalization():
    """Тестирование нормализации единиц измерения"""
    print("=== Тестирование нормализации единиц измерения ===")
    
    test_cases = [
        ("pcs", "mushroom"),
        ("kg", "tomato"),
        ("krat", "egg"),
        ("ea", "apple"),
        ("each", "pineapple"),
        ("bottles", "water"),
        ("", "watermelon"),  # Пустая единица измерения
        ("", "cheese"),      # Пустая единица измерения
    ]
    
    for unit, product in test_cases:
        normalized = normalize_units(unit, product)
        print(f"{unit:10} для {product:15} → {normalized}")
    
    print()

def test_string_similarity():
    """Тестирование улучшенного алгоритма сравнения строк"""
    print("=== Тестирование сравнения строк ===")
    
    test_pairs = [
        ("romaine", "romana"),
        ("romana", "romaine"),
        ("green bean", "green beans"),
        ("chickpeas", "chick peas"),
        ("tomato", "tomatoes"),
        ("eggplant", "aubergine"),
        ("english spinach", "local spinach"),  # Разные продукты
        ("potato", "tomato"),                  # Разные продукты
        ("mushroom", "mushrooms"),
        ("chick peas", "chickpea")
    ]
    
    for s1, s2 in test_pairs:
        score = matcher.calculate_string_similarity(s1, s2)
        status = "MATCH" if score > 0.9 else "PARTIAL" if score > 0.7 else "NO MATCH"
        print(f"{s1:20} ↔ {s2:20} = {score:.2f} [{status}]")
    
    print()

def test_mock_data_matching():
    """Тестирование сопоставления с использованием тестовых данных"""
    print("=== Тестирование сопоставления данных OCR с базой ===")
    
    # Тестовые данные OCR с проблемными вариациями
    test_positions = [
        {"name": "Romana", "qty": 1.0, "unit": "pcs", "price": 55000, "total_price": 55000},
        {"name": "green beans", "qty": 0.5, "unit": "kg", "price": 18000, "total_price": 9000},
        {"name": "chick peas", "qty": 12.0, "unit": "pcs", "price": 32000, "total_price": 384000},
        {"name": "Tomatoes", "qty": 2.0, "unit": "kg", "price": 20000, "total_price": 40000},
        {"name": "Aubergine", "qty": 1.0, "unit": "pcs", "price": 15000, "total_price": 15000},
        {"name": "eggplant", "qty": 1.0, "unit": "pcs", "price": 15000, "total_price": 15000},
    ]
    
    # Загрузка продуктов из базы
    products = data_loader.load_products()
    
    # Тестируем улучшенный мэтчинг
    print("Результаты сопоставления:")
    matched_positions = matcher.match_positions(test_positions, products, threshold=0.7)
    
    for i, pos in enumerate(matched_positions):
        status_symbol = "✓" if pos["status"] == "ok" else "≈" if pos["status"] == "partial" else "✗"
        print(f"{i+1}. {pos['name']:20} [{pos['status']:8}] {status_symbol} (score: {pos.get('score', 0):.2f})")
    
    # Тестирование постобработки данных
    print("\nПостобработка данных:")
    
    # Создаем тестовый объект ParsedData
    positions = []
    for pos_dict in test_positions:
        positions.append(Position(
            name=pos_dict["name"],
            qty=pos_dict["qty"],
            unit=pos_dict["unit"],
            price=pos_dict["price"],
            total_price=pos_dict["total_price"]
        ))
    
    parsed_data = ParsedData(
        supplier="UD. WIDI WIGUNA",
        date="2025-04-20",
        positions=positions,
        total_price=518000
    )
    
    # Применяем постобработку
    processed_data = postprocess_parsed_data(parsed_data)
    
    # Выводим результаты постобработки
    for i, pos in enumerate(processed_data.positions):
        print(f"{i+1}. {pos.name:20} - {pos.qty} {pos.unit:3} × {pos.price} = {pos.total_price}")
    
    print(f"Total: {processed_data.total_price}")

if __name__ == "__main__":
    test_product_normalization()
    test_unit_normalization()
    test_string_similarity()
    test_mock_data_matching() 