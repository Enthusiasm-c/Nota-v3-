"""Tests for app/ocr_helpers.py"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
import base64
import numpy as np
from PIL import Image
import io

from app.ocr_helpers import (
    parse_numeric_value,
    process_cell_with_gpt4o,
    prepare_cell_image,
    build_lines_from_cells
)


class TestParseNumericValue:
    """Test parse_numeric_value function"""
    
    def test_parse_simple_integer(self):
        """Test parsing simple integers"""
        assert parse_numeric_value("100") == 100
        assert parse_numeric_value("1000") == 1000
        assert parse_numeric_value("0") == 0
    
    def test_parse_simple_float(self):
        """Test parsing simple floats"""
        assert parse_numeric_value("100.5", is_float=True) == 100.5
        assert parse_numeric_value("1000.99", is_float=True) == 1000.99
        assert parse_numeric_value("0.1", is_float=True) == 0.1
    
    def test_parse_american_format(self):
        """Test parsing American number format (1,000.50)"""
        assert parse_numeric_value("1,000") == 1000
        assert parse_numeric_value("1,000,000") == 1000000
        assert parse_numeric_value("1,000.50", is_float=True) == 1000.5
    
    def test_parse_european_format(self):
        """Test parsing European number format (1.000,50)"""
        assert parse_numeric_value("1.000") == 1000
        assert parse_numeric_value("1.000.000") == 1000000
        assert parse_numeric_value("10.000,00", is_float=True) == 10000.0
    
    def test_parse_with_currency_symbols(self):
        """Test parsing numbers with currency symbols"""
        assert parse_numeric_value("$100") == 100
        assert parse_numeric_value("€1,000") == 1000
        assert parse_numeric_value("Rp 10.000") == 10000
        assert parse_numeric_value("р.100") == 100
    
    def test_parse_with_k_for_thousands(self):
        """Test parsing numbers with K for thousands"""
        assert parse_numeric_value("10k") == 10000
        assert parse_numeric_value("1.5K", is_float=True) == 1500.0
        assert parse_numeric_value("100K") == 100000
    
    def test_parse_with_spaces(self):
        """Test parsing numbers with spaces as separators"""
        assert parse_numeric_value("1 000") == 1000
        assert parse_numeric_value("10 000 000") == 10000000
    
    def test_parse_invalid_input(self):
        """Test parsing invalid inputs returns default"""
        assert parse_numeric_value(None) == 0
        assert parse_numeric_value("") == 0
        assert parse_numeric_value("abc") == 0
        assert parse_numeric_value("invalid", default=100) == 100
    
    def test_parse_edge_cases(self):
        """Test edge cases and special formats"""
        # Test special cases from the function
        assert parse_numeric_value("1.000", is_float=False) == 1000
        assert parse_numeric_value("Rp 10.000") == 10000
        assert parse_numeric_value("10.000,00", is_float=True) == 10000.0
        assert parse_numeric_value("1,000.50", is_float=True) == 1000.5
    
    def test_parse_decimal_detection(self):
        """Test correct detection of decimal vs thousand separator"""
        # Comma as decimal separator (European)
        assert parse_numeric_value("10,50", is_float=True) == 10.5
        # Comma as thousand separator
        assert parse_numeric_value("10,000") == 10000
        # Period as decimal separator
        assert parse_numeric_value("10.50", is_float=True) == 10.5
        # Period as thousand separator (European)
        assert parse_numeric_value("10.000", is_float=False) == 10000


class TestProcessCellWithGpt4o:
    """Test process_cell_with_gpt4o function"""
    
    @pytest.mark.asyncio
    @patch('app.ocr_helpers.get_ocr_client')
    async def test_successful_ocr(self, mock_get_client):
        """Test successful OCR with GPT-4o"""
        # Setup mock client
        mock_client = Mock()
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content="Test Text"))]
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_get_client.return_value = mock_client
        
        # Test
        text, confidence = await process_cell_with_gpt4o(b"test_image_data")
        
        assert text == "Test Text"
        assert confidence == 1.0
        
        # Verify API call
        mock_client.chat.completions.create.assert_called_once()
        call_args = mock_client.chat.completions.create.call_args
        assert call_args.kwargs['model'] == 'gpt-4o'
        assert call_args.kwargs['temperature'] == 0.0
    
    @pytest.mark.asyncio
    @patch('app.ocr_helpers.get_ocr_client')
    async def test_no_client_available(self, mock_get_client):
        """Test when no OCR client is available"""
        mock_get_client.return_value = None
        
        text, confidence = await process_cell_with_gpt4o(b"test_image_data")
        
        assert text == ""
        assert confidence == 0.0
    
    @pytest.mark.asyncio
    @patch('app.ocr_helpers.get_ocr_client')
    async def test_client_without_chat_attribute(self, mock_get_client):
        """Test when client doesn't have chat attribute"""
        mock_client = Mock(spec=[])  # No attributes
        mock_get_client.return_value = mock_client
        
        text, confidence = await process_cell_with_gpt4o(b"test_image_data")
        
        assert text == ""
        assert confidence == 0.0
    
    @pytest.mark.asyncio
    @patch('app.ocr_helpers.get_ocr_client')
    async def test_api_error(self, mock_get_client):
        """Test handling of API errors"""
        mock_client = Mock()
        mock_client.chat.completions.create = AsyncMock(side_effect=Exception("API Error"))
        mock_get_client.return_value = mock_client
        
        text, confidence = await process_cell_with_gpt4o(b"test_image_data")
        
        assert text == ""
        assert confidence == 0.0
    
    @pytest.mark.asyncio
    @patch('app.ocr_helpers.get_ocr_client')
    async def test_base64_encoding(self, mock_get_client):
        """Test that image is properly base64 encoded"""
        mock_client = Mock()
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content="Text"))]
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_get_client.return_value = mock_client
        
        test_image = b"test_image_data"
        await process_cell_with_gpt4o(test_image)
        
        # Check that base64 encoding was used
        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs['messages']
        image_url = messages[1]['content'][1]['image_url']['url']
        
        expected_b64 = base64.b64encode(test_image).decode('utf-8')
        assert f"data:image/jpeg;base64,{expected_b64}" == image_url


