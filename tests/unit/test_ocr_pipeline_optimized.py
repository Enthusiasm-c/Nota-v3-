"""
Unit tests for optimized OCR pipeline.
"""

import io
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

# Add app directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from app.ocr_pipeline_optimized import OCRPipelineOptimized


# Helper function for creating test images
def create_test_image(width, height, text=None):
    """Create a test image with optional text."""
    from PIL import ImageDraw, ImageFont

    image = Image.new("RGB", (width, height), color=(255, 255, 255))
    if text:
        try:
            draw = ImageDraw.Draw(image)
            try:
                font = ImageFont.truetype("Arial", 12)
            except OSError:
                font = ImageFont.load_default()
            draw.text((10, 10), text, fill=(0, 0, 0), font=font)
        except Exception:
            # Fallback if text drawing fails
            pass
    img_byte_arr = io.BytesIO()
    image.save(img_byte_arr, format="JPEG")
    return img_byte_arr.getvalue()


# Sample data
@pytest.fixture
def sample_cells():
    """Sample cells for testing."""
    return [
        {"bbox": [10, 10, 100, 30], "image": create_test_image(90, 20, "Product A")},
        {"bbox": [110, 10, 150, 30], "image": create_test_image(40, 20, "5")},
        {"bbox": [160, 10, 200, 30], "image": create_test_image(40, 20, "pcs")},
        {"bbox": [210, 10, 250, 30], "image": create_test_image(40, 20, "100")},
        {"bbox": [260, 10, 300, 30], "image": create_test_image(40, 20, "500")},
        {"bbox": [10, 60, 100, 80], "image": create_test_image(90, 20, "Product B")},
        {"bbox": [110, 60, 150, 80], "image": create_test_image(40, 20, "2")},
        {"bbox": [160, 60, 200, 80], "image": create_test_image(40, 20, "kg")},
        {"bbox": [210, 60, 250, 80], "image": create_test_image(40, 20, "200")},
        {"bbox": [260, 60, 300, 80], "image": create_test_image(40, 20, "400")},
    ]


@pytest.fixture
def mock_paddle_ocr_result():
    """Mock PaddleOCR result."""
    return [[[[[0, 0], [0, 0], [0, 0], [0, 0]], ["Product A", 0.98]]]]


@pytest.fixture
def mock_vision_result():
    """Mock OpenAI Vision API result."""
    return json.dumps(
        {
            "lines": [
                {"name": "Product A", "qty": 5, "unit": "pcs", "price": 100, "amount": 500},
                {"name": "Product B", "qty": 2, "unit": "kg", "price": 200, "amount": 400},
            ]
        }
    )


@pytest.mark.asyncio
async def test_ocr_pipeline_init():
    """Test OCR pipeline initialization."""
    with patch("app.ocr_pipeline_optimized.get_detector") as mock_get_detector, patch(
        "app.ocr_pipeline_optimized.PaddleOCR"
    ) as mock_paddle_ocr:
        pipeline = OCRPipelineOptimized(table_detector_method="paddle", paddle_ocr_lang="en")

        assert pipeline.low_conf_threshold == 0.75
        assert pipeline.fallback_to_vision is True
        mock_get_detector.assert_called_once_with(method="paddle")
        mock_paddle_ocr.assert_called_once()


@pytest.mark.asyncio
async def test_ocr_cell_with_paddle(mock_paddle_ocr_result):
    """Test processing a single cell with PaddleOCR."""
    with patch("app.ocr_pipeline_optimized.PaddleOCR") as mock_paddle_class:
        mock_paddle = MagicMock()
        mock_paddle.ocr.return_value = mock_paddle_ocr_result
        mock_paddle_class.return_value = mock_paddle

        pipeline = OCRPipelineOptimized()
        cell = {"bbox": [10, 10, 100, 30], "image": create_test_image(90, 20, "Product A")}

        result = await pipeline._ocr_cell(cell)

        assert result["text"] == "Product A"
        assert result["confidence"] == 0.98
        assert result["used_gpt4o"] is False


@pytest.mark.asyncio
async def test_ocr_cell_with_gpt4o():
    """Test processing a cell with GPT-4o when confidence is low."""
    with patch("app.ocr_pipeline_optimized.PaddleOCR") as mock_paddle_class, patch(
        "app.ocr_pipeline_optimized.process_cell_with_gpt4o"
    ) as mock_gpt4o:
        mock_paddle = MagicMock()
        # Low confidence result from PaddleOCR
        mock_paddle.ocr.return_value = [[[[[0, 0], [0, 0], [0, 0], [0, 0]], ["Product?", 0.3]]]]
        mock_paddle_class.return_value = mock_paddle

        # Mock GPT-4o response
        mock_gpt4o.return_value = ("Product A", 1.0)

        pipeline = OCRPipelineOptimized()
        cell = {"bbox": [10, 10, 100, 30], "image": create_test_image(90, 20, "Product A")}

        result = await pipeline._ocr_cell(cell)

        assert result["text"] == "Product A"
        assert result["confidence"] == 1.0
        assert result["used_gpt4o"] is True
        mock_gpt4o.assert_called_once()


