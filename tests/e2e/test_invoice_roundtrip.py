"""
End-to-end tests for full OCR invoice processing pipeline.
Tests the entire flow from image input to parsed structured data.
"""
import pytest
pytest_plugins = ["pytest_asyncio"]
import json
import os
import base64
import numpy as np
from PIL import Image
import io
from unittest.mock import MagicMock, patch, AsyncMock
import datetime

# Add paddleocr mock to avoid import error
import sys
if 'paddleocr' not in sys.modules:
    sys.modules['paddleocr'] = MagicMock()
    # Create PaddleOCR class mock
    PaddleOCR = MagicMock()
    PaddleOCR.return_value.ocr.return_value = [
        [((0, 0, 100, 30), ("Test Text", 0.95))]
    ]
    sys.modules['paddleocr'].PaddleOCR = PaddleOCR

# Import after mocking
from app.ocr_pipeline import OCRPipeline
from app.models import ParsedData
from app.validators.pipeline import ValidationPipeline
from app.postprocessing import postprocess_parsed_data


@pytest.fixture
def sample_invoice_png():
    """Generate a sample invoice image for testing."""
    # Check if test assets directory exists
    assets_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'assets')
    sample_path = os.path.join(assets_dir, 'sample_invoice.png')
    
    # If the sample exists, use it
    if os.path.exists(sample_path):
        with open(sample_path, "rb") as f:
            return f.read()
    
    # Otherwise, generate a simple test image with invoice-like content
    img = Image.new('RGB', (800, 1000), color='white')
    draw = Image.new('RGB', img.size, color='white').getimages()[0].getcontext()
    
    # Draw invoice content
    draw.text((50, 50), "INVOICE", fill="black")
    draw.text((50, 100), "Supplier: Test Company", fill="black")
    draw.text((50, 150), "Date: 2025-01-01", fill="black")
    
    # Draw table headers
    draw.text((50, 200), "Product", fill="black")
    draw.text((350, 200), "Qty", fill="black")
    draw.text((450, 200), "Unit", fill="black")
    draw.text((550, 200), "Price", fill="black")
    draw.text((650, 200), "Total", fill="black")
    
    # Draw table rows
    draw.text((50, 250), "Test Product", fill="black")
    draw.text((350, 250), "1", fill="black")
    draw.text((450, 250), "pcs", fill="black")
    draw.text((550, 250), "100", fill="black")
    draw.text((650, 250), "100", fill="black")
    
    # Draw total
    draw.text((550, 300), "Total:", fill="black")
    draw.text((650, 300), "100", fill="black")
    
    # Save to bytes
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='PNG')
    return img_bytes.getvalue()


@pytest.fixture
def mock_table_detector():
    """Mock table detector for testing."""
    detector_mock = MagicMock()
    detector_mock.detect.return_value = {"tables": 1, "cells": 10}
    
    # Generate sample cells that mimic a real invoice structure
    cells = [
        # Header row
        {
            "bbox": [50, 200, 300, 230],
            "image": b"header_image",
            "structure": {"text": "Product"}
        },
        {
            "bbox": [350, 200, 400, 230],
            "image": b"header_image",
            "structure": {"text": "Qty"}
        },
        {
            "bbox": [450, 200, 500, 230],
            "image": b"header_image",
            "structure": {"text": "Unit"}
        },
        {
            "bbox": [550, 200, 600, 230],
            "image": b"header_image",
            "structure": {"text": "Price"}
        },
        {
            "bbox": [650, 200, 700, 230],
            "image": b"header_image",
            "structure": {"text": "Total"}
        },
        # Data row
        {
            "bbox": [50, 250, 300, 280],
            "image": b"data_image",
            "structure": {"text": "Test Product"}
        },
        {
            "bbox": [350, 250, 400, 280],
            "image": b"data_image",
            "structure": {"text": "1"}
        },
        {
            "bbox": [450, 250, 500, 280],
            "image": b"data_image",
            "structure": {"text": "pcs"}
        },
        {
            "bbox": [550, 250, 600, 280],
            "image": b"data_image",
            "structure": {"text": "100"}
        },
        {
            "bbox": [650, 250, 700, 280],
            "image": b"data_image",
            "structure": {"text": "100"}
        }
    ]
    detector_mock.extract_cells.return_value = cells
    return detector_mock


