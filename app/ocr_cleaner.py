"""
Модуль для предварительной обработки изображений перед OCR.
"""

import io
from typing import Union

from PIL import Image
from PIL.Image import Resampling


def preprocess_for_ocr(image_bytes: bytes) -> bytes:
    """
    Предварительная обработка изображения для улучшения качества OCR.

    Args:
        image_bytes: Байты изображения

    Returns:
        Обработанные байты изображения
    """
    # Оптимизируем размер изображения
    image_bytes = resize_image(image_bytes)
    return image_bytes


def resize_image(image_bytes: bytes, max_size: int = 1600, quality: int = 90) -> bytes:
    """
    Изменяет размер изображения, если оно превышает максимальный размер.

    Args:
        image_bytes: Байты изображения
        max_size: Максимальный размер в пикселях
        quality: Качество JPEG (0-100)

    Returns:
        Оптимизированные байты изображения
    """
    try:
        img: Image.Image = Image.open(io.BytesIO(image_bytes))

        # Если изображение уже достаточно маленькое, возвращаем как есть
        if max(img.size) <= max_size and len(image_bytes) <= 1.5 * 1024 * 1024:
            return image_bytes

        # Изменяем размер с сохранением пропорций
        if max(img.size) > max_size:
            ratio = max_size / max(img.size)
            new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
            img = img.resize(new_size, Resampling.LANCZOS)

        # Сохраняем с оптимизацией качества
        output = io.BytesIO()

        # Определяем формат вывода
        if img.mode == "RGBA" and "transparency" in img.info:
            img.save(output, format="PNG", optimize=True)
        else:
            # Конвертируем в RGB при необходимости
            if img.mode != "RGB":
                img = img.convert("RGB")
            img.save(output, format="JPEG", quality=quality, optimize=True)

        result = output.getvalue()

        # Проверяем, действительно ли оптимизация уменьшила размер
        if len(result) >= len(image_bytes):
            return image_bytes

        return result
    except Exception:
        # При любой ошибке возвращаем оригинальное изображение
        return image_bytes


def clean_ocr_response(text: str) -> str:
    """
    Очищает текст, полученный от OCR.

    Args:
        text: Исходный текст

    Returns:
        Очищенный текст
    """
    if not text:
        return ""

    # Удаляем лишние пробелы
    text = " ".join(text.split())

    # Удаляем специальные символы в начале и конце
    text = text.strip(".,;:!?-_")

    return text 
 