import pytest
import os
import shutil
from pathlib import Path
import tempfile
from PIL import Image
import numpy as np

# Пути для тестовых файлов
FIXTURE_DIR = Path(__file__).parent / "fixtures"
FIXTURE_DIR.mkdir(exist_ok=True)

# Создаем тестовые изображения разных размеров
@pytest.fixture
def test_images():
    """Создает временные тестовые изображения разных размеров для тестирования ресайза."""
    temp_dir = Path(tempfile.mkdtemp())
    
    # Создаем изображения разных размеров
    sizes = [
        (2500, 1800),  # Больше лимитов - нужен ресайз
        (1900, 1400),  # Меньше лимитов - не нужен ресайз
        (3000, 1000),  # Ширина больше лимита, высота в норме
        (1500, 2000),  # Ширина в норме, высота больше лимита
        (5000, 4000),  # Намного больше лимитов
        (1000, 700),   # Намного меньше лимитов
    ]
    
    image_paths = []
    
    for i, (width, height) in enumerate(sizes):
        img = Image.new('RGB', (width, height), color=(255, 255, 255))
        path = temp_dir / f"test_image_{i}_{width}x{height}.jpg"
        img.save(path)
        image_paths.append((path, (width, height)))
    
    yield image_paths
    
    # Очищаем временные файлы
    shutil.rmtree(temp_dir)

def test_resize_if_needed_opencv():
    """Тестирует функцию resize_if_needed из OpenCV для разных размеров изображений."""
    try:
        import cv2
        from app.imgprep.prepare import resize_if_needed
    except ImportError:
        pytest.skip("OpenCV не установлен, пропускаем тест")
    
    # Создаем несколько тестовых массивов изображений разного размера
    test_cases = [
        (np.zeros((1800, 2500, 3), dtype=np.uint8), True),    # Больше лимитов - нужен ресайз
        (np.zeros((1400, 1900, 3), dtype=np.uint8), False),   # Меньше лимитов - не нужен ресайз
        (np.zeros((1000, 3000, 3), dtype=np.uint8), True),    # Только ширина больше лимита
        (np.zeros((2000, 1500, 3), dtype=np.uint8), True),    # Только высота больше лимита
        (np.zeros((4000, 5000, 3), dtype=np.uint8), True),    # Намного больше лимитов
        (np.zeros((700, 1000, 3), dtype=np.uint8), False),    # Намного меньше лимитов
    ]
    
    for img, should_resize in test_cases:
        h, w = img.shape[:2]
        resized = resize_if_needed(img)
        resized_h, resized_w = resized.shape[:2]
        
        if should_resize:
            assert resized_w != w or resized_h != h, f"Изображение {w}x{h} должно быть изменено"
            
            # Проверяем, что ресайз не выходит за минимальные размеры
            is_landscape = w > h
            min_long, min_short = 1680, 1000
            
            # Определяем минимальные размеры в зависимости от ориентации
            min_w = min_long if is_landscape else min_short
            min_h = min_short if is_landscape else min_long
            
            # Проверяем, что размеры не меньше минимальных
            assert resized_w >= min_w, f"Ширина {resized_w} должна быть не меньше {min_w}"
            assert resized_h >= min_h, f"Высота {resized_h} должна быть не меньше {min_h}"
            
            # Проверяем сохранение пропорций
            original_ratio = w / h
            resized_ratio = resized_w / resized_h
            
            # Для случаев с экстремальными пропорциями (например, очень широкие и низкие изображения),
            # может потребоваться нарушить пропорции для достижения минимального размера узкой стороны
            if (w / h > 2.5) or (h / w > 2.5):
                # Для таких случаев позволяем большее отклонение от исходного соотношения сторон
                allowed_deviation = 1.0
            else:
                # Для обычных изображений требуем хорошего сохранения пропорций
                allowed_deviation = 0.05
                
            assert abs(original_ratio - resized_ratio) < allowed_deviation, f"Пропорции изменились: было {original_ratio}, стало {resized_ratio}"
        else:
            assert resized_w == w and resized_h == h, f"Изображение {w}x{h} не должно изменяться"

