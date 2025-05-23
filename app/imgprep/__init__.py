"""
Модуль для оптимизации и подготовки изображений к OCR.
"""

from .prepare import prepare_for_ocr, resize_image

__all__ = ["prepare_for_ocr", "resize_image"]