@pytest.mark.asyncio
async def test_process_cells(sample_cells):
    """Test processing multiple cells in parallel."""
    with patch("app.ocr_pipeline_optimized.OCRPipelineOptimized._ocr_cell") as mock_ocr_cell:
        # Set up mock responses for each cell
        async def mock_ocr_response(cell):
            idx = sample_cells.index(cell) if cell in sample_cells else -1
            if idx == 0:
                return {**cell, "text": "Product A", "confidence": 0.98, "used_gpt4o": False}
            elif idx == 1:
                return {**cell, "text": "5", "confidence": 0.95, "used_gpt4o": False}
            elif idx == 2:
                return {**cell, "text": "pcs", "confidence": 0.9, "used_gpt4o": False}
            elif idx == 3:
                return {**cell, "text": "100", "confidence": 0.95, "used_gpt4o": False}
            elif idx == 4:
                return {**cell, "text": "500", "confidence": 0.95, "used_gpt4o": False}
            elif idx == 5:
                return {**cell, "text": "Product B", "confidence": 0.8, "used_gpt4o": True}
            elif idx == 6:
                return {**cell, "text": "2", "confidence": 0.95, "used_gpt4o": False}
            elif idx == 7:
                return {**cell, "text": "kg", "confidence": 0.9, "used_gpt4o": False}
            elif idx == 8:
                return {**cell, "text": "200", "confidence": 0.95, "used_gpt4o": False}
            elif idx == 9:
                return {**cell, "text": "400", "confidence": 0.95, "used_gpt4o": False}
            else:
                return {**cell, "text": "", "confidence": 0.0, "used_gpt4o": False}

        mock_ocr_cell.side_effect = mock_ocr_response

        pipeline = OCRPipelineOptimized()
        lines = await pipeline._process_cells(sample_cells, ["en"])

        # Should have 2 lines based on our sample cells
        assert len(lines) == 2

        # Verify line content
        assert lines[0]["name"] == "Product A"
        assert lines[0]["qty"] == 5
        assert lines[0]["unit"] == "pcs"
        assert lines[0]["price"] == 100
        assert lines[0]["amount"] == 500

        assert lines[1]["name"] == "Product B"
        assert lines[1]["qty"] == 2
        assert lines[1]["unit"] == "kg"
        assert lines[1]["price"] == 200
        assert lines[1]["amount"] == 400

        # Check GPT-4o metrics
        assert pipeline._metrics["gpt4o_count"] == 1
        assert pipeline._metrics["gpt4o_percent"] == 10.0
        assert pipeline._metrics["total_cells"] == 10


@pytest.mark.asyncio
async def test_process_with_openai_vision(mock_vision_result):
    """Test fallback to OpenAI Vision API."""
    with patch("app.ocr_pipeline_optimized.call_openai_ocr_async") as mock_call_vision:
        mock_call_vision.return_value = mock_vision_result

        pipeline = OCRPipelineOptimized()
        result = await pipeline._process_with_openai_vision(b"test_image", ["en"])

        assert result["status"] == "success"
        assert len(result["lines"]) == 2
        assert result["lines"][0]["name"] == "Product A"
        assert result["lines"][1]["name"] == "Product B"
        assert result["accuracy"] == 0.9  # OpenAI Vision accuracy


