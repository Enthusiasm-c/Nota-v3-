"""
OCR utility functions for invoice processing.
"""
import base64
import logging
import time
from typing import Dict, Any, Optional

from app.models import ParsedData
from app.postprocessing import postprocess_parsed_data
from app.ocr_prompt import OCR_SYSTEM_PROMPT
from app.config import settings
from app.utils.ocr_cache import get_from_cache, save_to_cache
from app.imgprep.prepare import prepare_for_ocr


# Schema for the function call in OpenAI API
INVOICE_FUNCTION_SCHEMA = {
    "name": "get_parsed_invoice",
    "description": "Parse structured data from invoice image",
    "parameters": {
        "type": "object",
        "properties": {
            "supplier": {
                "type": "string",
                "description": "Supplier name from the invoice"
            },
            "date": {
                "type": "string",
                "description": "Invoice date in YYYY-MM-DD format"
            },
            "positions": {
                "type": "array",
                "description": "List of invoice positions",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Product name"
                        },
                        "qty": {
                            "type": "number",
                            "description": "Quantity"
                        },
                        "unit": {
                            "type": "string",
                            "description": "Unit of measurement"
                        },
                        "price": {
                            "type": "number",
                            "description": "Price per unit"
                        },
                        "total_price": {
                            "type": "number",
                            "description": "Total price for this position"
                        }
                    },
                    "required": ["name", "qty"]
                }
            },
            "total_price": {
                "type": "number",
                "description": "Total invoice amount"
            }
        },
        "required": ["positions"]
    }
}


def get_ocr_client():
    """Get OpenAI client instance for OCR."""
    try:
        import openai
        # Use OPENAI_OCR_KEY instead of OPENAI_API_KEY
        client = openai.OpenAI(api_key=settings.OPENAI_OCR_KEY)
        return client
    except (ImportError, Exception) as e:
        logging.error(f"Failed to initialize OpenAI client: {e}")
        return None


def call_openai_ocr(image_bytes: bytes, _req_id=None, use_cache: bool = True, timeout: int = 20) -> ParsedData:
    """
    Call OpenAI Vision API to extract data from an invoice image.
    
    Args:
        image_bytes: Raw image bytes
        _req_id: Optional request ID for tracking
        use_cache: Whether to use cache
        timeout: Timeout in seconds for the API call (default 20)
        
    Returns:
        ParsedData model with extracted information
    """
    # Try to get from cache first (fastest path)
    if use_cache:
        try:
            cached_data = get_from_cache(image_bytes)
            if cached_data:
                logging.info("Using cached OCR result")
                return cached_data
        except Exception as e:
            logging.warning(f"Cache read error: {e}")
    
    # Start timer for overall processing
    start_time = time.time()
    
    # Prepare image - optimize for OCR
    try:
        optimized_image = prepare_for_ocr(image_bytes)
        logging.debug("Image optimized for OCR")
    except Exception as e:
        logging.warning(f"Image optimization error: {e}, using original image")
        optimized_image = image_bytes
    
    # Get OpenAI client with validation
    client = get_ocr_client()
    if not client:
        raise RuntimeError("OpenAI client not available")
    
    # Ensure client has chat attribute
    if not hasattr(client, 'chat'):
        raise RuntimeError("Invalid OpenAI client (no chat attribute)")
    
    # Convert image to base64 - required for API
    base64_image = base64.b64encode(optimized_image).decode("utf-8")
    
    # Log start of API call
    api_start_time = time.time()
    logging.info(f"Starting OCR API call with timeout {timeout}s")
    
    # Call OpenAI Vision with timeout
    import concurrent.futures
    from concurrent.futures import ThreadPoolExecutor
    
    try:
        # Create thread pool for timeout management
        with ThreadPoolExecutor(max_workers=1) as executor:
            # Submit API call to thread pool
            future = executor.submit(
                client.chat.completions.create,
                model="gpt-4o",
                max_tokens=2048,
                temperature=0.0,
                tools=[{"type": "function", "function": INVOICE_FUNCTION_SCHEMA}],
                tool_choice={"type": "function", "function": {"name": "get_parsed_invoice"}},
                messages=[
                    {"role": "system", "content": OCR_SYSTEM_PROMPT},
                    {"role": "user", "content": [
                        {"type": "image_url", "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}",
                            "detail": "high"
                        }}
                    ]}
                ]
            )
            
            # Wait for result with timeout
            try:
                response = future.result(timeout=timeout)
                # Measure time
                api_duration = time.time() - api_start_time
                logging.info(f"OCR API call completed successfully in {api_duration:.2f}s")
            except concurrent.futures.TimeoutError:
                # Cancel the future if possible
                future.cancel()
                logging.error(f"OCR API call timed out after {timeout}s")
                raise TimeoutError(f"OCR API call timed out after {timeout}s")
        
        # Extract function call result with validation at each step
        if not response.choices:
            raise ValueError("Empty response from OpenAI")
        
        message = response.choices[0].message
        if not message.tool_calls or len(message.tool_calls) == 0:
            raise ValueError("No tool call in response")
        
        # Get the first tool call
        tool_call = message.tool_calls[0]
        if tool_call.function.name != "get_parsed_invoice":
            raise ValueError(f"Unexpected function name: {tool_call.function.name}")
        
        # Parse JSON arguments
        import json
        result_data = json.loads(tool_call.function.arguments)
        
        # Convert to Pydantic model
        parsed_data = ParsedData.model_validate(result_data)
        
        # Post-process data
        processed_data = postprocess_parsed_data(parsed_data)
        
        # Cache the result for future use
        if use_cache:
            try:
                save_to_cache(image_bytes, processed_data)
                logging.debug("OCR result saved to cache")
            except Exception as e:
                logging.warning(f"Cache save error: {e}")
        
        # Log total processing time
        total_duration = time.time() - start_time
        logging.info(f"Total OCR processing completed in {total_duration:.2f}s")
        
        return processed_data
    
    except TimeoutError as e:
        logging.error(f"OCR timeout error: {e}")
        raise RuntimeError(f"OCR operation timed out: {e}")
    except Exception as e:
        logging.error(f"OCR API error: {e}")
        raise RuntimeError(f"Failed to extract data from image: {e}")


