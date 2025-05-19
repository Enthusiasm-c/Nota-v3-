import re
import json
import logging
from typing import Optional, Dict, Any
import cv2
import numpy as np


def resize_image(image: np.ndarray, max_size: int = 2048) -> np.ndarray:
    """
    Изменяет размер изображения, сохраняя пропорции, если оно превышает максимальный размер.
    
    Args:
        image: Входное изображение
        max_size: Максимальный размер стороны изображения в пикселях
        
    Returns:
        Изображение с корректным размером
    """
    height, width = image.shape[:2]
    
    # Если изображение меньше максимального размера, возвращаем как есть
    if max(height, width) <= max_size:
        return image
        
    # Вычисляем новые размеры, сохраняя пропорции
    if height > width:
        new_height = max_size
        new_width = int(width * (max_size / height))
    else:
        new_width = max_size
        new_height = int(height * (max_size / width))
        
    return cv2.resize(image, (new_width, new_height), interpolation=cv2.INTER_AREA)


def preprocess_for_ocr(image_bytes: bytes, settings: Optional[Dict[str, Any]] = None) -> bytes:
    """
    Базовая предобработка изображения для OCR.
    Контролирует только размер и разрешение изображения.
    
    Args:
        image_bytes: Байты исходного изображения
        settings: Дополнительные настройки обработки
        
    Returns:
        Байты обработанного изображения
    """
    # Преобразуем байты в numpy array
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if img is None:
        logging.error("Failed to decode image")
        return image_bytes
        
    try:
        # Применяем настройки по умолчанию, если не указаны
        settings = settings or {}
        
        # Контроль размера изображения
        max_size = settings.get("max_size", 2048)
        img = resize_image(img, max_size)
            
        # Кодируем обратно в байты с контролем качества
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, settings.get("jpeg_quality", 95)]
        success, processed_bytes = cv2.imencode(".jpg", img, encode_params)
        
        if not success:
            logging.error("Failed to encode processed image")
            return image_bytes
            
        return processed_bytes.tobytes()
        
    except Exception as e:
        logging.error(f"Error during image preprocessing: {e}")
        return image_bytes


def extract_json_block(text: str) -> str:
    """
    Extracts the first JSON object from a string, ignoring code fences and commentary.
    Returns the JSON string or raises ValueError if not found.
    """
    # Remove code fences and 'json' labels
    text = text.strip()
    text = re.sub(r"^```(json)?", "", text, flags=re.IGNORECASE | re.MULTILINE)
    text = re.sub(r"```$", "", text, flags=re.MULTILINE)
    # Find the first balanced {...} block
    brace_stack = []
    start = None
    for i, c in enumerate(text):
        if c == "{":
            if not brace_stack:
                start = i
            brace_stack.append(c)
        elif c == "}":
            if brace_stack:
                brace_stack.pop()
                if not brace_stack and start is not None:
                    return text[start : i + 1]
    raise ValueError("No JSON object found in text")


def _sanitize_json(obj):
    # Если уже ParsedData-like
    if isinstance(obj, dict):
        # Если есть positions, но нет supplier/date — добавить их как None
        if "positions" in obj:
            if "supplier" not in obj:
                obj["supplier"] = None
            if "date" not in obj:
                obj["date"] = None
            return obj
        # Если это dict-позиция
        return {"supplier": None, "date": None, "positions": [obj]}
    # Если это список позиций
    if isinstance(obj, list):
        return {"supplier": None, "date": None, "positions": obj}
    # fallback
    return {"supplier": None, "date": None, "positions": []}


def clean_ocr_response(text: str):
    """
    Cleans OpenAI OCR response and returns parsed dict.
    """
    logging.debug(f"Raw OCR answer: {text!r}")
    json_str = extract_json_block(text)
    obj = json.loads(json_str)
    return _sanitize_json(obj)
