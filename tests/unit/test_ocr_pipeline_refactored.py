"""
Unit tests for refactored OCR pipeline functionality.
"""
import pytest
pytest_plugins = ["pytest_asyncio"]
import json
import os
import base64
import numpy as np
from datetime import datetime
from PIL import Image
import io
from unittest.mock import MagicMock, patch, AsyncMock, call

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
from app.ocr_pipeline_refactored import OCRPipeline, send_to_gpt


@pytest.fixture
def mock_paddle_ocr():
    """Mock PaddleOCR instance for testing."""
    paddle_mock = MagicMock()
    # Default OCR result for a cell: [[(bbox, (text, confidence))]]
    paddle_mock.ocr.return_value = [
        [((0, 0, 100, 30), ("Test", 0.98))]
    ]
    return paddle_mock


@pytest.fixture
def mock_table_detector():
    """Mock table detector for testing."""
    detector_mock = MagicMock()
    detector_mock.detect.return_value = {"tables": 1, "cells": 10}
    detector_mock.extract_cells.return_value = [
        {
            "bbox": [0, 0, 100, 30],
            "image": b"test_image_data",
            "structure": {"text": "Product"}
        }
    ]
    return detector_mock


@pytest.fixture
def mock_validation_pipeline():
    """Mock validation pipeline for testing."""
    validation_mock = MagicMock()
    validation_mock.validate.side_effect = lambda x: x
    return validation_mock


@pytest.fixture
def sample_image_bytes():
    """Generate a simple test image."""
    img = Image.new('RGB', (100, 100), color='white')
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='JPEG')
    return img_bytes.getvalue()


@pytest.fixture
def sample_cells():
    """Generate sample cells for testing."""
    return [
        {
            "bbox": [0, 0, 100, 30],
            "image": b"test_image_data",
            "structure": {"text": "Product"}
        },
        {
            "bbox": [100, 0, 150, 30],
            "image": b"test_image_data",
            "structure": {"text": "1"}
        },
        {
            "bbox": [150, 0, 200, 30],
            "image": b"test_image_data",
            "structure": {"text": "kg"}
        },
        {
            "bbox": [200, 0, 250, 30],
            "image": b"test_image_data",
            "structure": {"text": "100"}
        },
        {
            "bbox": [250, 0, 300, 30],
            "image": b"test_image_data",
            "structure": {"text": "100"}
        }
    ]


def test_parse_numeric_value():
    """Test numeric value parsing."""
    # Now we can directly test the static method without accessing closures
    # This is much cleaner and more maintainable
    
    # Test various inputs
    assert OCRPipeline.parse_numeric_value("100", default=0) == 100
    assert OCRPipeline.parse_numeric_value("1,000", default=0) == 1000
    assert OCRPipeline.parse_numeric_value("1.000", default=0) == 1000
    assert OCRPipeline.parse_numeric_value("1 000", default=0) == 1000
    assert OCRPipeline.parse_numeric_value("1,000.50", default=0, is_float=True) == 1000.5
    assert OCRPipeline.parse_numeric_value("1.000,50", default=0, is_float=True) == 1000.5
    assert OCRPipeline.parse_numeric_value("invalid", default=42) == 42
    assert OCRPipeline.parse_numeric_value(None, default=99) == 99
    assert OCRPipeline.parse_numeric_value("", default=123) == 123


@pytest.mark.asyncio
async def test_process_cells_empty():
    """Test processing with empty cells."""
    with patch("app.ocr_pipeline_refactored.get_detector") as mock_get_detector, \
         patch("app.ocr_pipeline_refactored.PaddleOCR") as mock_paddle_ocr, \
         patch("app.ocr_pipeline_refactored.ValidationPipeline") as mock_validation:
        
        # Configure mocks
        mock_get_detector.return_value = MagicMock()
        mock_paddle_ocr.return_value = MagicMock()
        mock_validation.return_value = MagicMock()
        
        # Initialize pipeline
        pipeline = OCRPipeline()
        
        # Process empty cells
        result = await pipeline._process_cells([], ["en"])
        
        # Verify result is empty
        assert result == []
        assert pipeline._last_gpt4o_percent == 0
        assert pipeline._last_gpt4o_count == 0
        assert pipeline._last_total_cells == 0


