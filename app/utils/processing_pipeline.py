import logging
import asyncio
from typing import Tuple, Optional
from pathlib import Path
from app.ocr import call_openai_ocr
from app.models import ParsedData
from app.utils.enhanced_logger import PerformanceTimer

logger = logging.getLogger(__name__)

async def process_image_step(step_func, *args, **kwargs):
    """
    Выполняет один шаг обработки в отдельном потоке с таймаутом.
    """
    return await asyncio.wait_for(
        asyncio.to_thread(step_func, *args, **kwargs),
        timeout=90.0
    )

async def process_invoice_pipeline(
    img_bytes: bytes,
    img_path: Path,
    req_id: str
) -> Tuple[bytes, Optional[ParsedData]]:
    """
    Асинхронный пайплайн для обработки фотографии накладной.
    Теперь не содержит этапа предобработки, работает только с оригинальным изображением.
    """
    processed_bytes = None
    parsed_data = None
    # Шаг 1: Используем оригинальное изображение
    try:
        with PerformanceTimer(req_id, "image_loading"):
            logger.info(f"[{req_id}] Используется оригинальное изображение без предобработки")
            processed_bytes = img_bytes
    except Exception as e:
        logger.error(f"[{req_id}] Ошибка при загрузке изображения: {e}")
        processed_bytes = img_bytes
    # Шаг 2: OCR через OpenAI
    try:
        with PerformanceTimer(req_id, "ocr_processing"):
            logger.info(f"[{req_id}] Запуск OCR")
            parsed_data = await process_image_step(
                call_openai_ocr, processed_bytes, _req_id=req_id
            )
    except asyncio.TimeoutError:
        logger.error(f"[{req_id}] OCR processing timeout")
        raise RuntimeError("OCR processing timed out. Please try with a clearer image.")
    except Exception as e:
        logger.error(f"[{req_id}] Error during OCR processing: {e}")
        raise
    return processed_bytes, parsed_data