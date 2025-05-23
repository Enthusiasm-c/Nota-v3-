"""
Image preprocessing utilities for OCR.
"""

import io
from typing import Union

from PIL import Image
from PIL.Image import Resampling


def resize_image(image_bytes: bytes, max_size: int = 1600, quality: int = 90) -> bytes:
    """
    Resize an image if it exceeds the maximum size.

    Args:
        image_bytes: Raw image bytes
        max_size: Maximum dimension size in pixels
        quality: JPEG quality (0-100)

    Returns:
        Optimized image bytes
    """
    try:
        img: Image.Image = Image.open(io.BytesIO(image_bytes))

        # If image is already small enough, return as is
        if max(img.size) <= max_size and len(image_bytes) <= 1.5 * 1024 * 1024:
            return image_bytes

        # Resize while maintaining aspect ratio
        if max(img.size) > max_size:
            ratio = max_size / max(img.size)
            new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
            img = img.resize(new_size, Resampling.LANCZOS)

        # Save with quality optimization
        output = io.BytesIO()

        # Determine output format
        if img.mode == "RGBA" and "transparency" in img.info:
            img.save(output, format="PNG", optimize=True)
        else:
            # Convert to RGB if needed
            if img.mode != "RGB":
                img = img.convert("RGB")
            img.save(output, format="JPEG", quality=quality, optimize=True)

        result = output.getvalue()

        # Check if optimization actually reduced size
        if len(result) >= len(image_bytes):
            return image_bytes

        return result
    except Exception:
        # If any error occurs, return original image
        return image_bytes


def prepare_for_ocr(
    image_path_or_bytes: Union[str, bytes], use_preprocessing: bool = True
) -> bytes:
    """
    Prepare an image for OCR.

    Args:
        image_path_or_bytes: Image path or bytes
        use_preprocessing: Whether to use preprocessing

    Returns:
        Processed image bytes
    """
    # Load image
    if isinstance(image_path_or_bytes, str):
        with open(image_path_or_bytes, "rb") as f:
            image_bytes = f.read()
    else:
        image_bytes = image_path_or_bytes

    # Skip preprocessing if disabled
    if not use_preprocessing:
        return image_bytes

    # Apply preprocessing
    return resize_image(image_bytes)