@pytest.mark.asyncio
async def test_process_cells_with_ocr_errors(sample_cells):
    """Test processing cells with OCR errors."""
    with patch("app.ocr_pipeline_refactored.PaddleOCR") as mock_paddle_ocr:
        # Configure PaddleOCR to raise an exception
        paddle_instance = MagicMock()
        paddle_instance.ocr.side_effect = Exception("OCR Error")
        mock_paddle_ocr.return_value = paddle_instance
        
        # Mock process_cell_with_gpt4o to return fallback result
        async def mock_gpt4o(*args, **kwargs):
            return "Fallback Text", 0.8
        
        # Now we can directly patch the method
        with patch.object(OCRPipeline, "process_cell_with_gpt4o", side_effect=mock_gpt4o):
            
            # Initialize pipeline
            pipeline = OCRPipeline()
            
            # Process cells (should fall back to GPT-4o due to OCR error)
            lines = await pipeline._process_cells(sample_cells, ["en"])
            
            # Verify lines were created
            assert len(lines) > 0


@pytest.mark.asyncio
async def test_process_cells_all_errors(sample_cells):
    """Test cell processing when all OCR and GPT-4o calls fail."""
    with patch("app.ocr_pipeline_refactored.PaddleOCR") as mock_paddle_ocr, \
         patch.object(OCRPipeline, "process_cell_with_gpt4o", side_effect=Exception("GPT-4o Error")):
        
        # Configure mocks to raise exceptions
        paddle_instance = MagicMock()
        paddle_instance.ocr.side_effect = Exception("OCR Error")
        mock_paddle_ocr.return_value = paddle_instance
        
        # Initialize pipeline
        pipeline = OCRPipeline()
        
        # Process cells (all OCR and GPT-4o will fail)
        lines = await pipeline._process_cells(sample_cells, ["en"])
        
        # Verify appropriate empty cells were returned
        # Cells may be empty but the structure should exist
        assert isinstance(lines, list)


@pytest.mark.asyncio
async def test_process_cells_row_grouping(sample_cells):
    """Test row grouping logic in cell processing."""
    with patch("app.ocr_pipeline_refactored.PaddleOCR") as mock_paddle_ocr:
        # Configure mock to return specific texts
        paddle_instance = MagicMock()
        
        # Simulate different OCR results for each cell
        # This will let us test the row grouping logic
        def ocr_side_effect(np_img, **kwargs):
            # Return different texts based on the call count
            call_count = paddle_instance.ocr.call_count
            texts = [
                [((0, 0, 100, 30), ("Product A", 0.98))],
                [((0, 0, 100, 30), ("10", 0.99))],
                [((0, 0, 100, 30), ("kg", 0.97))],
                [((0, 0, 100, 30), ("1000", 0.99))],
                [((0, 0, 100, 30), ("10000", 0.99))]
            ]
            if call_count < len(texts):
                return [texts[call_count]]
            return [texts[0]]
        
        paddle_instance.ocr.side_effect = ocr_side_effect
        mock_paddle_ocr.return_value = paddle_instance
        
        # Initialize pipeline
        pipeline = OCRPipeline()
        
        # Modify sample cells to have different y-coordinates for row grouping
        row1_cells = [
            {**sample_cells[0], "bbox": [0, 10, 100, 40]},
            {**sample_cells[1], "bbox": [100, 12, 150, 42]},
            {**sample_cells[2], "bbox": [150, 8, 200, 38]},
            {**sample_cells[3], "bbox": [200, 11, 250, 41]},
            {**sample_cells[4], "bbox": [250, 13, 300, 43]}
        ]
        
        row2_cells = [
            {**sample_cells[0], "bbox": [0, 60, 100, 90]},
            {**sample_cells[1], "bbox": [100, 58, 150, 88]},
            {**sample_cells[2], "bbox": [150, 62, 200, 92]},
            {**sample_cells[3], "bbox": [200, 59, 250, 89]},
            {**sample_cells[4], "bbox": [250, 61, 300, 91]}
        ]
        
        # Combine rows
        test_cells = row1_cells + row2_cells
        
        # Process cells
        lines = await pipeline._process_cells(test_cells, ["en"])
        
        # Verify row grouping
        assert len(lines) == 2  # Should have two rows
        
        # Check first row data
        assert lines[0]["name"] == "Product A"
        assert lines[0]["qty"] == 10
        assert lines[0]["unit"] == "kg"
        assert lines[0]["price"] == 1000
        assert lines[0]["amount"] == 10000


