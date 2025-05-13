"""
Базовый модуль оптимизации изображений (облегченная версия).
Выполняет только необходимые операции для обеспечения совместимости.
"""

import io
from typing import Union, Optional
from PIL import Image


def resize_image(image_bytes: bytes, max_size: int = 1600, quality: int = 90) -> bytes:
    """
    Изменяет размер изображения, если оно превышает максимальный размер.
    Возвращает оптимизированные байты изображения.
    
    Args:
        image_bytes: Байты исходного изображения
        max_size: Максимальный размер (ширина или высота) в пикселях
        quality: Качество сжатия JPEG (0-100)
        
    Returns:
        bytes: Оптимизированные байты изображения
    """
    try:
        img = Image.open(io.BytesIO(image_bytes))
        
        # Если изображение меньше максимального размера, возвращаем как есть
        if max(img.size) <= max_size and len(image_bytes) <= 1.5 * 1024 * 1024:
            return image_bytes
            
        # Изменяем размер с сохранением соотношения сторон
        if max(img.size) > max_size:
            ratio = max_size / max(img.size)
            new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
            img = img.resize(new_size, Image.LANCZOS)
            
        # Сохраняем с оптимизацией качества
        output = io.BytesIO()
        # Определяем формат для сохранения. Если был PNG с прозрачностью, сохраняем как PNG
        if img.mode == 'RGBA' and 'transparency' in img.info:
            img.save(output, format='PNG', optimize=True)
        else:
            # Преобразуем в RGB, если нужно
            if img.mode != 'RGB':
                img = img.convert('RGB')
            img.save(output, format='JPEG', quality=quality, optimize=True)
            
        result = output.getvalue()
        
        # Проверяем, что результат действительно меньше оригинала
        if len(result) >= len(image_bytes):
            return image_bytes
            
        return result
    except Exception:
        # При любой ошибке возвращаем исходное изображение
        return image_bytes


def prepare_for_ocr(image_path_or_bytes: Union[str, bytes], use_preprocessing: bool = True) -> bytes:
    """
    Простая подготовка изображения для OCR.
    Поддерживает обратную совместимость с предыдущей версией.
    
    Args:
        image_path_or_bytes: Путь к файлу или байты изображения
        use_preprocessing: Включить предобработку (изменение размера)
        
    Returns:
        bytes: Подготовленные байты изображения
    """
    # Если передан путь к файлу
    if isinstance(image_path_or_bytes, str):
        with open(image_path_or_bytes, "rb") as f:
            image_bytes = f.read()
    else:
        image_bytes = image_path_or_bytes
        
    # Если предобработка отключена, возвращаем как есть
    if not use_preprocessing:
        return image_bytes
        
    # Простое изменение размера
    return resize_image(image_bytes)