@pytest.mark.asyncio
async def test_process_image_happy_path(sample_cells, mock_vision_result):
    """Test complete image processing - happy path."""
    with patch("app.ocr_pipeline_optimized.get_detector") as mock_get_detector, patch(
        "app.ocr_pipeline_optimized.OCRPipelineOptimized._process_cells"
    ) as mock_process_cells, patch(
        "app.ocr_pipeline_optimized.ValidationPipeline.validate"
    ) as mock_validate, patch(
        "app.ocr_pipeline_optimized.cache_get"
    ) as mock_cache_get, patch(
        "app.ocr_pipeline_optimized.cache_set"
    ) as mock_cache_set, patch(
        "app.ocr_pipeline_optimized.prepare_for_ocr"
    ) as mock_prepare:

        # Mock detector
        mock_detector = MagicMock()
        mock_detector.detect.return_value = {"table_data": "mock"}
        mock_detector.extract_cells.return_value = sample_cells
        mock_get_detector.return_value = mock_detector

        # Mock cell processing
        expected_lines = [
            {"name": "Product A", "qty": 5, "unit": "pcs", "price": 100, "amount": 500},
            {"name": "Product B", "qty": 2, "unit": "kg", "price": 200, "amount": 400},
        ]
        mock_process_cells.return_value = expected_lines

        # Mock validation
        mock_validate.return_value = {
            "status": "success",
            "lines": expected_lines,
            "accuracy": 0.9,
            "issues": [],
        }

        # Mock cache - no cache hit
        mock_cache_get.return_value = None

        # Mock image preparation
        mock_prepare.return_value = b"optimized_image"

        pipeline = OCRPipelineOptimized()
        result = await pipeline.process_image(b"test_image", ["en"])

        assert result["status"] == "success"
        assert "lines" in result
        assert "timing" in result
        assert "total_time" in result
        mock_detector.detect.assert_called_once()
        mock_detector.extract_cells.assert_called_once()
        mock_process_cells.assert_called_once()
        mock_validate.assert_called_once()
        mock_cache_set.assert_called_once()


@pytest.mark.asyncio
async def test_process_image_cache_hit():
    """Test cache hit during image processing."""
    with patch("app.ocr_pipeline_optimized.cache_get") as mock_cache_get:
        # Mock cache hit
        expected_result = {
            "status": "success",
            "lines": [
                {"name": "Product A", "qty": 5, "unit": "pcs", "price": 100, "amount": 500},
                {"name": "Product B", "qty": 2, "unit": "kg", "price": 200, "amount": 400},
            ],
            "accuracy": 0.9,
            "issues": [],
        }
        mock_cache_get.return_value = expected_result

        pipeline = OCRPipelineOptimized()
        result = await pipeline.process_image(b"test_image", ["en"])

        assert result == expected_result
        mock_cache_get.assert_called_once()
        assert pipeline._metrics["cache_hits"] == 1


@pytest.mark.asyncio
async def test_process_image_table_detection_error():
    """Test fallback to Vision API when table detection fails."""
    with patch("app.ocr_pipeline_optimized.get_detector") as mock_get_detector, patch(
        "app.ocr_pipeline_optimized.OCRPipelineOptimized._process_with_openai_vision"
    ) as mock_vision, patch(
        "app.ocr_pipeline_optimized.ValidationPipeline.validate"
    ) as mock_validate, patch(
        "app.ocr_pipeline_optimized.cache_get"
    ) as mock_cache_get:

        # Mock cache miss
        mock_cache_get.return_value = None

        # Mock detector that raises an error
        mock_detector = MagicMock()
        mock_detector.detect.side_effect = Exception("Table detection error")
        mock_get_detector.return_value = mock_detector

        # Mock Vision API response
        expected_lines = [
            {"name": "Product A", "qty": 5, "unit": "pcs", "price": 100, "amount": 500},
            {"name": "Product B", "qty": 2, "unit": "kg", "price": 200, "amount": 400},
        ]
        mock_vision.return_value = {
            "status": "success",
            "lines": expected_lines,
            "accuracy": 0.9,
            "issues": [],
        }

        # Mock validation
        mock_validate.return_value = {
            "status": "success",
            "lines": expected_lines,
            "accuracy": 0.9,
            "issues": [],
        }

        pipeline = OCRPipelineOptimized()
        result = await pipeline.process_image(b"test_image", ["en"])

        assert result["status"] == "success"
        assert "used_fallback" in result
        assert result["used_fallback"] is True
        mock_detector.detect.assert_called_once()
        mock_vision.assert_called_once()
        mock_validate.assert_called_once()


@pytest.mark.asyncio
async def test_process_image_disable_fallback():
    """Test error when table detection fails and fallback is disabled."""
    with patch("app.ocr_pipeline_optimized.get_detector") as mock_get_detector, patch(
        "app.ocr_pipeline_optimized.cache_get"
    ) as mock_cache_get:

        # Mock cache miss
        mock_cache_get.return_value = None

        # Mock detector that raises an error
        mock_detector = MagicMock()
        mock_detector.detect.side_effect = Exception("Table detection error")
        mock_get_detector.return_value = mock_detector

        pipeline = OCRPipelineOptimized(fallback_to_vision=False)
        result = await pipeline.process_image(b"test_image", ["en"])

        assert result["status"] == "error"
        assert "message" in result
        assert "Table detection failed" in result["message"]
        mock_detector.detect.assert_called_once()


if __name__ == "__main__":
    pytest.main(["-xvs", __file__])
