#!/usr/bin/env python
"""
Скрипт для создания различных вариантов тестового изображения накладной
с внесенными ошибками для проверки устойчивости OCR и бота.
"""

import json
import os
import random
import sys
from copy import deepcopy
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

# Подключаем модуль для создания тестовых изображений
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from create_test_image import create_invoice_image

def load_reference_data(reference_path):
    """Загружает данные из эталонного JSON"""
    with open(reference_path, 'r') as f:
        return json.load(f)

def save_variant_data(data, output_path):
    """Сохраняет модифицированные данные в JSON"""
    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)

def create_variant_with_typos(data, output_json, output_img):
    """Создает вариант с опечатками в названиях товаров"""
    variant_data = deepcopy(data)
    
    # Вносим опечатки в 30% названий товаров
    for pos in variant_data["positions"]:
        if random.random() < 0.3:
            name = pos["name"]
            if len(name) > 3:
                # Заменяем случайную букву
                idx = random.randint(1, len(name) - 2)
                name = name[:idx] + random.choice("abcdefghijklmnopqrstuvwxyz") + name[idx+1:]
                pos["name"] = name
    
    # Сохраняем модифицированные данные
    save_variant_data(variant_data, output_json)
    
    # Создаем изображение
    create_invoice_image(output_json, output_img)
    
    return f"Создан вариант с опечатками: {output_img}"

def create_variant_with_missing_items(data, output_json, output_img):
    """Создает вариант с отсутствующими позициями"""
    variant_data = deepcopy(data)
    
    # Удаляем 20% позиций
    if len(variant_data["positions"]) > 5:
        num_to_remove = max(1, int(len(variant_data["positions"]) * 0.2))
        indices_to_remove = random.sample(range(len(variant_data["positions"])), num_to_remove)
        variant_data["positions"] = [pos for i, pos in enumerate(variant_data["positions"]) if i not in indices_to_remove]
    
    # Сохраняем модифицированные данные
    save_variant_data(variant_data, output_json)
    
    # Создаем изображение
    create_invoice_image(output_json, output_img)
    
    return f"Создан вариант с отсутствующими позициями: {output_img}"

def create_variant_with_price_errors(data, output_json, output_img):
    """Создает вариант с ошибками в ценах и суммах"""
    variant_data = deepcopy(data)
    
    # Вносим ошибки в 30% цен или сумм
    for pos in variant_data["positions"]:
        if random.random() < 0.3:
            if random.random() < 0.5:
                # Ошибка в цене
                pos["price"] = round(pos["price"] * (1 + random.uniform(-0.1, 0.1)))
            else:
                # Ошибка в сумме
                pos["total_price"] = round(pos["total_price"] * (1 + random.uniform(-0.1, 0.1)))
    
    # Сохраняем модифицированные данные
    save_variant_data(variant_data, output_json)
    
    # Создаем изображение
    create_invoice_image(output_json, output_img)
    
    return f"Создан вариант с ошибками в ценах: {output_img}"

def create_variant_with_blurred_image(data, output_json, output_img):
    """Создает вариант с размытым изображением"""
    # Сохраняем данные без изменений
    save_variant_data(data, output_json)
    
    # Создаем стандартное изображение
    create_invoice_image(output_json, output_img)
    
    # Добавляем размытие
    img = Image.open(output_img)
    img = img.filter(ImageFilter.GaussianBlur(radius=1.2))
    img.save(output_img)
    
    return f"Создан вариант с размытым изображением: {output_img}"

def create_variant_with_low_contrast(data, output_json, output_img):
    """Создает вариант с низким контрастом"""
    # Сохраняем данные без изменений
    save_variant_data(data, output_json)
    
    # Создаем стандартное изображение
    create_invoice_image(output_json, output_img)
    
    # Уменьшаем контраст
    img = Image.open(output_img)
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(0.7)  # Снижаем контраст на 30%
    img.save(output_img)
    
    return f"Создан вариант с низким контрастом: {output_img}"

def create_variant_with_different_units(data, output_json, output_img):
    """Создает вариант с измененными единицами измерения"""
    variant_data = deepcopy(data)
    
    # Список альтернативных единиц измерения
    unit_options = ["kg", "g", "pcs", "box", "pack", "can", "btl"]
    
    # Меняем единицы измерения в 30% позиций
    for pos in variant_data["positions"]:
        if random.random() < 0.3 and "unit" in pos:
            current_unit = pos.get("unit", "pcs")
            alternatives = [u for u in unit_options if u != current_unit]
            pos["unit"] = random.choice(alternatives)
    
    # Сохраняем модифицированные данные
    save_variant_data(variant_data, output_json)
    
    # Создаем изображение
    create_invoice_image(output_json, output_img)
    
    return f"Создан вариант с измененными единицами измерения: {output_img}"

def create_variant_with_duplicated_items(data, output_json, output_img):
    """Создает вариант с дублированными позициями"""
    variant_data = deepcopy(data)
    
    # Дублируем несколько позиций
    if len(variant_data["positions"]) > 3:
        num_to_duplicate = max(1, int(len(variant_data["positions"]) * 0.15))
        for _ in range(num_to_duplicate):
            idx = random.randint(0, len(variant_data["positions"]) - 1)
            variant_data["positions"].append(deepcopy(variant_data["positions"][idx]))
    
    # Сохраняем модифицированные данные
    save_variant_data(variant_data, output_json)
    
    # Создаем изображение
    create_invoice_image(output_json, output_img)
    
    return f"Создан вариант с дублированными позициями: {output_img}"

def main():
    # Директории для тестовых вариантов
    os.makedirs("tmp/test_variants", exist_ok=True)
    
    # Путь к эталонному JSON
    reference_path = "data/sample/invoice_reference.json"
    
    # Проверяем наличие файла
    if not os.path.exists(reference_path):
        print(f"Ошибка: эталонный JSON не найден по пути {reference_path}")
        return
    
    # Загружаем эталонные данные
    reference_data = load_reference_data(reference_path)
    
    # Создаем разные варианты для тестирования
    variants = [
        ("typos", create_variant_with_typos),
        ("missing_items", create_variant_with_missing_items),
        ("price_errors", create_variant_with_price_errors),
        ("blurred", create_variant_with_blurred_image),
        ("low_contrast", create_variant_with_low_contrast),
        ("different_units", create_variant_with_different_units),
        ("duplicated_items", create_variant_with_duplicated_items)
    ]
    
    results = []
    for variant_name, variant_func in variants:
        output_json = f"tmp/test_variants/invoice_{variant_name}.json"
        output_img = f"tmp/test_variants/invoice_{variant_name}.jpg"
        
        result = variant_func(reference_data, output_json, output_img)
        results.append(result)
    
    # Выводим результаты
    print("Созданы следующие тестовые варианты:")
    for result in results:
        print(f"- {result}")
    
    print(f"\nДля тестирования вариантов используйте команду:")
    print(f"python debug_ocr_direct.py tmp/test_variants/invoice_XXX.jpg")

if __name__ == "__main__":
    main() 