@pytest.mark.asyncio
async def test_process_with_openai_vision_success():
    """Test OpenAI Vision processing success path."""
    with patch("app.ocr_pipeline_refactored.call_openai_ocr_async", new_callable=AsyncMock) as mock_call_ocr, \
         patch("app.ocr_pipeline_refactored.settings") as mock_settings:
        
        # Configure mocks
        mock_call_ocr.return_value = json.dumps({
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
        mock_settings.OPENAI_API_KEY = "test-key"
        
        # Initialize pipeline
        pipeline = OCRPipeline()
        
        # Process with OpenAI Vision
        result = await pipeline._process_with_openai_vision(b"test_image", ["en"])
        
        # Verify result structure
        assert result["status"] == "success"
        assert len(result["lines"]) == 1
        assert result["lines"][0]["name"] == "Test Product"
        assert result["lines"][0]["qty"] == 1
        assert result["lines"][0]["unit"] == "pcs"
        assert result["lines"][0]["price"] == 100
        assert result["lines"][0]["amount"] == 100


@pytest.mark.asyncio
async def test_process_with_openai_vision_error():
    """Test OpenAI Vision processing error path."""
    with patch("app.ocr_pipeline_refactored.call_openai_ocr_async", new_callable=AsyncMock) as mock_call_ocr, \
         patch("app.ocr_pipeline_refactored.settings") as mock_settings:
        
        # Configure mocks
        mock_call_ocr.side_effect = Exception("API Error")
        mock_settings.OPENAI_API_KEY = "test-key"
        
        # Initialize pipeline
        pipeline = OCRPipeline()
        
        # Process with OpenAI Vision
        result = await pipeline._process_with_openai_vision(b"test_image", ["en"])
        
        # Verify result structure
        assert result["status"] == "error"
        assert "message" in result
        assert "API Error" in result["message"]


@pytest.mark.asyncio
async def test_process_with_openai_vision_invalid_json():
    """Test OpenAI Vision processing with invalid JSON response."""
    with patch("app.ocr_pipeline_refactored.call_openai_ocr_async", new_callable=AsyncMock) as mock_call_ocr, \
         patch("app.ocr_pipeline_refactored.settings") as mock_settings:
        
        # Configure mocks
        mock_call_ocr.return_value = "Not a JSON response"
        mock_settings.OPENAI_API_KEY = "test-key"
        
        # Initialize pipeline
        pipeline = OCRPipeline()
        
        # Process with OpenAI Vision
        result = await pipeline._process_with_openai_vision(b"test_image", ["en"])
        
        # Verify result structure
        assert result["status"] == "error"
        assert "message" in result
        assert "raw_result" in result
        assert result["raw_result"] == "Not a JSON response"


def test_send_to_gpt_normal():
    """Test normal operation of send_to_gpt function."""
    with patch("openai.chat.completions.create") as mock_create, \
         patch("app.ocr_pipeline_refactored.settings") as mock_settings:
        
        # Configure mocks
        mock_response = MagicMock()
        mock_response.usage = {"total_tokens": 100}
        mock_response.choices = [
            MagicMock(message=MagicMock(content='{"result": "success"}'))
        ]
        mock_create.return_value = mock_response
        mock_settings.OPENAI_GPT_MODEL = "gpt-3.5-turbo"
        
        # Call function
        result = send_to_gpt("Sample text", "req-123")
        
        # Verify result
        assert result == {"result": "success"}
        
        # Verify API call
        mock_create.assert_called_once()
        call_args = mock_create.call_args[1]
        assert call_args["model"] == "gpt-3.5-turbo"
        assert call_args["response_format"]["type"] == "json_object"
        assert len(call_args["messages"]) == 2
        assert call_args["messages"][1]["content"] == "Sample text"


def test_send_to_gpt_error():
    """Test error handling in send_to_gpt function."""
    with patch("openai.chat.completions.create", side_effect=Exception("API Error")), \
         patch("app.ocr_pipeline_refactored.settings") as mock_settings:
        
        # Configure mocks
        mock_settings.OPENAI_GPT_MODEL = "gpt-3.5-turbo"
        
        # Call function and check error handling
        with pytest.raises(RuntimeError) as excinfo:
            send_to_gpt("Sample text", "req-123")
        
        # Verify error message
        assert "Error calling OpenAI API" in str(excinfo.value)
        assert "API Error" in str(excinfo.value)


@pytest.mark.asyncio
async def test_ocr_cell_success(sample_image_bytes):
    """Test successful OCR of a cell."""
    with patch("app.ocr_pipeline_refactored.PaddleOCR") as mock_paddle_ocr:
        # Configure mock
        paddle_instance = MagicMock()
        paddle_instance.ocr.return_value = [
            [((0, 0, 100, 30), ("Cell Text", 0.98))]
        ]
        mock_paddle_ocr.return_value = paddle_instance
        
        # Initialize pipeline
        pipeline = OCRPipeline()
        
        # Process a single cell using the extracted method
        cell = {
            "bbox": [0, 0, 100, 30],
            "image": sample_image_bytes,
            "structure": {"text": "Test"}
        }
        result = await pipeline._ocr_cell(cell)
        
        # Verify result
        assert result is not None
        assert "text" in result
        assert result["text"] == "Cell Text"
        assert "confidence" in result
        assert result["confidence"] >= 0.9
        assert "used_gpt4o" in result
        assert not result["used_gpt4o"]


@pytest.mark.asyncio
async def test_ocr_cell_too_small():
    """Test handling of cell images that are too small."""
    with patch("app.ocr_pipeline_refactored.PaddleOCR") as mock_paddle_ocr, \
         patch("PIL.Image.open") as mock_image_open:
        
        # Configure mocks
        paddle_instance = MagicMock()
        mock_paddle_ocr.return_value = paddle_instance
        
        # Mock a tiny image
        mock_img = MagicMock()
        mock_img.width = 5
        mock_img.height = 5
        mock_img.convert.return_value = mock_img
        mock_image_open.return_value = mock_img
        
        # Initialize pipeline
        pipeline = OCRPipeline()
        
        # Test with a tiny image cell
        cell = {"bbox": [0, 0, 100, 30], "image": b"tiny_image", "structure": {"text": "Test"}}
        result = await pipeline._ocr_cell(cell)
        
        # Verify the tiny image was detected and handled
        assert "error" in result
        assert result["error"] == "too_small"


@pytest.mark.asyncio
async def test_process_cell_with_gpt4o():
    """Test the GPT-4o cell processing method directly."""
    # This test directly tests the extracted method
    
    # Mock OpenAI client
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content="Extracted Text"))
    ]
    mock_client.chat.completions.create.return_value = mock_response
    
    with patch("app.ocr_pipeline_refactored.get_ocr_client", return_value=mock_client):
        # Initialize pipeline
        pipeline = OCRPipeline()
        
        # Call the method directly
        text, confidence = await pipeline.process_cell_with_gpt4o(b"test_image_data")
        
        # Verify results
        assert text == "Extracted Text"
        assert confidence == 1.0
        
        # Verify API call was made correctly
        mock_client.chat.completions.create.assert_called_once()
        call_args = mock_client.chat.completions.create.call_args[1]
        assert call_args["model"] == "gpt-4o"
        assert call_args["temperature"] == 0.0
        assert call_args["max_tokens"] == 100


