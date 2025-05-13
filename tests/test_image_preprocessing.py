import os
import sys
import pytest
from io import BytesIO
from PIL import Image
import numpy as np

# Добавляем путь к директории проекта в sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Импортируем функции предобработки изображений
from app.imgprep import prepare_for_ocr, resize_image

def create_test_image(width, height, color=(255, 255, 255)):
    """Создает тестовое изображение заданного размера"""
    img = Image.new('RGB', (width, height), color=color)
    output = BytesIO()
    img.save(output, format='JPEG', quality=90)
    return output.getvalue()

def test_resize_image_no_resize_needed():
    """Тест на сохранение размера для небольших изображений"""
    # Создаем небольшое изображение
    original_bytes = create_test_image(800, 600)
    
    # Обрабатываем изображение
    processed_bytes = resize_image(original_bytes)
    
    # Проверяем, что изображение не изменилось
    assert processed_bytes == original_bytes

def test_resize_image_large_image():
    """Тест на уменьшение размера для больших изображений"""
    # Создаем большое изображение
    original_bytes = create_test_image(2000, 1500)
    
    # Обрабатываем изображение
    processed_bytes = resize_image(original_bytes)
    
    # Проверяем, что размер изображения уменьшился
    assert len(processed_bytes) < len(original_bytes)
    
    # Проверяем, что размеры в пикселях изменились
    original_img = Image.open(BytesIO(original_bytes))
    processed_img = Image.open(BytesIO(processed_bytes))
    
    # Проверяем, что максимальный размер не превышает 1600
    assert max(processed_img.size) <= 1600
    
    # Проверяем, что соотношение сторон сохранилось
    original_ratio = original_img.width / original_img.height
    processed_ratio = processed_img.width / processed_img.height
    assert abs(original_ratio - processed_ratio) < 0.01  # Допускаем погрешность из-за округления

def test_prepare_for_ocr():
    """Тест основной функции prepare_for_ocr"""
    # Создаем изображение
    original_bytes = create_test_image(1800, 1200)
    
    # Сохраняем во временный файл
    temp_file = "tmp_test_image.jpg"
    with open(temp_file, "wb") as f:
        f.write(original_bytes)
    
    try:
        # Тестируем функцию с путем к файлу
        result_from_path = prepare_for_ocr(temp_file)
        
        # Тестируем функцию с байтами
        result_from_bytes = prepare_for_ocr(original_bytes)
        
        # Проверяем, что результаты примерно одинаковы
        assert abs(len(result_from_path) - len(result_from_bytes)) < 1024  # Допускаем небольшую разницу
        
        # Проверяем с отключенной предобработкой
        result_no_preprocessing = prepare_for_ocr(original_bytes, use_preprocessing=False)
        assert result_no_preprocessing == original_bytes
        
    finally:
        # Удаляем временный файл
        if os.path.exists(temp_file):
            os.remove(temp_file)

if __name__ == "__main__":
    pytest.main(["-v", __file__])