@pytest.fixture
def mock_paddle_ocr():
    """Mock PaddleOCR for testing."""
    paddle_mock = MagicMock()
    
    # Define a side effect to return different text based on bounding box
    def ocr_side_effect(np_img, **kwargs):
        # Get image dimensions to identify which cell we're processing
        # For test, we just fake it with a static mapping
        
        # Use call count to determine which cell is being processed
        call_count = paddle_mock.ocr.call_count
        
        # Map call count to expected text and confidence
        cell_results = {
            1: [((0, 0, 100, 30), ("Product", 0.98))],
            2: [((0, 0, 100, 30), ("Qty", 0.99))],
            3: [((0, 0, 100, 30), ("Unit", 0.97))],
            4: [((0, 0, 100, 30), ("Price", 0.99))],
            5: [((0, 0, 100, 30), ("Total", 0.99))],
            6: [((0, 0, 100, 30), ("Test Product", 0.95))],
            7: [((0, 0, 100, 30), ("1", 0.99))],
            8: [((0, 0, 100, 30), ("pcs", 0.98))],
            9: [((0, 0, 100, 30), ("100", 0.99))],
            10: [((0, 0, 100, 30), ("100", 0.99))]
        }
        
        # Return the result for this call
        if call_count in cell_results:
            return [cell_results[call_count]]
        
        # Default fallback
        return [[((0, 0, 100, 30), ("Unknown", 0.5))]]
    
    # Configure the mock
    paddle_mock.ocr.side_effect = ocr_side_effect
    return paddle_mock


@pytest.fixture
def mock_validation_pipeline():
    """Mock validation pipeline for testing."""
    validation_mock = MagicMock()
    
    def validate_func(result):
        """Simple validation that just adds validation information."""
        result["validated"] = True
        result["validation_passed"] = True
        result["issues"] = []
        return result
    
    validation_mock.validate.side_effect = validate_func
    return validation_mock


@pytest.fixture
def mock_openai_vision():
    """Mock OpenAI Vision API call."""
    # Prepare mock response
    sample_response = json.dumps({
        "lines": [
            {
                "name": "Test Product",
                "qty": 1,
                "unit": "pcs",
                "price": 100,
                "amount": 100
            }
        ]
    })
    
    mock_call = AsyncMock(return_value=sample_response)
    return mock_call


@pytest.mark.asyncio
async def test_e2e_table_detection_path(sample_invoice_png, mock_table_detector, mock_paddle_ocr, mock_validation_pipeline):
    """Test the full pipeline using table detection path."""
    with patch("app.ocr_pipeline.get_detector", return_value=mock_table_detector), \
         patch("app.ocr_pipeline.PaddleOCR", return_value=mock_paddle_ocr), \
         patch("app.ocr_pipeline.ValidationPipeline", return_value=mock_validation_pipeline):
        
        # Initialize pipeline
        pipeline = OCRPipeline()
        
        # Process the invoice
        result = await pipeline.process_image(sample_invoice_png, ["en"])
        
        # Verify calls to dependencies
        mock_table_detector.detect.assert_called_once()
        mock_table_detector.extract_cells.assert_called_once()
        assert mock_paddle_ocr.ocr.call_count > 0
        mock_validation_pipeline.validate.assert_called_once()
        
        # Verify result structure
        assert result["status"] == "success"
        assert "lines" in result
        assert len(result["lines"]) > 0
        assert "timing" in result
        assert "total_time" in result
        assert "validated" in result
        
        # Verify data content
        first_line = result["lines"][0]
        assert "name" in first_line
        assert "qty" in first_line
        assert "unit" in first_line
        assert "price" in first_line
        assert "amount" in first_line
        assert first_line["name"] == "Test Product"
        assert first_line["qty"] == 1
        assert first_line["unit"] == "pcs"
        assert first_line["price"] == 100
        assert first_line["amount"] == 100


