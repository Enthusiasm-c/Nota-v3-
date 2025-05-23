import os
import sys
import time
import pytest
from io import BytesIO
from PIL import Image

# Добавляем путь к директории проекта в sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Импортируем функции кеширования OCR
from app.utils.ocr_cache import get_image_hash, get_from_cache, save_to_cache, clear_cache, get_cache_stats
from app.models import ParsedData, Position

def create_test_image(width, height, color=(255, 255, 255)):
    """Создает тестовое изображение заданного размера"""
    img = Image.new('RGB', (width, height), color=color)
    output = BytesIO()
    img.save(output, format='JPEG', quality=90)
    return output.getvalue()

def create_test_parsed_data():
    """Создает тестовый объект ParsedData"""
    positions = [
        Position(name="Test Product 1", qty=2.0, unit="kg", price=10.0, total_price=20.0),
        Position(name="Test Product 2", qty=1.0, unit="pcs", price=15.0, total_price=15.0)
    ]
    return ParsedData(
        supplier="Test Supplier",
        positions=positions,
        total_price=35.0
    )

def test_get_image_hash():
    """Тест функции получения хеша изображения"""
    # Создаем два разных изображения
    image1 = create_test_image(100, 100, color=(255, 0, 0))
    image2 = create_test_image(100, 100, color=(0, 255, 0))
    
    # Получаем хеши
    hash1 = get_image_hash(image1)
    hash2 = get_image_hash(image2)
    
    # Проверяем, что хеши разные
    assert hash1 != hash2
    
    # Проверяем, что хеш одного и того же изображения одинаковый
    assert hash1 == get_image_hash(image1)

def test_cache_save_and_retrieve():
    """Тест сохранения и получения данных из кеша"""
    # Очищаем кеш перед тестом
    clear_cache()
    
    # Создаем тестовое изображение и данные
    image = create_test_image(200, 150)
    parsed_data = create_test_parsed_data()
    
    # Проверяем, что изначально в кеше нет данных
    assert get_from_cache(image) is None
    
    # Сохраняем в кеш
    save_to_cache(image, parsed_data)
    
    # Получаем из кеша
    cached_data = get_from_cache(image)
    
    # Проверяем, что данные сохранились
    assert cached_data is not None
    assert cached_data.supplier == parsed_data.supplier
    assert len(cached_data.positions) == len(parsed_data.positions)
    assert cached_data.total_price == parsed_data.total_price

def test_cache_stats():
    """Тест получения статистики кеша"""
    # Очищаем кеш перед тестом
    clear_cache()
    
    # Проверяем начальную статистику
    stats = get_cache_stats()
    assert stats["total_entries"] == 0
    
    # Добавляем элементы в кеш
    for i in range(3):
        image = create_test_image(100, 100, color=(i*50, i*50, i*50))
        parsed_data = create_test_parsed_data()
        save_to_cache(image, parsed_data)
    
    # Проверяем обновленную статистику
    stats = get_cache_stats()
    assert stats["total_entries"] == 3
    assert stats["active_entries"] == 3

def test_cache_expiration():
    """Тест на устаревание кеша (требует модификации TTL для тестирования)"""
    # Этот тест можно выполнить только с временным изменением TTL в модуле ocr_cache
    # Для промышленного кода рекомендуется использовать инъекцию зависимостей или моки
    import app.utils.ocr_cache as ocr_cache
    original_ttl = ocr_cache.CACHE_TTL
    
    try:
        # Устанавливаем короткий TTL для тестирования
        ocr_cache.CACHE_TTL = 0.1  # 100 миллисекунд
        
        # Очищаем кеш перед тестом
        clear_cache()
        
        # Добавляем элемент в кеш
        image = create_test_image(100, 100)
        parsed_data = create_test_parsed_data()
        save_to_cache(image, parsed_data)
        
        # Проверяем, что элемент есть в кеше
        assert get_from_cache(image) is not None
        
        # Ждем, пока элемент устареет
        time.sleep(0.2)
        
        # Проверяем, что элемент больше недоступен
        assert get_from_cache(image) is None
        
    finally:
        # Восстанавливаем исходное значение TTL
        ocr_cache.CACHE_TTL = original_ttl

if __name__ == "__main__":
    pytest.main(["-v", __file__])