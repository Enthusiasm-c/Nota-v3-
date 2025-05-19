"""
Optimized OCR pipeline for invoice processing.

This module provides an optimized implementation of the OCR pipeline with enhanced:
1. Redis caching with fallback to local memory
2. Parallel processing of cells
3. More efficient error handling and recovery
4. Better resource management
5. Detailed performance metrics

The pipeline includes:
1. Table detector
2. OCR processor
3. Validation pipeline (arithmetic + business rules)
"""
import json
import logging
import asyncio
import time
import traceback
import hashlib
from typing import Dict, List, Any

from app.detectors.table.factory import get_detector
from app.validators.pipeline import ValidationPipeline
from paddleocr import PaddleOCR
from app.ocr import call_openai_ocr_async
from app.ocr_prompt import OCR_SYSTEM_PROMPT
from app.config import settings
from app.utils.redis_cache import cache_get, cache_set
from app.ocr_helpers import (
    process_cell_with_gpt4o, 
    prepare_cell_image, build_lines_from_cells
)
from app.imgprep.prepare import prepare_for_ocr

logger = logging.getLogger(__name__)

# Constants for performance tuning
MAX_PARALLEL_CELLS = 10  # Maximum number of cells to process in parallel
GPT4O_CONFIDENCE_THRESHOLD = 0.75  # When to use GPT-4o instead of PaddleOCR
CACHE_TTL = 24 * 60 * 60  # 24 hour cache TTL
SMALL_CELL_SIZE_THRESHOLD = 15  # Minimum pixel dimensions for OCR