@pytest.mark.asyncio
async def test_e2e_openai_vision_fallback(sample_invoice_png, mock_validation_pipeline, mock_openai_vision):
    """Test the full pipeline using OpenAI Vision fallback."""
    # Create a table detector that raises an exception
    error_detector = MagicMock()
    error_detector.detect.side_effect = Exception("Table detection failed")
    
    with patch("app.ocr_pipeline.get_detector", return_value=error_detector), \
         patch("app.ocr_pipeline.ValidationPipeline", return_value=mock_validation_pipeline), \
         patch("app.ocr_pipeline.call_openai_ocr", mock_openai_vision):
        
        # Initialize pipeline
        pipeline = OCRPipeline()
        
        # Process the invoice
        result = await pipeline.process_image(sample_invoice_png, ["en"])
        
        # Verify calls to dependencies
        error_detector.detect.assert_called_once()
        mock_openai_vision.assert_called_once()
        mock_validation_pipeline.validate.assert_called_once()
        
        # Verify result structure
        assert result["status"] == "success"
        assert "lines" in result
        assert "used_fallback" in result
        assert result["used_fallback"] is True
        assert "validated" in result
        
        # Verify data content
        first_line = result["lines"][0]
        assert "name" in first_line
        assert "qty" in first_line
        assert "unit" in first_line
        assert "price" in first_line
        assert "amount" in first_line
        assert first_line["name"] == "Test Product"
        assert first_line["qty"] == 1
        assert first_line["unit"] == "pcs"
        assert first_line["price"] == 100
        assert first_line["amount"] == 100


@pytest.mark.asyncio
async def test_e2e_with_arithmetic_errors(sample_invoice_png, mock_table_detector, mock_paddle_ocr):
    """Test validation with arithmetic errors."""
    # Create validation pipeline that detects arithmetic errors
    validation_mock = MagicMock()
    
    def validate_with_error(result):
        """Validation that adds arithmetic error."""
        result["validated"] = True
        result["validation_passed"] = False
        result["issues"] = ["Arithmetic error: amount doesn't match qty * price"]
        
        # Modify a price to introduce an error
        if "lines" in result and len(result["lines"]) > 0:
            result["lines"][0]["amount"] = 999  # Introduce error
        
        return result
    
    validation_mock.validate.side_effect = validate_with_error
    
    with patch("app.ocr_pipeline.get_detector", return_value=mock_table_detector), \
         patch("app.ocr_pipeline.PaddleOCR", return_value=mock_paddle_ocr), \
         patch("app.ocr_pipeline.ValidationPipeline", return_value=validation_mock):
        
        # Initialize pipeline
        pipeline = OCRPipeline()
        
        # Process the invoice
        result = await pipeline.process_image(sample_invoice_png, ["en"])
        
        # Verify validation was called
        validation_mock.validate.assert_called_once()
        
        # Verify error was detected
        assert "validated" in result
        assert "issues" in result
        assert len(result["issues"]) > 0
        assert "Arithmetic error" in result["issues"][0]
        
        # Verify the erroneous data
        assert result["lines"][0]["amount"] == 999


@pytest.mark.asyncio
async def test_e2e_complete_failure(sample_invoice_png):
    """Test complete failure of the pipeline."""
    # Create mocks that all raise exceptions
    error_detector = MagicMock()
    error_detector.detect.side_effect = Exception("Table detection failed")
    
    with patch("app.ocr_pipeline.get_detector", return_value=error_detector), \
         patch("app.ocr_pipeline.call_openai_ocr", side_effect=Exception("OpenAI API error")):
        
        # Initialize pipeline
        pipeline = OCRPipeline()
        
        # Process the invoice
        result = await pipeline.process_image(sample_invoice_png, ["en"])
        
        # Verify error response
        assert result["status"] == "error"
        assert "message" in result
        assert "timing" in result
        assert "total_time" in result