class TestPrepareCellImage:
    """Test prepare_cell_image function"""
    
    def test_prepare_test_image(self):
        """Test preparing test image placeholder"""
        result = prepare_cell_image(b"test_image_data")
        
        assert isinstance(result, np.ndarray)
        assert result.shape == (20, 50, 3)  # Height, Width, Channels
    
    def test_prepare_real_image(self):
        """Test preparing real image bytes"""
        # Create a test image
        img = Image.new('RGB', (100, 50), color='white')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes = img_bytes.getvalue()
        
        result = prepare_cell_image(img_bytes)
        
        assert isinstance(result, np.ndarray)
        assert result.shape == (50, 100, 3)  # Height, Width, Channels
    
    def test_prepare_too_small_image(self):
        """Test that too small images return None"""
        # Create a tiny image
        img = Image.new('RGB', (5, 5), color='white')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes = img_bytes.getvalue()
        
        result = prepare_cell_image(img_bytes)
        
        assert result is None
    
    def test_prepare_invalid_image(self):
        """Test handling of invalid image data"""
        result = prepare_cell_image(b"invalid_image_data")
        
        assert result is None
    
    def test_prepare_different_formats(self):
        """Test preparing images in different formats"""
        formats = ['PNG', 'JPEG', 'BMP']
        
        for fmt in formats:
            img = Image.new('RGB', (100, 50), color='white')
            img_bytes = io.BytesIO()
            img.save(img_bytes, format=fmt)
            img_bytes = img_bytes.getvalue()
            
            result = prepare_cell_image(img_bytes)
            
            assert isinstance(result, np.ndarray)
            assert result.shape == (50, 100, 3)