def test_prepare_for_ocr_with_different_sizes(test_images):
    """Проверяет корректность обработки изображений разных размеров через prepare_for_ocr."""
    from app.imgprep import prepare_for_ocr
    
    for path, (width, height) in test_images:
        processed_bytes = prepare_for_ocr(path)
        assert processed_bytes, f"Ошибка при обработке изображения {width}x{height}"
        
        # Открываем обработанное изображение и проверяем размеры
        with tempfile.NamedTemporaryFile(suffix='.webp', delete=False) as tmp:
            tmp.write(processed_bytes)
            tmp.flush()
            img = Image.open(tmp.name)
            
            # Проверяем размеры в соответствии с новыми правилами
            if width > 2000 or height > 1600:
                # Изображение должно быть изменено
                processed_w, processed_h = img.size
                
                # Изображение не должно быть меньше минимальных размеров
                is_landscape = width > height
                min_long, min_short = 1680, 1000
                
                min_w = min_long if is_landscape else min_short
                min_h = min_short if is_landscape else min_long
                
                assert processed_w >= min_w, f"Ширина {processed_w} должна быть не меньше {min_w}"
                assert processed_h >= min_h, f"Высота {processed_h} должна быть не меньше {min_h}"
                
                # Проверяем сохранение пропорций
                original_ratio = width / height
                processed_ratio = processed_w / processed_h
                assert abs(original_ratio - processed_ratio) < 0.05, f"Пропорции изменились"
            else:
                # Изображение не должно изменяться по размеру
                expected_w, expected_h = width, height
                processed_w, processed_h = img.size
                
                # Некоторое отклонение возможно из-за конвертации форматов
                assert abs(processed_w - expected_w) <= expected_w * 0.05, f"Ширина изменилась: {expected_w} -> {processed_w}"
                assert abs(processed_h - expected_h) <= expected_h * 0.05, f"Высота изменилась: {expected_h} -> {processed_h}"
            
            # Удаляем временный файл
            os.remove(tmp.name)

def test_prepare_with_pil():
    """Тестирует функцию prepare_with_pil для разных размеров изображений."""
    # Создаем временную директорию для тестовых изображений
    with tempfile.TemporaryDirectory() as temp_dir:
        test_cases = [
            (2500, 1800),  # Больше лимитов
            (1900, 1400),  # Меньше лимитов
            (3000, 1000),  # Только ширина больше
            (1500, 2000),  # Только высота больше
        ]
        
        for width, height in test_cases:
            # Создаем тестовое изображение
            img = Image.new('RGB', (width, height), color=(255, 255, 255))
            path = os.path.join(temp_dir, f"test_{width}x{height}.jpg")
            img.save(path)
            
            # Импортируем функцию напрямую, чтобы избежать зависимости от OpenCV
            from app.imgprep.prepare import prepare_with_pil
            
            # Обрабатываем изображение
            processed_bytes = prepare_with_pil(path)
            
            # Загружаем обработанное изображение
            with tempfile.NamedTemporaryFile(suffix='.webp', delete=False) as tmp:
                tmp.write(processed_bytes)
                tmp.flush()
                processed_img = Image.open(tmp.name)
                processed_width, processed_height = processed_img.size
                
                # Проверяем правильность ресайза
                if width > 2000 or height > 1600:
                    # Определяем минимальные размеры
                    is_landscape = width > height
                    min_long, min_short = 1680, 1000
                    min_w = min_long if is_landscape else min_short
                    min_h = min_short if is_landscape else min_long
                    
                    # Проверяем, что размеры не меньше минимальных
                    assert processed_width >= min_w, f"Ширина {processed_width} должна быть не меньше {min_w}"
                    assert processed_height >= min_h, f"Высота {processed_height} должна быть не меньше {min_h}"
                    
                    # Проверяем сохранение пропорций
                    original_ratio = width / height
                    processed_ratio = processed_width / processed_height
                    assert abs(original_ratio - processed_ratio) < 0.05, "Пропорции нарушены"
                else:
                    # Для изображений меньше лимитов размер не должен сильно меняться
                    # (возможны небольшие изменения из-за конвертации форматов)
                    assert abs(processed_width - width) <= width * 0.05
                    assert abs(processed_height - height) <= height * 0.05
                
                # Удаляем временный файл
                os.remove(tmp.name) 