@pytest.mark.asyncio
async def test_process_cell_with_gpt4o_no_client():
    """Test GPT-4o processing when no client is available."""
    with patch("app.ocr_pipeline_refactored.get_ocr_client", return_value=None):
        # Initialize pipeline
        pipeline = OCRPipeline()
        
        # Call the method directly
        text, confidence = await pipeline.process_cell_with_gpt4o(b"test_image_data")
        
        # Verify default empty results when no client
        assert text == ""
        assert confidence == 0.0


@pytest.mark.asyncio
async def test_process_cell_with_gpt4o_invalid_client():
    """Test GPT-4o processing with invalid client."""
    # Mock client without chat attribute
    mock_client = MagicMock(spec=[])
    
    with patch("app.ocr_pipeline_refactored.get_ocr_client", return_value=mock_client):
        # Initialize pipeline
        pipeline = OCRPipeline()
        
        # Call the method directly
        text, confidence = await pipeline.process_cell_with_gpt4o(b"test_image_data")
        
        # Verify default empty results with invalid client
        assert text == ""
        assert confidence == 0.0


@pytest.mark.asyncio
async def test_process_cell_with_gpt4o_api_error():
    """Test GPT-4o processing with API error."""
    # Mock client that raises exception
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = Exception("API Error")
    
    with patch("app.ocr_pipeline_refactored.get_ocr_client", return_value=mock_client):
        # Initialize pipeline
        pipeline = OCRPipeline()
        
        # Call the method directly
        text, confidence = await pipeline.process_cell_with_gpt4o(b"test_image_data")
        
        # Verify error handling
        assert text == ""
        assert confidence == 0.0