class OCRPipelineOptimized:
    """
    Optimized OCR pipeline for invoice processing with parallel processing,
    multi-level caching, and advanced error recovery.
    """
    
    def __init__(self, 
                table_detector_method: str = "paddle",
                paddle_ocr_lang: str = "en",
                fallback_to_vision: bool = True):
        """
        Initialize OCR pipeline with optimized configuration.
        
        Args:
            table_detector_method: Table detection method ('paddle', etc.)
            paddle_ocr_lang: Language for PaddleOCR
            fallback_to_vision: Whether to fallback to OpenAI Vision if table detection fails
        """
        self.table_detector = get_detector(method=table_detector_method)
        self.validation_pipeline = ValidationPipeline()
        self.paddle_ocr = PaddleOCR(use_angle_cls=True, lang=paddle_ocr_lang, show_log=False)
        self.low_conf_threshold = GPT4O_CONFIDENCE_THRESHOLD
        self.fallback_to_vision = fallback_to_vision
        
        # Performance metrics tracking
        self._metrics = {
            "gpt4o_percent": 0,
            "gpt4o_count": 0,
            "total_cells": 0,
            "table_detection_ms": 0,
            "cell_processing_ms": 0,
            "line_building_ms": 0,
            "validation_ms": 0,
            "cache_hits": 0,
            "total_processing_ms": 0
        }
    
    async def process_image(self, 
                           image_bytes: bytes, 
                           lang: List[str], 
                           max_retries: int = 2,
                           use_cache: bool = True) -> Dict[str, Any]:
        """
        Process image, extract table and recognize text with optimized workflow.
        
        Args:
            image_bytes: Raw image bytes
            lang: List of languages for OCR
            max_retries: Maximum number of retries on errors
            use_cache: Whether to use cache for this request
            
        Returns:
            Data structure with OCR results
        """
        start_time = time.time()
        timing = {}
        image_hash = None
        
        # Check cache for this image
        if use_cache:
            image_hash = hashlib.md5(image_bytes).hexdigest()
            cache_key = f"ocr_pipeline:{image_hash}"
            cached_result = cache_get(cache_key)
            
            if cached_result:
                logger.info(f"Cache hit for image {image_hash[:8]}")
                self._metrics["cache_hits"] += 1
                return cached_result
        
        # Optimize image for OCR if needed
        try:
            optimized_bytes = prepare_for_ocr(image_bytes)
            logger.debug(f"Image optimized for OCR: {len(image_bytes)} -> {len(optimized_bytes)} bytes")
            image_bytes = optimized_bytes
        except Exception as e:
            logger.warning(f"Image optimization error (non-critical): {e}")
        
        try:
            # Try using table detector
            table_detection_start = time.time()
            try:
                table_detector = get_detector("paddle")
                cells = table_detector.extract_cells(image_bytes)
                timing['table_detection'] = round((time.time() - table_detection_start) * 1000)
                self._metrics["table_detection_ms"] = timing['table_detection']
                
                # Process cells
                processing_start = time.time()
                lines = await self._process_cells(cells, lang)
                timing['cell_processing'] = round((time.time() - processing_start) * 1000)
                self._metrics["cell_processing_ms"] = timing['cell_processing']
                
                # Compile result
                result = {
                    'status': 'success',
                    'lines': lines,
                    'accuracy': 0.8,  # Default accuracy estimate
                    'issues': [],
                    'timing': timing,
                    'metrics': {**self._metrics}
                }
                
            except Exception as e:
                # Table detector error - use fallback method (OpenAI Vision)
                logger.warning(f"Error using table detector: {str(e)}, switching to OpenAI Vision")
                
                # Reset timers and record error
                timing['table_detection_error'] = round((time.time() - table_detection_start) * 1000)
                timing['table_detection_error_message'] = str(e)
                
                # Only use fallback if enabled
                if self.fallback_to_vision:
                    # Use OpenAI Vision for the entire image
                    vision_start = time.time()
                    result = await self._process_with_openai_vision(image_bytes, lang)
                    timing['vision_processing'] = round((time.time() - vision_start) * 1000)
                    result['timing'] = timing
                    result['used_fallback'] = True
                else:
                    return {
                        'status': 'error',
                        'message': f"Table detection failed: {str(e)}",
                        'timing': timing,
                        'total_time': round((time.time() - start_time) * 1000)
                    }
                
            # Apply validation
            if result["status"] == "success":
                validation_start = time.time()
                validation_pipeline = ValidationPipeline()
                validated_result = validation_pipeline.validate(result)
                timing['validation'] = round((time.time() - validation_start) * 1000)
                self._metrics["validation_ms"] = timing['validation']
                validated_result['timing'] = timing
                validated_result['total_time'] = round((time.time() - start_time) * 1000)
                
                # Cache the successful result
                if use_cache and image_hash:
                    try:
                        cache_key = f"ocr_pipeline:{image_hash}"
                        cache_set(cache_key, validated_result, ex=CACHE_TTL)
                        logger.debug(f"Cached OCR result for {image_hash[:8]}")
                    except Exception as cache_e:
                        logger.warning(f"Error caching result: {cache_e}")
                
                self._metrics["total_processing_ms"] = round((time.time() - start_time) * 1000)
                return validated_result
            else:
                result['total_time'] = round((time.time() - start_time) * 1000)
                self._metrics["total_processing_ms"] = result['total_time']
                return result
                
        except Exception as e:
            # Fallback - general error
            logger.error(f"Critical error in OCR pipeline: {str(e)}", exc_info=True)
            return {
                'status': 'error',
                'message': f"Processing error: {str(e)}",
                'timing': timing,
                'total_time': round((time.time() - start_time) * 1000)
            }
    
    async def _process_with_openai_vision(self, image_bytes: bytes, lang: List[str]) -> Dict[str, Any]:
        """
        Fallback method for processing via OpenAI Vision API with improved error handling.
        Used when PaddleOCR/PPStructure cannot process the image.
        
        Args:
            image_bytes: Raw image bytes
            lang: List of languages for OCR
            
        Returns:
            Data structure with OCR results
        """
        try:
            # Use OpenAI Vision for table recognition with automatic retries
            for attempt in range(2):  # Try up to 2 times
                try:
                    vision_result = await call_openai_ocr_async(
                        image_bytes=image_bytes, 
                        system_prompt=OCR_SYSTEM_PROMPT,
                        api_key=settings.OPENAI_API_KEY
                    )
                    break
                except Exception as e:
                    if attempt == 1:  # Last attempt
                        raise
                    logger.warning(f"OCR API attempt {attempt+1} failed: {e}. Retrying...")
                    await asyncio.sleep(1)  # Wait before retry
            
            # Convert result to line format - handle different result formats
            if isinstance(vision_result, str):
                try:
                    parsed = json.loads(vision_result)
                    if isinstance(parsed, dict):
                        if 'lines' in parsed:
                            return {
                                'status': 'success',
                                'lines': parsed.get('lines', []),
                                'accuracy': 0.9,  # Accuracy estimate for OpenAI Vision
                                'issues': []
                            }
                        elif 'positions' in parsed:
                            # Handle case where API returns positions instead of lines
                            lines = []
                            for pos in parsed.get('positions', []):
                                line = {
                                    'name': pos.get('name', ''),
                                    'qty': pos.get('qty', 0),
                                    'unit': pos.get('unit', 'pcs'),
                                    'price': pos.get('price', 0),
                                    'amount': pos.get('total_price', 0)
                                }
                                lines.append(line)
                            return {
                                'status': 'success',
                                'lines': lines,
                                'accuracy': 0.9,
                                'issues': []
                            }
                except json.JSONDecodeError:
                    # If result is not JSON, try to process text
                    logger.warning("OpenAI didn't return JSON, trying to process text")
            
            # Return error if parsing failed
            return {
                'status': 'error',
                'message': "Failed to parse OpenAI Vision result",
                'raw_result': vision_result[:200] + '...' if len(str(vision_result)) > 200 else vision_result
            }
            
        except Exception as e:
            logger.error(f"Error in OpenAI Vision fallback method: {str(e)}", exc_info=True)
            return {
                'status': 'error',
                'message': f"Error in fallback method: {str(e)}"
            }
    
    async def _ocr_cell(self, cell: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a single cell with OCR and optionally GPT-4o if confidence is low.
        Includes optimizations for handling different cell types and image quality.
        
        Args:
            cell: Cell data including image and position
            
        Returns:
            Cell with recognized text and confidence score
        """
        try:
            # Prepare cell image
            np_img = prepare_cell_image(cell['image'])
            if np_img is None:
                return {**cell, 'text': '', 'confidence': 0.0, 'used_gpt4o': False, 'error': 'too_small'}
            
            # Detect image quality and complexity
            img_height, img_width = np_img.shape[:2]
            is_small_cell = img_width < SMALL_CELL_SIZE_THRESHOLD or img_height < SMALL_CELL_SIZE_THRESHOLD
            
            text, conf = '', 0.0
            used_gpt = False
            
            # Skip PaddleOCR for very small cells
            if not is_small_cell:
                try:
                    # Run PaddleOCR on the cell
                    result = self.paddle_ocr.ocr(np_img, cls=True)
                    if result and result[0]:
                        text, conf = result[0][0][1][0], result[0][0][1][1]
                except Exception as e:
                    logger.warning(f"PaddleOCR error: {e}")
                    # If PaddleOCR fails, we'll fall back to GPT-4o
            
            # Use GPT-4o if confidence is low, PaddleOCR returned empty, or cell is very small
            if conf < self.low_conf_threshold or not text or is_small_cell:
                try:
                    # Use process_cell_with_gpt4o function from ocr_helpers
                    gpt_text, gpt_conf = await process_cell_with_gpt4o(cell['image'])
                    if gpt_text:
                        text = gpt_text
                        conf = gpt_conf
                        used_gpt = True
                except Exception as e:
                    logger.warning(f"Error processing cell with GPT-4o: {e}")
            
            # Process any digits-only special case
            if text and text.strip().isdigit():
                # For digit-only cells, ensure they're not treated as text
                text = text.strip()
            
            return {**cell, 'text': text, 'confidence': conf, 'used_gpt4o': used_gpt}
                
        except Exception as e:
            logger.error(f"Critical error processing cell: {e}")
            return {**cell, 'text': '', 'confidence': 0.0, 'used_gpt4o': False, 'error': str(e)}
    
    async def _process_cells(self, cells: List[Dict[str, Any]], lang: List[str]) -> List[Dict[str, Any]]:
        """
        Process cells in parallel chunks and build data structure for invoice.
        Uses chunking for better resource utilization and system stability.
        
        Args:
            cells: List of cells with coordinates and images
            lang: List of languages for OCR
            
        Returns:
            List of invoice lines
        """
        gpt4o_count = 0
        total_cells = len(cells)
        self._metrics["total_cells"] = total_cells
        
        # Measure OCR time for each cell
        ocr_cells_start = time.time()
        ocr_results = []
        
        # Check if there are cells to process
        if not cells:
            logger.warning("No cells detected for OCR")
            self._metrics["gpt4o_percent"] = 0
            self._metrics["gpt4o_count"] = 0
            return []
        
        try:
            # Process cells in parallel chunks for better resource management
            chunk_size = min(MAX_PARALLEL_CELLS, max(1, len(cells) // 4))
            for i in range(0, len(cells), chunk_size):
                chunk = cells[i:i+chunk_size]
                
                # Process chunk in parallel
                chunk_results = await asyncio.gather(*(self._ocr_cell(cell) for cell in chunk), 
                                                  return_exceptions=False)
                
                # Count GPT-4o usage in this chunk
                for result in chunk_results:
                    if result.get('used_gpt4o', False):
                        gpt4o_count += 1
                
                # Add results to overall list
                ocr_results.extend(chunk_results)
                
                # Log progress for long-running processes
                if len(cells) > 20:
                    progress = min(100, int((i + len(chunk)) / len(cells) * 100))
                    logger.debug(f"OCR progress: {progress}% ({i + len(chunk)}/{len(cells)} cells)")
            
        except Exception as e:
            logger.error(f"Error in parallel OCR processing: {e}")
            stack_trace = traceback.format_exc()
            logger.debug(f"Stack trace: {stack_trace}")
            
            # Try to process remaining cells sequentially if parallel processing fails
            logger.warning("Falling back to sequential cell processing")
            for cell in cells:
                if cell not in [c.get('original_cell') for c in ocr_results]:
                    try:
                        result = await self._ocr_cell(cell)
                        ocr_results.append(result)
                        if result.get('used_gpt4o', False):
                            gpt4o_count += 1
                    except Exception as cell_e:
                        logger.error(f"Failed to process cell: {cell_e}")
                        ocr_results.append({**cell, 'text': '', 'confidence': 0.0, 'error': str(cell_e)})
            
        ocr_cells_time = round((time.time() - ocr_cells_start) * 1000)
        gpt4o_percent = (gpt4o_count / total_cells) * 100 if total_cells else 0
        
        logger.info(f"[TIMING] OCR for {total_cells} cells: {ocr_cells_time}ms")
        logger.info(f"Cells sent to GPT-4o: {gpt4o_percent:.1f}% ({gpt4o_count}/{total_cells})")

        # Handle case where all cells are empty
        all_empty = all(not cell.get('text') for cell in ocr_results)
        if all_empty and len(ocr_results) > 2:
            logger.warning("All cells have no text. Adding pre-recognized text from cell structure.")
            # Try to get text from HTML structure if available
            for i, cell in enumerate(ocr_results):
                if 'text' in cell and not cell['text'] and cell.get('structure') and 'text' in cell['structure']:
                    ocr_results[i]['text'] = cell['structure'].get('text', '')
                    logger.info(f"Added text from HTML for cell {i}: {ocr_results[i]['text']}")
                    
        # Measure time for building lines
        lines_build_start = time.time()
        
        # Build lines from cells
        lines = build_lines_from_cells(ocr_results)
        
        lines_build_time = round((time.time() - lines_build_start) * 1000)
        self._metrics["line_building_ms"] = lines_build_time
        logger.info(f"[TIMING] Line building: {lines_build_time}ms. Lines formed: {len(lines)}")
        
        # Save statistics for response
        self._metrics["gpt4o_percent"] = gpt4o_percent
        self._metrics["gpt4o_count"] = gpt4o_count
        return lines

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get current performance metrics from the pipeline.
        
        Returns:
            Dictionary with performance metrics
        """
        return {**self._metrics}