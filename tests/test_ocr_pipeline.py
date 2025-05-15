"""
Integration tests for OCR pipeline functionality.
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
from app.ocr_pipeline import OCRPipeline, send_to_gpt
from app.models import ParsedData


@pytest.fixture
def mock_paddle_ocr():
    """Mock PaddleOCR instance for testing."""
    paddle_mock = MagicMock()
    # Default OCR result for a cell: [[(bbox, (text, confidence))]]
    paddle_mock.ocr.return_value = [
        [((0, 0, 100, 30), ("Product", 0.98))]
    ]
    return paddle_mock


@pytest.fixture
def mock_table_detector():
    """Mock table detector for testing."""
    detector_mock = MagicMock()
    detector_mock.detect.return_value = {"tables": 1, "cells": 10}
    
    # Generate sample cells
    cells = [
        {
            "bbox": [0, 0, 100, 30],
            "image": b"test_image_data",
            "structure": {"text": "Product Name"}
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
            "structure": {"text": "10000"}
        },
        {
            "bbox": [250, 0, 300, 30],
            "image": b"test_image_data",
            "structure": {"text": "10000"}
        }
    ]
    detector_mock.extract_cells.return_value = cells
    return detector_mock


@pytest.fixture
def mock_validation_pipeline():
    """Mock validation pipeline for testing."""
    validation_mock = MagicMock()
    
    def validate_func(result):
        """Simple validation that just adds a validated flag."""
        result["validated"] = True
        return result
    
    validation_mock.validate.side_effect = validate_func
    return validation_mock


@pytest.fixture
def sample_image_bytes():
    """Generate a simple test image."""
    img = Image.new('RGB', (100, 100), color='white')
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='JPEG')
    return img_bytes.getvalue()


@pytest.fixture
def mock_openai_response():
    """Mock response from OpenAI Vision API."""
    return json.dumps({
        "supplier": "Test Supplier",
        "date": "2025-01-01",
        "lines": [
            {
                "name": "Test Product",
                "qty": 1,
                "unit": "pcs",
                "price": 100,
                "amount": 100
            }
        ],
        "total_amount": 100
    })


def test_ocr_pipeline_init():
    """Test OCR pipeline initialization with default parameters."""
    with patch("app.ocr_pipeline.get_detector") as mock_get_detector, \
         patch("app.ocr_pipeline.PaddleOCR") as mock_paddle_ocr, \
         patch("app.ocr_pipeline.ValidationPipeline") as mock_validation:
        
        # Configure mocks
        mock_get_detector.return_value = MagicMock()
        mock_paddle_ocr.return_value = MagicMock()
        mock_validation.return_value = MagicMock()
        
        # Initialize pipeline
        pipeline = OCRPipeline()
        
        # Verify initialization
        assert pipeline.table_detector is not None
        assert pipeline.validation_pipeline is not None
        assert pipeline.paddle_ocr is not None
        assert pipeline.low_conf_threshold == 0.7  # Check default threshold


def test_ocr_pipeline_init_custom_params():
    """Test OCR pipeline initialization with custom parameters."""
    with patch("app.ocr_pipeline.get_detector") as mock_get_detector, \
         patch("app.ocr_pipeline.PaddleOCR") as mock_paddle_ocr, \
         patch("app.ocr_pipeline.ValidationPipeline") as mock_validation:
        
        # Configure mocks
        mock_get_detector.return_value = MagicMock()
        mock_paddle_ocr.return_value = MagicMock()
        mock_validation.return_value = MagicMock()
        
        # Initialize pipeline with custom parameters
        pipeline = OCRPipeline(table_detector_method="custom", paddle_ocr_lang="ru")
        
        # Verify initialization with custom parameters
        mock_get_detector.assert_called_once_with(method="custom")
        mock_paddle_ocr.assert_called_once()
        paddle_call_args = mock_paddle_ocr.call_args[1]
        assert paddle_call_args["lang"] == "ru"
        assert paddle_call_args["use_angle_cls"] is True
        assert paddle_call_args["show_log"] is False


@pytest.mark.asyncio
async def test_process_image_success(sample_image_bytes, mock_table_detector, mock_paddle_ocr, mock_validation_pipeline):
    """Test successful processing of an image through table detection."""
    with patch("app.ocr_pipeline.get_detector", return_value=mock_table_detector), \
         patch("app.ocr_pipeline.PaddleOCR", return_value=mock_paddle_ocr), \
         patch("app.ocr_pipeline.ValidationPipeline", return_value=mock_validation_pipeline):
        
        # Initialize pipeline
        pipeline = OCRPipeline()
        
        # Process image
        result = await pipeline.process_image(sample_image_bytes, ["en"])
        
        # Verify calls
        mock_table_detector.detect.assert_called_once()
        mock_table_detector.extract_cells.assert_called_once()
        
        # Verify result structure
        assert result["status"] == "success"
        assert "lines" in result
        assert "accuracy" in result
        assert "issues" in result
        assert "timing" in result
        assert "total_time" in result
        assert "validated" in result  # Added by our mock validation


@pytest.mark.asyncio
async def test_process_image_table_detection_failure(sample_image_bytes, mock_validation_pipeline):
    """Test fallback to OpenAI Vision when table detection fails."""
    # Mock table detector that raises an exception
    error_detector = MagicMock()
    error_detector.detect.side_effect = Exception("Table detection failed")
    
    # Mock OpenAI Vision API call
    mock_vision_result = {
        "status": "success",
        "lines": [{"name": "Test Product", "qty": 1, "unit": "pcs", "price": 100, "amount": 100}],
        "accuracy": 0.9,
        "issues": []
    }
    
    with patch("app.ocr_pipeline.get_detector", return_value=error_detector), \
         patch("app.ocr_pipeline.ValidationPipeline", return_value=mock_validation_pipeline), \
         patch("app.ocr_pipeline.PaddleOCR", return_value=MagicMock()), \
         patch.object(OCRPipeline, "_process_with_openai_vision", new_callable=AsyncMock) as mock_vision:
        
        # Configure mock
        mock_vision.return_value = mock_vision_result
        
        # Initialize pipeline
        pipeline = OCRPipeline()
        
        # Process image
        result = await pipeline.process_image(sample_image_bytes, ["en"])
        
        # Verify calls
        error_detector.detect.assert_called_once()
        mock_vision.assert_called_once()
        
        # Verify result structure
        assert result["status"] == "success"
        assert "lines" in result
        assert "used_fallback" in result
        assert result["used_fallback"] is True
        assert "validated" in result  # Added by our mock validation


@pytest.mark.asyncio
async def test_process_image_invalid_image(mock_table_detector, mock_paddle_ocr, mock_validation_pipeline):
    """Test error handling for invalid images."""
    with patch("app.ocr_pipeline.get_detector", return_value=mock_table_detector), \
         patch("app.ocr_pipeline.PaddleOCR", return_value=mock_paddle_ocr), \
         patch("app.ocr_pipeline.ValidationPipeline", return_value=mock_validation_pipeline), \
         patch.object(OCRPipeline, "_process_cells", side_effect=Exception("Invalid image")):
        
        # Initialize pipeline
        pipeline = OCRPipeline()
        
        # Process invalid image
        result = await pipeline.process_image(b"invalid_image_data", ["en"])
        
        # Verify result indicates error
        assert result["status"] == "error"
        assert "message" in result
        assert "timing" in result
        assert "total_time" in result


@pytest.mark.asyncio
async def test_process_cells_high_confidence(sample_image_bytes, mock_paddle_ocr):
    """Test processing cells with high confidence (no GPT-4o fallback)."""
    with patch("app.ocr_pipeline.PaddleOCR", return_value=mock_paddle_ocr):
        # Initialize pipeline
        pipeline = OCRPipeline()
        
        # Create sample cells
        cells = [
            {
                "bbox": [0, 0, 100, 30],
                "image": sample_image_bytes,
                "structure": {"text": "Product"}
            },
            {
                "bbox": [0, 50, 100, 80],
                "image": sample_image_bytes,
                "structure": {"text": "Quantity"}
            }
        ]
        
        # Configure mock to return high confidence results
        mock_paddle_ocr.ocr.return_value = [
            [((0, 0, 100, 30), ("Product", 0.98))]
        ]
        
        # Process cells
        lines = await pipeline._process_cells(cells, ["en"])
        
        # Verify results
        assert len(lines) > 0
        
        # Check no GPT-4o calls were made (all cells had high confidence)
        for line in lines:
            if "cells" in line:
                for cell in line["cells"]:
                    assert cell.get("used_gpt4o", False) is False


@pytest.mark.asyncio
async def test_process_cells_low_confidence(sample_image_bytes):
    """Test processing cells with low confidence (triggers GPT-4o fallback)."""
    # Mock paddle OCR to return low confidence
    paddle_mock = MagicMock()
    paddle_mock.ocr.return_value = [
        [((0, 0, 100, 30), ("Product", 0.3))]
    ]
    
    # Setup mock for get_ocr_client
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content="Enhanced Text"))
    ]
    mock_client.chat.completions.create.return_value = mock_response
    
    with patch("app.ocr_pipeline.PaddleOCR", return_value=paddle_mock), \
         patch("app.ocr_pipeline.get_ocr_client", return_value=mock_client):
        
        # Initialize pipeline
        pipeline = OCRPipeline()
        
        # Create sample cells
        cells = [
            {
                "bbox": [0, 0, 100, 30],
                "image": sample_image_bytes,
                "structure": {"text": "Product"}
            }
        ]
        
        # Process cells
        lines = await pipeline._process_cells(cells, ["en"])
        
        # Verify client API was called
        mock_client.chat.completions.create.assert_called_once()
        
        # Check result
        assert len(lines) > 0


@pytest.mark.asyncio
async def test_process_with_openai_vision_success(sample_image_bytes):
    """Test successful processing with OpenAI Vision API."""
    # Mock OpenAI Vision API call
    with patch("app.ocr_pipeline.call_openai_ocr_async", new_callable=AsyncMock) as mock_call_ocr:
        # Configure mock to return successful result
        mock_call_ocr.return_value = json.dumps({
            "lines": [
                {"name": "Test Product", "qty": 1, "unit": "pcs", "price": 100, "amount": 100}
            ]
        })
        
        # Initialize pipeline
        pipeline = OCRPipeline()
        
        # Process with OpenAI Vision
        result = await pipeline._process_with_openai_vision(sample_image_bytes, ["en"])
        
        # Verify call was made
        mock_call_ocr.assert_called_once()
        
        # Verify result structure
        assert result["status"] == "success"
        assert "lines" in result
        assert len(result["lines"]) > 0
        assert "accuracy" in result
        assert "issues" in result


@pytest.mark.asyncio
async def test_process_with_openai_vision_error(sample_image_bytes):
    """Test error handling with OpenAI Vision API."""
    # Mock OpenAI Vision API call that raises exception
    with patch("app.ocr_pipeline.call_openai_ocr_async", new_callable=AsyncMock) as mock_call_ocr:
        # Configure mock to raise exception
        mock_call_ocr.side_effect = Exception("API Error")
        
        # Initialize pipeline
        pipeline = OCRPipeline()
        
        # Process with OpenAI Vision
        result = await pipeline._process_with_openai_vision(sample_image_bytes, ["en"])
        
        # Verify call was made
        mock_call_ocr.assert_called_once()
        
        # Verify result structure
        assert result["status"] == "error"
        assert "message" in result


@pytest.mark.asyncio
async def test_process_with_openai_vision_invalid_json(sample_image_bytes):
    """Test handling of invalid JSON response from OpenAI Vision API."""
    # Mock OpenAI Vision API call
    with patch("app.ocr_pipeline.call_openai_ocr_async", new_callable=AsyncMock) as mock_call_ocr:
        # Configure mock to return invalid JSON
        mock_call_ocr.return_value = "This is not JSON"
        
        # Initialize pipeline
        pipeline = OCRPipeline()
        
        # Process with OpenAI Vision
        result = await pipeline._process_with_openai_vision(sample_image_bytes, ["en"])
        
        # Verify call was made
        mock_call_ocr.assert_called_once()
        
        # Verify result structure
        assert result["status"] == "error"
        assert "message" in result
        assert "raw_result" in result


@pytest.mark.asyncio
async def test_integration_with_validation_pipeline(sample_image_bytes, mock_table_detector, mock_paddle_ocr):
    """Test integration with validation pipeline."""
    # Create validation pipeline that adds validation data
    validation_mock = MagicMock()
    def validate_func(result):
        """Add validation data to result."""
        result["validated"] = True
        result["validation_issues"] = ["Test issue"]
        return result
    validation_mock.validate.side_effect = validate_func
    
    with patch("app.ocr_pipeline.get_detector", return_value=mock_table_detector), \
         patch("app.ocr_pipeline.PaddleOCR", return_value=mock_paddle_ocr), \
         patch("app.ocr_pipeline.ValidationPipeline", return_value=validation_mock):
        
        # Initialize pipeline
        pipeline = OCRPipeline()
        
        # Process image
        result = await pipeline.process_image(sample_image_bytes, ["en"])
        
        # Verify validation was called
        validation_mock.validate.assert_called_once()
        
        # Verify validation data was added to result
        assert result["validated"] is True
        assert "validation_issues" in result
        assert result["validation_issues"] == ["Test issue"]


def test_send_to_gpt():
    """Test sending OCR text to OpenAI API for processing."""
    # Mock OpenAI client module
    with patch("app.ocr_pipeline.openai") as mock_openai:
        # Configure mock response
        mock_response = MagicMock()
        mock_response.usage = {"total_tokens": 100}
        mock_response.choices = [
            MagicMock(message=MagicMock(content='{"key": "value"}'))
        ]
        mock_openai.chat.completions.create.return_value = mock_response
        
        # Mock settings
        with patch("app.ocr_pipeline.settings") as mock_settings:
            mock_settings.OPENAI_GPT_MODEL = "gpt-3.5-turbo"
            
            # Call send_to_gpt
            result = send_to_gpt("Sample OCR text", "req123")
            
            # Verify API call
            mock_openai.chat.completions.create.assert_called_once()
            call_args = mock_openai.chat.completions.create.call_args[1]
            assert call_args["model"] == "gpt-3.5-turbo"
            assert call_args["response_format"]["type"] == "json_object"
            assert len(call_args["messages"]) == 2
            assert call_args["messages"][0]["role"] == "system"
            assert call_args["messages"][1]["role"] == "user"
            assert call_args["messages"][1]["content"] == "Sample OCR text"
            
            # Verify result
            assert result == {"key": "value"}


def test_send_to_gpt_error():
    """Test error handling in send_to_gpt function."""
    # Mock OpenAI module that raises exception
    with patch("app.ocr_pipeline.openai") as mock_openai:
        # Configure mock to raise exception
        mock_openai.chat.completions.create.side_effect = Exception("API Error")
        
        # Mock settings
        with patch("app.ocr_pipeline.settings") as mock_settings:
            mock_settings.OPENAI_GPT_MODEL = "gpt-3.5-turbo"
            
            # Call send_to_gpt and check error handling
            with pytest.raises(RuntimeError) as excinfo:
                send_to_gpt("Sample OCR text", "req123")
            
            # Verify error message
            assert "Error calling OpenAI API" in str(excinfo.value)


@pytest.mark.asyncio
async def test_process_cell_with_gpt4o(sample_image_bytes):
    """Test processing a cell with GPT-4o when available."""
    # Mock OpenAI client
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content="Enhanced Text"))
    ]
    mock_client.chat.completions.create.return_value = mock_response
    
    with patch("app.ocr_pipeline.get_ocr_client", return_value=mock_client):
        # Initialize pipeline
        pipeline = OCRPipeline()
        
        # Create a test cell with low confidence to trigger GPT-4o
        cells = [
            {
                "bbox": [0, 0, 100, 30],
                "image": sample_image_bytes,
                "structure": {"text": "Product"}
            }
        ]
        
        # Force low confidence to trigger GPT-4o
        with patch.object(pipeline.paddle_ocr, "ocr", return_value=[
            [((0, 0, 100, 30), ("Low Confidence Text", 0.2))]
        ]):
            # Process the cells
            lines = await pipeline._process_cells(cells, ["en"])
            
            # Verify GPT-4o was called
            mock_client.chat.completions.create.assert_called_once()
            
            # Verify result contains enhanced text
            assert lines[0]["name"] == "Enhanced Text"
            # Check if the cell was processed with GPT-4o
            assert lines[0]["cells"][0].get("used_gpt4o", False) is True


@pytest.mark.asyncio
async def test_process_cell_with_gpt4o_no_client(sample_image_bytes):
    """Test handling no OpenAI client when processing cell with GPT-4o."""
    with patch("app.ocr_pipeline.get_ocr_client", return_value=None):
        # Initialize pipeline
        pipeline = OCRPipeline()
        
        # Create test cell
        cells = [
            {
                "bbox": [0, 0, 100, 30],
                "image": sample_image_bytes,
                "structure": {"text": "Product"}
            }
        ]
        
        # Process cell with GPT-4o (should handle no client)
        # We'll use a low confidence PaddleOCR result to trigger GPT-4o
        with patch.object(pipeline.paddle_ocr, "ocr", return_value=[
            [((0, 0, 100, 30), ("Low Confidence", 0.2))]
        ]):
            lines = await pipeline._process_cells(cells, ["en"])
            
            # Verify we got results
            assert len(lines) > 0
            # The OCR result should still be used despite GPT-4o failing
            assert lines[0]["name"] == "Low Confidence"


@pytest.mark.asyncio
async def test_process_cell_with_gpt4o_invalid_client(sample_image_bytes):
    """Test handling invalid OpenAI client when processing cell with GPT-4o."""
    # Mock invalid client (no chat attribute)
    mock_client = MagicMock(spec=[])
    
    with patch("app.ocr_pipeline.get_ocr_client", return_value=mock_client):
        # Initialize pipeline
        pipeline = OCRPipeline()
        
        # Create test cell
        cells = [
            {
                "bbox": [0, 0, 100, 30],
                "image": sample_image_bytes,
                "structure": {"text": "Product"}
            }
        ]
        
        # Process with a low confidence result to trigger GPT-4o
        with patch.object(pipeline.paddle_ocr, "ocr", return_value=[
            [((0, 0, 100, 30), ("Low Confidence", 0.2))]
        ]):
            lines = await pipeline._process_cells(cells, ["en"])
            
            # Verify we got results
            assert len(lines) > 0
            # The OCR result should still be used despite GPT-4o failing
            assert lines[0]["name"] == "Low Confidence"


@pytest.mark.asyncio
async def test_process_cell_with_gpt4o_api_error(sample_image_bytes):
    """Test handling API error when processing cell with GPT-4o."""
    # Mock OpenAI client that raises exception
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = Exception("API Error")
    
    with patch("app.ocr_pipeline.get_ocr_client", return_value=mock_client):
        # Initialize pipeline
        pipeline = OCRPipeline()
        
        # Create test cell
        cells = [
            {
                "bbox": [0, 0, 100, 30],
                "image": sample_image_bytes,
                "structure": {"text": "Product"}
            }
        ]
        
        # Process with a low confidence result to trigger GPT-4o
        with patch.object(pipeline.paddle_ocr, "ocr", return_value=[
            [((0, 0, 100, 30), ("Low Confidence", 0.2))]
        ]):
            lines = await pipeline._process_cells(cells, ["en"])
            
            # Verify API call was attempted
            mock_client.chat.completions.create.assert_called_once()
            
            # Verify we got results
            assert len(lines) > 0
            # The OCR result should still be used despite GPT-4o failing
            assert lines[0]["name"] == "Low Confidence"