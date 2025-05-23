import pytest
import io
from PIL import Image
import numpy as np

from app.ocr_cleaner import (
    preprocess_for_ocr,
    resize_image
)

@pytest.fixture
def sample_image():
    """Создает тестовое изображение для тестов"""
    img = Image.new('RGB', (100, 100), color='white')
    # Добавим несколько черных точек для имитации текста
    img_array = np.array(img)
    img_array[30:70, 30:70] = (0, 0, 0)
    return Image.fromarray(img_array)

@pytest.fixture
def large_sample_image():
    """Создает большое тестовое изображение"""
    img = Image.new('RGB', (3000, 2000), color='white')
    img_array = np.array(img)
    img_array[1000:1500, 1000:1500] = (0, 0, 0)
    return Image.fromarray(img_array)

@pytest.fixture
def sample_image_bytes(sample_image):
    """Преобразует тестовое изображение в байты"""
    img_byte_arr = io.BytesIO()
    sample_image.save(img_byte_arr, format='JPEG')
    return img_byte_arr.getvalue()

@pytest.fixture
def large_image_bytes(large_sample_image):
    """Преобразует большое тестовое изображение в байты"""
    img_byte_arr = io.BytesIO()
    large_sample_image.save(img_byte_arr, format='JPEG')
    return img_byte_arr.getvalue()

def test_preprocess_for_ocr_small_image(sample_image_bytes):
    """Тест обработки маленького изображения"""
    # Запускаем функцию предобработки
    processed_bytes = preprocess_for_ocr(sample_image_bytes)
    
    # Проверяем, что результат не None и является байтами
    assert processed_bytes is not None
    assert isinstance(processed_bytes, bytes)
    
    # Проверяем, что размер изменился незначительно (только из-за сжатия JPEG)
    assert len(processed_bytes) > 0
    assert len(processed_bytes) <= len(sample_image_bytes)

def test_preprocess_for_ocr_large_image(large_image_bytes):
    """Тест обработки большого изображения"""
    # Запускаем функцию предобработки
    processed_bytes = preprocess_for_ocr(large_image_bytes)
    
    # Проверяем, что результат не None и является байтами
    assert processed_bytes is not None
    assert isinstance(processed_bytes, bytes)
    
    # Проверяем, что размер значительно уменьшился
    assert len(processed_bytes) > 0
    assert len(processed_bytes) < len(large_image_bytes)

def test_resize_image(large_sample_image):
    """Тест функции изменения размера изображения"""
    # Конвертируем в массив numpy
    img_array = np.array(large_sample_image)
    
    # Задаем максимальный размер
    max_size = 1024
    
    # Применяем изменение размера
    resized = resize_image(img_array, max_size)
    
    # Проверяем, что размеры не превышают максимальный
    height, width = resized.shape[:2]
    assert max(height, width) <= max_size
    
    # Проверяем, что пропорции сохранились
    original_ratio = img_array.shape[1] / img_array.shape[0]
    resized_ratio = width / height
    assert abs(original_ratio - resized_ratio) < 0.1

def test_preprocess_for_ocr_with_invalid_input():
    """Тест предобработки с невалидными входными данными"""
    # Тест с пустыми байтами
    result = preprocess_for_ocr(b"")
    assert result == b""
    
    # Тест с невалидным форматом изображения
    result = preprocess_for_ocr(b"not an image")
    assert result == b"not an image"
    
    # Тест с None
    with pytest.raises(Exception):
        preprocess_for_ocr(None)

def test_preprocess_for_ocr_file_types(sample_image):
    """Тест предобработки разных форматов изображений"""
    formats = ['JPEG', 'PNG', 'BMP']
    
    for fmt in formats:
        # Сохраняем изображение в определенном формате
        img_byte_arr = io.BytesIO()
        sample_image.save(img_byte_arr, format=fmt)
        img_bytes = img_byte_arr.getvalue()
        
        # Проверяем, что обработка работает для всех форматов
        processed = preprocess_for_ocr(img_bytes)
        assert processed is not None
        assert isinstance(processed, bytes)
        assert len(processed) > 0

def test_preprocess_for_ocr_quality_settings(sample_image_bytes):
    """Тест настроек качества JPEG"""
    # Тест с разными уровнями качества
    high_quality = preprocess_for_ocr(sample_image_bytes, {"jpeg_quality": 95})
    low_quality = preprocess_for_ocr(sample_image_bytes, {"jpeg_quality": 50})
    
    # Проверяем, что размер файла с низким качеством меньше
    assert len(low_quality) < len(high_quality)