@pytest.mark.asyncio
async def test_e2e_invalid_image():
    """Test processing invalid image data."""
    with patch("app.ocr_pipeline.get_detector") as mock_get_detector, \
         patch("app.ocr_pipeline.PaddleOCR") as mock_paddle_ocr, \
         patch("app.ocr_pipeline.ValidationPipeline") as mock_validation:
        
        # Configure default mocks
        mock_get_detector.return_value = MagicMock()
        mock_paddle_ocr.return_value = MagicMock()
        mock_validation.return_value = MagicMock()
        
        # Initialize pipeline
        pipeline = OCRPipeline()
        
        # Process invalid image
        result = await pipeline.process_image(b"invalid_image_data", ["en"])
        
        # Verify error response
        assert result["status"] == "error"
        assert "message" in result
        assert "timing" in result
        assert "total_time" in result


@pytest.mark.asyncio
async def test_e2e_no_cells_found(sample_invoice_png):
    """Test when no cells are found in the image."""
    # Mock table detector that detects table but no cells
    empty_detector = MagicMock()
    empty_detector.detect.return_value = {"tables": 1, "cells": 0}
    empty_detector.extract_cells.return_value = []
    
    with patch("app.ocr_pipeline.get_detector", return_value=empty_detector), \
         patch("app.ocr_pipeline.ValidationPipeline", return_value=MagicMock()), \
         patch("app.ocr_pipeline.call_openai_ocr", new_callable=AsyncMock) as mock_vision:
        
        # Configure vision mock
        mock_vision.return_value = json.dumps({
            "lines": [
                {
                    "name": "Test Product (Fallback)",
                    "qty": 1,
                    "unit": "pcs",
                    "price": 100,
                    "amount": 100
                }
            ]
        })
        
        # Initialize pipeline
        pipeline = OCRPipeline()
        
        # Process the invoice
        result = await pipeline.process_image(sample_invoice_png, ["en"])
        
        # Verify fallback was used
        mock_vision.assert_called_once()
        assert "used_fallback" in result
        
        # Verify data content from fallback
        assert result["lines"][0]["name"] == "Test Product (Fallback)"


@pytest.mark.asyncio
async def test_parse_numeric_value_in_e2e(sample_invoice_png, mock_table_detector, mock_paddle_ocr, mock_validation_pipeline):
    """Test numeric parsing in e2e context."""
    # Override PaddleOCR mock to return special numeric formats
    special_paddle_mock = MagicMock()
    
    def ocr_side_effect(np_img, **kwargs):
        call_count = special_paddle_mock.ocr.call_count
        
        # Return special numeric formats for amount and price
        if call_count == 9:  # Price cell
            return [[((0, 0, 100, 30), ("1,000.00", 0.99))]]
        elif call_count == 10:  # Amount cell
            return [[((0, 0, 100, 30), ("1.000,00", 0.99))]]
        
        # Default for other cells
        default_results = {
            1: [((0, 0, 100, 30), ("Product", 0.98))],
            2: [((0, 0, 100, 30), ("Qty", 0.99))],
            3: [((0, 0, 100, 30), ("Unit", 0.97))],
            4: [((0, 0, 100, 30), ("Price", 0.99))],
            5: [((0, 0, 100, 30), ("Total", 0.99))],
            6: [((0, 0, 100, 30), ("Test Product", 0.95))],
            7: [((0, 0, 100, 30), ("1", 0.99))],
            8: [((0, 0, 100, 30), ("pcs", 0.98))]
        }
        
        if call_count in default_results:
            return [default_results[call_count]]
        
        return [[((0, 0, 100, 30), ("Unknown", 0.5))]]
    
    special_paddle_mock.ocr.side_effect = ocr_side_effect
    
    with patch("app.ocr_pipeline.get_detector", return_value=mock_table_detector), \
         patch("app.ocr_pipeline.PaddleOCR", return_value=special_paddle_mock), \
         patch("app.ocr_pipeline.ValidationPipeline", return_value=mock_validation_pipeline):
        
        # Initialize pipeline
        pipeline = OCRPipeline()
        
        # Process the invoice
        result = await pipeline.process_image(sample_invoice_png, ["en"])
        
        # Verify numeric parsing
        assert result["status"] == "success"
        assert len(result["lines"]) > 0
        
        # Check numeric parsing of price and amount
        first_line = result["lines"][0]
        assert first_line["price"] == 1000.00  # From 1,000.00 (US format)
        assert first_line["amount"] == 1000.00  # From 1.000,00 (EU format)