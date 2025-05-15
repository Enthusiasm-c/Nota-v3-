import pytest
from unittest.mock import MagicMock, patch
import os
import io
from PIL import Image
import numpy as np

from app.ocr_cleaner import (
    preprocess_for_ocr, 
    apply_thresholding,
    remove_noise, 
    straighten_image,
    enhance_contrast
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
def sample_image_bytes(sample_image):
    """Преобразует тестовое изображение в байты"""
    img_byte_arr = io.BytesIO()
    sample_image.save(img_byte_arr, format='JPEG')
    return img_byte_arr.getvalue()

def test_preprocess_for_ocr(sample_image_bytes):
    """Тест полного процесса предобработки изображения"""
    # Запускаем функцию предобработки
    processed_bytes = preprocess_for_ocr(sample_image_bytes)
    
    # Проверяем, что результат не None и является байтами
    assert processed_bytes is not None
    assert isinstance(processed_bytes, bytes)
    
    # Проверяем, что размер изменился (обычно уменьшается после оптимизации)
    assert len(processed_bytes) > 0
    assert len(processed_bytes) <= len(sample_image_bytes)

def test_apply_thresholding(sample_image):
    """Тест применения пороговой обработки к изображению"""
    # Конвертируем в массив numpy для преобработки
    img_array = np.array(sample_image)
    
    # Применяем пороговую обработку
    processed = apply_thresholding(img_array)
    
    # Проверяем, что результат имеет ожидаемую форму и тип
    assert processed.shape == img_array.shape
    assert processed.dtype == np.uint8
    
    # Проверяем, что изображение стало более контрастным (имеет меньше уникальных значений)
    assert len(np.unique(processed)) <= len(np.unique(img_array))

def test_remove_noise(sample_image):
    """Тест удаления шума из изображения"""
    # Конвертируем в массив numpy для преобработки
    img_array = np.array(sample_image)
    
    # Добавляем случайный шум
    noisy_img = img_array.copy()
    noisy_img[10:20, 10:20] = np.random.randint(0, 255, size=(10, 10, 3), dtype=np.uint8)
    
    # Применяем удаление шума
    denoised = remove_noise(noisy_img)
    
    # Проверяем, что форма и тип данных сохранились
    assert denoised.shape == noisy_img.shape
    assert denoised.dtype == np.uint8
    
    # Проверяем, что какая-то обработка произошла (пиксели изменились)
    assert not np.array_equal(denoised, noisy_img)

def test_straighten_image(sample_image):
    """Тест выпрямления изображения"""
    # Конвертируем в массив numpy
    img_array = np.array(sample_image)
    
    # Применяем выпрямление
    straightened = straighten_image(img_array)
    
    # Проверяем, что изображение не пустое и имеет правильную форму
    assert straightened.shape[:2] == img_array.shape[:2]
    assert straightened.dtype == np.uint8

def test_enhance_contrast(sample_image):
    """Тест улучшения контрастности изображения"""
    # Конвертируем в массив numpy
    img_array = np.array(sample_image)
    
    # Создаем изображение с низким контрастом
    low_contrast = img_array.copy()
    low_contrast = (low_contrast * 0.5).astype(np.uint8)
    
    # Применяем улучшение контраста
    enhanced = enhance_contrast(low_contrast)
    
    # Проверяем, что форма и тип данных сохранились
    assert enhanced.shape == low_contrast.shape
    assert enhanced.dtype == np.uint8
    
    # Проверяем, что контраст действительно улучшился
    # (стандартное отклонение значений пикселей должно увеличиться)
    assert np.std(enhanced) >= np.std(low_contrast)

def test_preprocess_for_ocr_with_invalid_input():
    """Тест предобработки с невалидными входными данными"""
    # Тест с пустыми байтами
    with pytest.raises(Exception):
        preprocess_for_ocr(b"")
    
    # Тест с невалидным форматом изображения
    with pytest.raises(Exception):
        preprocess_for_ocr(b"not an image")
    
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