class TestBuildLinesFromCells:
    """Test build_lines_from_cells function"""
    
    def test_build_lines_empty(self):
        """Test building lines from empty cells"""
        result = build_lines_from_cells([])
        assert result == []
    
    def test_build_lines_single_row(self):
        """Test building lines from single row"""
        cells = [
            {'text': 'Product', 'bbox': [10, 10, 50, 30], 'confidence': 0.9},
            {'text': '5', 'bbox': [60, 10, 80, 30], 'confidence': 0.9},
            {'text': 'pcs', 'bbox': [90, 10, 110, 30], 'confidence': 0.9},
            {'text': '100', 'bbox': [120, 10, 140, 30], 'confidence': 0.9},
            {'text': '500', 'bbox': [150, 10, 170, 30], 'confidence': 0.9}
        ]
        
        result = build_lines_from_cells(cells)
        
        assert len(result) == 1
        assert result[0]['name'] == 'Product'
        assert result[0]['qty'] == 5
        assert result[0]['unit'] == 'pcs'
        assert result[0]['price'] == 100
        assert result[0]['amount'] == 500
    
    def test_build_lines_multiple_rows(self):
        """Test building lines from multiple rows"""
        cells = [
            # Row 1
            {'text': 'Product A', 'bbox': [10, 10, 50, 30], 'confidence': 0.9},
            {'text': '5', 'bbox': [60, 12, 80, 32], 'confidence': 0.9},
            {'text': 'pcs', 'bbox': [90, 8, 110, 28], 'confidence': 0.9},
            {'text': '100', 'bbox': [120, 11, 140, 31], 'confidence': 0.9},
            {'text': '500', 'bbox': [150, 13, 170, 33], 'confidence': 0.9},
            # Row 2
            {'text': 'Product B', 'bbox': [10, 60, 50, 80], 'confidence': 0.8},
            {'text': '2', 'bbox': [60, 58, 80, 78], 'confidence': 0.8},
            {'text': 'kg', 'bbox': [90, 62, 110, 82], 'confidence': 0.8},
            {'text': '200', 'bbox': [120, 59, 140, 79], 'confidence': 0.8},
            {'text': '400', 'bbox': [150, 61, 170, 81], 'confidence': 0.8}
        ]
        
        result = build_lines_from_cells(cells)
        
        assert len(result) == 2
        assert result[0]['name'] == 'Product A'
        assert result[0]['qty'] == 5
        assert result[1]['name'] == 'Product B'
        assert result[1]['qty'] == 2
    
    def test_build_lines_missing_cells(self):
        """Test building lines with missing cells"""
        cells = [
            {'text': 'Product', 'bbox': [10, 10, 50, 30], 'confidence': 0.9},
            {'text': '5', 'bbox': [60, 10, 80, 30], 'confidence': 0.9}
            # Missing unit, price, amount cells
        ]
        
        result = build_lines_from_cells(cells)
        
        assert len(result) == 1
        assert result[0]['name'] == 'Product'
        assert result[0]['qty'] == 5
        assert result[0]['unit'] == 'pcs'  # Default
        assert result[0]['price'] == 0  # Default
        assert result[0]['amount'] == 0  # Default
    
    def test_build_lines_with_gpt4o_flag(self):
        """Test that used_gpt4o flag is preserved"""
        cells = [
            {'text': 'Product', 'bbox': [10, 10, 50, 30], 'confidence': 0.9, 'used_gpt4o': True},
            {'text': '5', 'bbox': [60, 10, 80, 30], 'confidence': 0.9, 'used_gpt4o': False}
        ]
        
        result = build_lines_from_cells(cells)
        
        assert result[0]['cells'][0]['used_gpt4o'] == True
        assert result[0]['cells'][1]['used_gpt4o'] == False
    
    def test_build_lines_row_tolerance(self):
        """Test row grouping with tolerance"""
        cells = [
            # Cells at slightly different y positions should be in same row
            {'text': 'A', 'bbox': [10, 10, 30, 30], 'confidence': 0.9},
            {'text': 'B', 'bbox': [40, 15, 60, 35], 'confidence': 0.9},  # y=15, within tolerance
            {'text': 'C', 'bbox': [70, 25, 90, 45], 'confidence': 0.9},  # y=25, within tolerance
            # Next row
            {'text': 'D', 'bbox': [10, 50, 30, 70], 'confidence': 0.9}
        ]
        
        result = build_lines_from_cells(cells)
        
        # Should have 2 rows: ABC and D
        assert len(result) == 2
        assert len(result[0]['cells']) == 3
        assert len(result[1]['cells']) == 1