@pytest.mark.asyncio
async def test_build_lines_from_cells():
    """Test the line building logic directly."""
    # Create mock cells with OCR results
    cells = [
        {
            "bbox": [0, 10, 100, 40],
            "text": "Product A",
            "confidence": 0.95,
            "used_gpt4o": False
        },
        {
            "bbox": [100, 12, 150, 42],
            "text": "10",
            "confidence": 0.98,
            "used_gpt4o": False
        },
        {
            "bbox": [150, 11, 200, 41],
            "text": "kg",
            "confidence": 0.97,
            "used_gpt4o": False
        },
        {
            "bbox": [200, 9, 250, 39],
            "text": "1000",
            "confidence": 0.99,
            "used_gpt4o": False
        },
        {
            "bbox": [250, 10, 300, 40],
            "text": "10000",
            "confidence": 0.99,
            "used_gpt4o": False
        }
    ]
    
    # Initialize pipeline
    with patch("app.ocr_pipeline_refactored.get_detector") as mock_get_detector, \
         patch("app.ocr_pipeline_refactored.PaddleOCR") as mock_paddle_ocr, \
         patch("app.ocr_pipeline_refactored.ValidationPipeline") as mock_validation:
        mock_get_detector.return_value = MagicMock()
        mock_paddle_ocr.return_value = MagicMock()
        mock_validation.return_value = MagicMock()
        
        pipeline = OCRPipeline()
        
        # Call the method directly
        lines = pipeline._build_lines_from_cells(cells)
        
        # Verify result
        assert len(lines) == 1
        assert lines[0]["name"] == "Product A"
        assert lines[0]["qty"] == 10
        assert lines[0]["unit"] == "kg"
        assert lines[0]["price"] == 1000
        assert lines[0]["amount"] == 10000
        assert len(lines[0]["cells"]) == 5


@pytest.mark.asyncio
async def test_numeric_parsing_edge_cases():
    """Test edge cases in numeric parsing."""
    # Test various edge cases directly with the static method
    assert OCRPipeline.parse_numeric_value("Rp 10.000", default=0) == 10000  # Currency symbol
    assert OCRPipeline.parse_numeric_value("10.000,00", default=0, is_float=True) == 10000.00  # European style
    assert OCRPipeline.parse_numeric_value("10,000.00", default=0, is_float=True) == 10000.00  # US style
    assert OCRPipeline.parse_numeric_value("N/A", default=42) == 42  # Non-numeric
    assert OCRPipeline.parse_numeric_value("--", default=0) == 0  # Dashes
    assert OCRPipeline.parse_numeric_value("$ 1,234.56", default=0, is_float=True) == 1234.56  # With currency