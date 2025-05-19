"""
Complete OCR pipeline for invoice processing.

Includes:
1. Table detector
2. OCR processor
3. Validation pipeline (arithmetic + business rules)
"""
import json
import logging
import asyncio
import time
from typing import Dict, List, Any
import openai

from app.detectors.table.factory import get_detector
from app.validators.pipeline import ValidationPipeline
from paddleocr import PaddleOCR
from app.ocr import call_openai_ocr_async
from app.ocr_prompt import OCR_SYSTEM_PROMPT
from app.config import settings
from app.ocr_helpers import (
    process_cell_with_gpt4o, 
    prepare_cell_image, build_lines_from_cells
)

logger = logging.getLogger(__name__)


class OCRPipeline:
    """
    Complete OCR pipeline for invoice processing.
    """
    
    def __init__(self, 
                 table_detector_method: str = "paddle",
                 paddle_ocr_lang: str = "en"):
        """
        Initialize OCR pipeline.
        
        Args:
            table_detector_method: Table detection method ('paddle', etc.)
            paddle_ocr_lang: Language for PaddleOCR
        """
        self.table_detector = get_detector(method=table_detector_method)
        self.validation_pipeline = ValidationPipeline()
        self.paddle_ocr = PaddleOCR(use_angle_cls=True, lang=paddle_ocr_lang, show_log=False)
        self.low_conf_threshold = 0.7  # Confidence threshold for GPT-4o fallback
        
        # Initialize statistics variables
        self._last_gpt4o_percent = 0
        self._last_gpt4o_count = 0
        self._last_total_cells = 0
    
    async def process_image(self, image_bytes: bytes, lang: List[str], max_retries: int = 2) -> Dict[str, Any]:
        """
        Process image, extract table and recognize text.
        
        Args:
            image_bytes: Raw image bytes
            lang: List of languages for OCR
            max_retries: Maximum number of retries on errors
            
        Returns:
            Data structure with OCR results
        """
        start_time = time.time()
        timing = {}
        
        try:
            # Try using table detector
            table_detection_start = time.time()
            try:
                table_detector = get_detector("paddle")
                cells = table_detector.extract_cells(image_bytes)
                timing['table_detection'] = time.time() - table_detection_start
                
                # Process cells
                processing_start = time.time()
                lines = await self._process_cells(cells, lang)
                timing['cell_processing'] = time.time() - processing_start
                
                # Compile result
                result = {
                    'status': 'success',
                    'lines': lines,
                    'accuracy': 0.8,  # Default accuracy estimate
                    'issues': [],
                    'timing': timing
                }
                
            except Exception as e:
                # Table detector error - use fallback method (OpenAI Vision)
                logger.warning(f"Error using table detector: {str(e)}, switching to OpenAI Vision")
                
                # Reset timers and record error
                timing['table_detection_error'] = time.time() - table_detection_start
                timing['table_detection_error_message'] = str(e)
                
                # Use OpenAI Vision for the entire image
                vision_start = time.time()
                result = await self._process_with_openai_vision(image_bytes, lang)
                timing['vision_processing'] = time.time() - vision_start
                result['timing'] = timing
                result['used_fallback'] = True
                
            # Apply validation
            if result["status"] == "success":
                validation_start = time.time()
                validation_pipeline = ValidationPipeline()
                validated_result = validation_pipeline.validate(result)
                timing['validation'] = time.time() - validation_start
                validated_result['timing'] = timing
                validated_result['total_time'] = time.time() - start_time
                return validated_result
            else:
                result['total_time'] = time.time() - start_time
                return result
                
        except Exception as e:
            # Fallback - general error
            logger.error(f"Critical error in OCR pipeline: {str(e)}", exc_info=True)
            return {
                'status': 'error',
                'message': f"Processing error: {str(e)}",
                'timing': timing,
                'total_time': time.time() - start_time
            }
            
    async def _process_with_openai_vision(self, image_bytes: bytes, lang: List[str]) -> Dict[str, Any]:
        """
        Fallback method for processing via OpenAI Vision API.
        Used when PaddleOCR/PPStructure cannot process the image.
        
        Args:
            image_bytes: Raw image bytes
            lang: List of languages for OCR
            
        Returns:
            Data structure with OCR results
        """
        try:
            # Use OpenAI Vision for table recognition
            vision_result = await call_openai_ocr_async(
                image_bytes=image_bytes, 
                system_prompt=OCR_SYSTEM_PROMPT,
                api_key=settings.OPENAI_API_KEY
            )
            
            # Convert result to line format
            if isinstance(vision_result, str):
                try:
                    parsed = json.loads(vision_result)
                    if isinstance(parsed, dict) and 'lines' in parsed:
                        return {
                            'status': 'success',
                            'lines': parsed.get('lines', []),
                            'accuracy': 0.9,  # Accuracy estimate for OpenAI Vision
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
            
            try:
                # Run PaddleOCR on the cell
                result = self.paddle_ocr.ocr(np_img, cls=True)
                if result and result[0]:
                    text, conf = result[0][0][1][0], result[0][0][1][1]
                else:
                    text, conf = '', 0.0
            except Exception as e:
                logger.warning(f"PaddleOCR error: {e}")
                # If PaddleOCR fails, go straight to GPT4o
                text, conf = '', 0.0
            
            used_gpt = False
            # Use GPT-4o if confidence is low or PaddleOCR returned empty result
            if conf < self.low_conf_threshold or not text:
                try:
                    # Use our cell processing function instead of call_openai_ocr
                    gpt_text, gpt_conf = await process_cell_with_gpt4o(cell['image'])
                    if gpt_text:
                        text = gpt_text
                        conf = gpt_conf
                        used_gpt = True
                except Exception as e:
                    logger.warning(f"Error processing cell with GPT-4o: {e}")
            
            return {**cell, 'text': text, 'confidence': conf, 'used_gpt4o': used_gpt}
                
        except Exception as e:
            logger.error(f"Critical error processing cell: {e}")
            return {**cell, 'text': '', 'confidence': 0.0, 'used_gpt4o': False, 'error': str(e)}
    
    async def _process_cells(self, cells: List[Dict[str, Any]], lang: List[str]) -> List[Dict[str, Any]]:
        """
        Process cells and build data structure for invoice.
        
        Args:
            cells: List of cells with coordinates and images
            lang: List of languages for OCR
            
        Returns:
            List of invoice lines
        """
        gpt4o_count = 0
        total_cells = len(cells)
        
        # Measure OCR time for each cell
        ocr_cells_start = time.time()
        ocr_results = []
        
        # Check if there are cells to process
        if not cells:
            logger.warning("No cells detected for OCR")
            self._last_gpt4o_percent = 0
            self._last_gpt4o_count = 0
            self._last_total_cells = 0
            
            # If no table or cells couldn't be extracted, return empty list
            return []
            
        try:
            # Process all cells in parallel
            ocr_results = await asyncio.gather(*(self._ocr_cell(cell) for cell in cells))
            
            # Count cells processed with GPT-4o
            gpt4o_count = sum(1 for cell in ocr_results if cell.get('used_gpt4o', False))
            
        except Exception as e:
            logger.error(f"Error performing OCR for cells: {e}")
            # If failing on all cells, try to process at least partially
            for cell in cells:
                try:
                    result = await self._ocr_cell(cell)
                    ocr_results.append(result)
                    if result.get('used_gpt4o', False):
                        gpt4o_count += 1
                except Exception as cell_e:
                    logger.error(f"Failed to process cell: {cell_e}")
                    ocr_results.append({**cell, 'text': '', 'confidence': 0.0, 'error': str(cell_e)})
            
        ocr_cells_time = time.time() - ocr_cells_start
        gpt4o_percent = (gpt4o_count / total_cells) * 100 if total_cells else 0
        
        logger.info(f"[TIMING] OCR for {total_cells} cells: {ocr_cells_time:.2f} sec")
        logger.info(f"Cells sent to GPT-4o: {gpt4o_percent:.1f}% ({gpt4o_count}/{total_cells})")

        # Emergency case: if all cells are empty, try using pre-recognized text from cells
        all_empty = all(not cell.get('text') for cell in ocr_results)
        if all_empty and len(ocr_results) > 2:
            logger.warning("All cells have no text. Adding pre-recognized text from cell structure.")
            # If there's HTML representation, add text from HTML
            for i, cell in enumerate(ocr_results):
                if 'text' in cell and not cell['text'] and cell.get('structure') and 'text' in cell['structure']:
                    ocr_results[i]['text'] = cell['structure'].get('text', '')
                    logger.info(f"Added text from HTML for cell {i}: {ocr_results[i]['text']}")
                    
        # Measure time for building lines
        lines_build_start = time.time()
        
        # Build lines from cells
        lines = build_lines_from_cells(ocr_results)
        
        lines_build_time = time.time() - lines_build_start
        logger.info(f"[TIMING] Line building: {lines_build_time:.2f} sec. Lines formed: {len(lines)}")
        
        # Save statistics for response
        self._last_gpt4o_percent = gpt4o_percent
        self._last_gpt4o_count = gpt4o_count
        self._last_total_cells = total_cells
        return lines


def send_to_gpt(text: str, req_id: str) -> dict:
    """
    Send OCR text to OpenAI API for processing.
    
    Args:
        text: Extracted OCR text
        req_id: Request ID for tracking
        
    Returns:
        JSON response from OpenAI API
    """
    logger.info(f"[{req_id}] Sending to GPT: {len(text)} chars")
    
    try:
        response = openai.chat.completions.create(
            model=settings.OPENAI_GPT_MODEL,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": OCR_SYSTEM_PROMPT},
                {"role": "user", "content": text}
            ],
            temperature=0.2,
            seed=777,
        )
        logger.info(f"[{req_id}] Got GPT response, usage: {response.usage}")
        result = json.loads(response.choices[0].message.content)
        return result
    except Exception as e:
        logger.error(f"[{req_id}] Error sending to GPT: {e}")
        raise RuntimeError(f"Error calling OpenAI API: {e}")