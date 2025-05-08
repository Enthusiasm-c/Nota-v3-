import logging
import asyncio
from typing import Tuple, Optional
from pathlib import Path
from app.imgprep import prepare_for_ocr, prepare_without_preprocessing
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
    use_preprocessing: bool,
    req_id: str
) -> Tuple[bytes, Optional[ParsedData]]:
    """
    Асинхронный пайплайн для обработки фотографии накладной.
    Разделяет процесс на шаги для предотвращения блокировки event loop.
    """
    processed_bytes = None
    parsed_data = None
    # Шаг 1: Предобработка изображения
    try:
        with PerformanceTimer(req_id, "image_preprocessing"):
            if use_preprocessing:
                logger.info(f"[{req_id}] Starting image preprocessing")
                processed_bytes = await process_image_step(
                    prepare_for_ocr, img_path, use_preprocessing=True
                )
            else:
                logger.info(f"[{req_id}] Preprocessing disabled, using original image")
                processed_bytes = await process_image_step(
                    prepare_without_preprocessing, img_path
                )
    except asyncio.TimeoutError:
        logger.warning(f"[{req_id}] Image preprocessing timeout, using original image")
        processed_bytes = img_bytes
    except Exception as e:
        logger.error(f"[{req_id}] Error during image preprocessing: {e}")
        processed_bytes = img_bytes
    # Шаг 2: OCR через OpenAI
    try:
        with PerformanceTimer(req_id, "ocr_processing"):
            logger.info(f"[{req_id}] Starting OCR processing")
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