async def call_openai_ocr_async(image_bytes: bytes, system_prompt: str = None, api_key: Optional[str] = None) -> str:
    """
    Async version of the OCR function that returns raw JSON string.
    Used by the OCR pipeline as a fallback.
    
    Args:
        image_bytes: Raw image bytes
        system_prompt: Optional custom system prompt
        api_key: Optional API key to use
        
    Returns:
        JSON string with extracted data
    """
    # This is a simplified async version for the pipeline
    # In a real implementation, this would use proper async client
    
    # Get OpenAI client
    client = get_ocr_client()
    if not client:
        raise RuntimeError("OpenAI client not available")
    
    # Convert image to base64
    base64_image = base64.b64encode(image_bytes).decode("utf-8")
    
    # Use provided prompt or default
    prompt = system_prompt or OCR_SYSTEM_PROMPT
    
    # Call OpenAI Vision
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            max_tokens=2048,
            temperature=0.0,
            tools=[
                {
                    "type": "function",
                    "function": INVOICE_FUNCTION_SCHEMA
                }
            ],
            tool_choice={
                "type": "function",
                "function": {"name": "get_parsed_invoice"}
            },
            messages=[
                {
                    "role": "system",
                    "content": prompt
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}",
                                "detail": "high"
                            }
                        }
                    ]
                }
            ]
        )
        
        # Extract function call result
        if not response.choices:
            raise ValueError("Empty response from OpenAI")
        
        message = response.choices[0].message
        if not message.tool_calls or len(message.tool_calls) == 0:
            raise ValueError("No tool call in response")
        
        # Get the first tool call
        tool_call = message.tool_calls[0]
        if tool_call.function.name != "get_parsed_invoice":
            raise ValueError(f"Unexpected function name: {tool_call.function.name}")
        
        # Return raw JSON string
        return tool_call.function.arguments
    
    except Exception as e:
        logging.error(f"Async OCR API error: {e}")
        raise RuntimeError(f"Failed to extract data from image: {e}")