"""
OCR utility functions for invoice processing.
"""

import logging
from typing import List, Optional

from pydantic import BaseModel

from app.config import settings
from app.models import ParsedData

# INVOICE_FUNCTION_SCHEMA is defined in app.utils.async_ocr.py
# and should be the single source of truth.


class Position(BaseModel):
    """
    Позиция в накладной.
    """

    name: str
    quantity: float
    unit: Optional[str] = None
    price: Optional[float] = None
    total: Optional[float] = None


class ParsedData(BaseModel):
    """
    Распознанные данные накладной.
    """

    positions: List[Position]
    supplier: Optional[str] = None
    date: Optional[str] = None
    number: Optional[str] = None
    total: Optional[float] = None


# Схема функции для обработки накладных
INVOICE_FUNCTION_SCHEMA = {
    "name": "extract_invoice_data",
    "description": "Extract structured data from invoice image",
    "parameters": {
        "type": "object",
        "properties": {
            "positions": {
                "type": "array",
                "description": "List of items in the invoice",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Item name"},
                        "quantity": {"type": "number", "description": "Item quantity"},
                        "unit": {"type": "string", "description": "Unit of measurement"},
                        "price": {"type": "number", "description": "Price per unit"},
                        "total": {"type": "number", "description": "Total price for this item"},
                    },
                    "required": ["name", "quantity"],
                },
            },
            "supplier": {"type": "string", "description": "Supplier name"},
            "date": {"type": "string", "description": "Invoice date"},
            "number": {"type": "string", "description": "Invoice number"},
            "total": {"type": "number", "description": "Total invoice amount"},
        },
        "required": ["positions"],
    },
}


def get_ocr_client():
    """Get OpenAI client instance for OCR."""
    try:
        import openai

        # Use OPENAI_OCR_KEY, fallback to OPENAI_API_KEY if not available
        api_key = settings.OPENAI_OCR_KEY
        if not api_key:
            logging.warning("OPENAI_OCR_KEY not set, trying to use OPENAI_API_KEY")
            api_key = getattr(settings, "OPENAI_API_KEY", "")

        if not api_key:
            logging.error("No API key available for OCR client")
            return None

        client = openai.OpenAI(api_key=api_key)
        return client
    except (ImportError, Exception) as e:
        logging.error(f"Failed to initialize OpenAI client: {e}")
        return None


def call_openai_ocr(
    image_bytes: bytes, _req_id=None, use_cache: bool = True, timeout: int = 60
) -> ParsedData:
    """
    Call OpenAI Vision API to extract data from an invoice image.

    Args:
        image_bytes: Raw image bytes
        _req_id: Optional request ID for tracking
        use_cache: Whether to use cache
        timeout: Timeout in seconds for the API call (default 60)

    Returns:
        ParsedData model with extracted information
    """
    import asyncio

    from app.utils.async_ocr import async_ocr as new_async_ocr_utility  # Renamed to avoid confusion

    # This synchronous function now calls the new async_ocr_utility from app.utils.async_ocr
    # All logic like caching, image prep, OpenAI client handling, post-processing
    # is handled by new_async_ocr_utility.
    # The 'use_cache' and 'timeout' parameters are passed to new_async_ocr_utility.
    # The _req_id parameter is not directly used by new_async_ocr_utility, which has its own request ID generation.

    logging.info(
        f"Synchronous call_openai_ocr (in app.ocr) is wrapping app.utils.async_ocr.async_ocr. Timeout: {timeout}, Use Cache: {use_cache}"
    )

    try:
        # Get or create a new event loop for this synchronous context
        try:
            loop = asyncio.get_event_loop_policy().get_event_loop()
            if loop.is_running():
                # If an event loop is already running (e.g., in a Jupyter notebook or another async context),
                # create a new loop to avoid RuntimeError: Cannot run new tasks from a different thread.
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            else:
                # If no loop is running, the default get_event_loop() is fine.
                # Or, to be absolutely safe, always use a new loop for sync calls:
                # loop = asyncio.new_event_loop()
                # asyncio.set_event_loop(loop)
                pass  # Current loop is fine if not running
        except RuntimeError:  # pragma: no cover
            # This might happen if no current event loop is set and policy doesn't create one.
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        parsed_data_result = loop.run_until_complete(
            new_async_ocr_utility(
                image_bytes=image_bytes,
                req_id=_req_id,  # Pass along if new_async_ocr_utility can use it
                use_cache=use_cache,
                timeout=timeout,
            )
        )
        # loop.close() # Closing the loop can cause issues if it's the main loop or shared.
        # Let the caller manage the loop lifecycle if it created it.
        # If we created a new_event_loop(), it's safer to close it.
        # However, run_until_complete usually handles this.
        return parsed_data_result

    except asyncio.TimeoutError:
        logging.error(f"OCR operation timed out in sync wrapper call_openai_ocr after {timeout}s.")
        raise RuntimeError(f"OCR operation timed out after {timeout}s (from sync wrapper).")
    except Exception as e:
        logging.error(
            f"Error in sync wrapper call_openai_ocr for new_async_ocr_utility: {e}", exc_info=True
        )
        raise RuntimeError(
            f"Failed to extract data from image (from sync wrapper call_openai_ocr): {e}"
        )


# Removed call_openai_ocr_async as app.utils.async_ocr.async_ocr is the preferred async version.
# async def call_openai_ocr_async(image_bytes: bytes, system_prompt: str = None, api_key: Optional[str] = None) -> str:
#     """
#     DEPRECATED: Use app.utils.async_ocr.async_ocr instead.
#     Async version of the OCR function that returns raw JSON string.
#     Used by the OCR pipeline as a fallback.
#     """
#     # ... (original implementation removed) ...
#     pass
