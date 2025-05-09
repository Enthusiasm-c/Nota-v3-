#!/usr/bin/env python
"""
Скрипт для создания тестового изображения инвойса на основе данных из эталонного JSON.
"""

import json
import os
from PIL import Image, ImageDraw, ImageFont
import numpy as np

def create_invoice_image(reference_path, output_path, width=800, height=1200):
    """
    Создает тестовое изображение инвойса на основе данных из JSON.
    """
    # Загружаем данные из JSON
    with open(reference_path, 'r') as f:
        data = json.load(f)
    
    # Создаем пустое изображение
    img = Image.new('RGB', (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    # Пытаемся загрузить шрифт
    try:
        font = ImageFont.truetype("Arial", 16)
        title_font = ImageFont.truetype("Arial", 22)
        small_font = ImageFont.truetype("Arial", 12)
    except IOError:
        # Используем стандартный шрифт, если Arial не найден
        font = ImageFont.load_default()
        title_font = font
        small_font = font
    
    # Рисуем заголовок (поставщик)
    draw.text((50, 30), data.get("supplier", "SUPPLIER NAME"), fill=(0, 0, 200), font=title_font)
    
    # Рисуем дату
    draw.text((width-150, 30), data.get("date", "DATE"), fill=(0, 0, 0), font=font)
    
    # Рисуем таблицу
    start_y = 100
    col_widths = [50, 50, 200, 100, 100]
    col_starts = [50]
    for i in range(1, len(col_widths)):
        col_starts.append(col_starts[i-1] + col_widths[i-1])
    
    # Заголовки таблицы
    headers = ["№", "Кол-во", "Наименование", "Цена", "Сумма"]
    header_y = start_y
    
    # Рисуем границы таблицы и заголовки
    for i, header in enumerate(headers):
        # Рисуем ячейку заголовка
        draw.rectangle(
            [col_starts[i], header_y, col_starts[i] + col_widths[i], header_y + 30],
            outline=(0, 0, 0),
            fill=(230, 230, 255)
        )
        # Пишем текст заголовка
        draw.text(
            (col_starts[i] + 5, header_y + 5),
            header,
            fill=(0, 0, 0),
            font=font
        )
    
    # Данные таблицы
    positions = data.get("positions", [])
    row_height = 30
    current_y = header_y + row_height
    
    for i, pos in enumerate(positions):
        # Ограничиваем количество строк, чтобы влезли на изображение
        if i >= 30:  # Максимум 30 строк
            break
        
        # Рисуем строку
        pos_data = [
            str(i+1),  # №
            str(pos.get("qty", "")),  # Количество
            pos.get("name", ""),  # Наименование
            str(pos.get("price", "")),  # Цена
            str(pos.get("total_price", "")),  # Сумма
        ]
        
        for j, cell_data in enumerate(pos_data):
            # Рисуем ячейку
            draw.rectangle(
                [col_starts[j], current_y, col_starts[j] + col_widths[j], current_y + row_height],
                outline=(0, 0, 0),
                fill=(255, 255, 255)
            )
            # Пишем текст ячейки
            draw.text(
                (col_starts[j] + 5, current_y + 5),
                cell_data,
                fill=(0, 0, 100),
                font=small_font
            )
        
        current_y += row_height
    
    # Рисуем итоговую сумму
    if "total_price" in data:
        draw.text(
            (col_starts[3], current_y + 10),
            "ИТОГО:",
            fill=(0, 0, 0),
            font=font
        )
        draw.text(
            (col_starts[4], current_y + 10),
            str(data["total_price"]),
            fill=(0, 0, 0),
            font=font
        )
    
    # Сохраняем изображение
    img.save(output_path)
    print(f"Создано тестовое изображение: {output_path}")

def main():
    # Создаем необходимые директории
    os.makedirs("data/sample", exist_ok=True)
    os.makedirs("tmp", exist_ok=True)
    
    # Путь к эталонному JSON и выходному изображению
    reference_path = "data/sample/invoice_reference.json"
    output_path = "data/sample/invoice_test.jpg"
    
    # Проверяем наличие эталонного JSON
    if not os.path.exists(reference_path):
        print(f"Ошибка: эталонный JSON не найден: {reference_path}")
        return
    
    # Создаем тестовое изображение
    create_invoice_image(reference_path, output_path)

if __name__ == "__main__":
    main() 