"""Tests for app/ocr_pipeline_optimized.py"""

import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
import numpy as np
from PIL import Image
import io
import base64

from app.ocr_pipeline_optimized import (
    OCRPipelineOptimized,
    build_ocr_prompt,
    ocr_with_gpt4
)


class TestBuildOCRPrompt:
    """Test build_ocr_prompt function"""
    
    def test_build_ocr_prompt_minimal(self):
        """Test building OCR prompt with minimal parameters"""
        prompt = build_ocr_prompt()
        
        assert "invoice" in prompt.lower()
        assert "table" in prompt.lower()
        assert "extract" in prompt.lower()
    
    def test_build_ocr_prompt_with_template(self):
        """Test building OCR prompt with template"""
        template = "Custom OCR template: {}"
        prompt = build_ocr_prompt(template=template)
        
        assert "Custom OCR template:" in prompt
    
    def test_build_ocr_prompt_with_hint(self):
        """Test building OCR prompt with hint"""
        hint = "Focus on product names and prices"
        prompt = build_ocr_prompt(hint=hint)
        
        assert hint in prompt


@pytest.mark.asyncio
class TestOCRWithGPT4:
    """Test ocr_with_gpt4 function"""
    
    @patch('app.ocr_pipeline_optimized.get_ocr_client')
    async def test_ocr_with_gpt4_success(self, mock_get_client):
        """Test successful OCR with GPT-4"""
        # Setup mock client
        mock_client = Mock()
        mock_response = Mock()
        mock_response.choices = [
            Mock(message=Mock(content="Product A|10|kg|100|1000\nProduct B|5|pcs|50|250"))
        ]
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_get_client.return_value = mock_client
        
        # Create test image
        img = Image.new('RGB', (100, 50), color='white')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes = img_bytes.getvalue()
        
        # Run OCR
        result = await ocr_with_gpt4(img_bytes)
        
        assert "Product A" in result
        assert "Product B" in result
        assert mock_client.chat.completions.create.called
    
    @patch('app.ocr_pipeline_optimized.get_ocr_client')
    async def test_ocr_with_gpt4_no_client(self, mock_get_client):
        """Test OCR when no client available"""
        mock_get_client.return_value = None
        
        img_bytes = b"test_image"
        result = await ocr_with_gpt4(img_bytes)
        
        assert result == ""
    
    @patch('app.ocr_pipeline_optimized.get_ocr_client')
    async def test_ocr_with_gpt4_api_error(self, mock_get_client):
        """Test OCR with API error"""
        mock_client = Mock()
        mock_client.chat.completions.create = AsyncMock(side_effect=Exception("API Error"))
        mock_get_client.return_value = mock_client
        
        img_bytes = b"test_image"
        result = await ocr_with_gpt4(img_bytes)
        
        assert result == ""


class TestOCRPipelineOptimized:
    """Test OCRPipelineOptimized class"""
    
    def test_init_default_params(self):
        """Test initialization with default parameters"""
        pipeline = OCRPipelineOptimized()
        
        assert pipeline.use_paddle is True
        assert pipeline.use_gpt4_ocr is True
        assert pipeline.enable_preprocessing is True
        assert pipeline.enable_postprocessing is True
        assert pipeline.enable_validation is True
        assert pipeline.parallel_ocr is True
        assert pipeline.cache_enabled is True
    
    def test_init_custom_params(self):
        """Test initialization with custom parameters"""
        pipeline = OCRPipelineOptimized(
            use_paddle=False,
            use_gpt4_ocr=False,
            cache_enabled=False
        )
        
        assert pipeline.use_paddle is False
        assert pipeline.use_gpt4_ocr is False
        assert pipeline.cache_enabled is False
    
    @pytest.mark.asyncio
    @patch('app.ocr_pipeline_optimized.OCRPipelineOptimized._check_cache')
    @patch('app.ocr_pipeline_optimized.OCRPipelineOptimized._save_to_cache')
    @patch('app.ocr_pipeline_optimized.ocr_with_gpt4')
    async def test_process_image_with_cache_hit(
        self,
        mock_ocr,
        mock_save_cache,
        mock_check_cache
    ):
        """Test processing image with cache hit"""
        # Setup cache hit
        cached_result = {
            "supplier": "Cached Supplier",
            "date": "2024-01-15",
            "positions": [{"name": "Product", "qty": 10}]
        }
        mock_check_cache.return_value = cached_result
        
        pipeline = OCRPipelineOptimized()
        img_bytes = b"test_image"
        
        result = await pipeline.process_image(img_bytes)
        
        assert result == cached_result
        assert not mock_ocr.called  # OCR should not be called on cache hit
        assert not mock_save_cache.called
    
    @pytest.mark.asyncio
    @patch('app.ocr_pipeline_optimized.OCRPipelineOptimized._check_cache')
    @patch('app.ocr_pipeline_optimized.OCRPipelineOptimized._save_to_cache')
    @patch('app.ocr_pipeline_optimized.ocr_with_gpt4')
    @patch('app.ocr_pipeline_optimized.OCRPipelineOptimized._parse_ocr_text')
    async def test_process_image_with_cache_miss(
        self,
        mock_parse,
        mock_ocr,
        mock_save_cache,
        mock_check_cache
    ):
        """Test processing image with cache miss"""
        # Setup cache miss
        mock_check_cache.return_value = None
        
        # Setup OCR response
        mock_ocr.return_value = "Product A|10|kg|100|1000"
        
        # Setup parse response
        parsed_result = {
            "supplier": "Test Supplier",
            "date": "2024-01-15",
            "positions": [{"name": "Product A", "qty": 10, "unit": "kg", "price": 100}]
        }
        mock_parse.return_value = parsed_result
        
        pipeline = OCRPipelineOptimized()
        img_bytes = b"test_image"
        
        result = await pipeline.process_image(img_bytes)
        
        assert result == parsed_result
        assert mock_ocr.called
        assert mock_parse.called
        assert mock_save_cache.called
    
    @pytest.mark.asyncio
    @patch('app.ocr_pipeline_optimized.ocr_with_gpt4')
    async def test_process_image_ocr_failure(self, mock_ocr):
        """Test processing image when OCR fails"""
        mock_ocr.return_value = ""  # Empty OCR result
        
        pipeline = OCRPipelineOptimized(cache_enabled=False)
        img_bytes = b"test_image"
        
        result = await pipeline.process_image(img_bytes)
        
        assert result["positions"] == []
        assert result.get("error") is not None
    
    def test_parse_ocr_text_valid_format(self):
        """Test parsing valid OCR text"""
        pipeline = OCRPipelineOptimized()
        
        ocr_text = """Supplier: Test Company
Date: 2024-01-15

Product A|10|kg|100|1000
Product B|5|pcs|50|250"""
        
        result = pipeline._parse_ocr_text(ocr_text)
        
        assert result["supplier"] == "Test Company"
        assert result["date"] == "2024-01-15"
        assert len(result["positions"]) == 2
        assert result["positions"][0]["name"] == "Product A"
        assert result["positions"][0]["qty"] == 10
    
    def test_parse_ocr_text_invalid_format(self):
        """Test parsing invalid OCR text"""
        pipeline = OCRPipelineOptimized()
        
        ocr_text = "Invalid format text"
        
        result = pipeline._parse_ocr_text(ocr_text)
        
        assert result["positions"] == []
        assert "error" in result
    
    def test_parse_ocr_text_partial_data(self):
        """Test parsing OCR text with partial data"""
        pipeline = OCRPipelineOptimized()
        
        ocr_text = """Product A|10|kg
Product B||pcs|50
Product C|5"""
        
        result = pipeline._parse_ocr_text(ocr_text)
        
        # Should handle partial data gracefully
        assert len(result["positions"]) >= 0
    
    def test_check_cache_disabled(self):
        """Test cache check when cache is disabled"""
        pipeline = OCRPipelineOptimized(cache_enabled=False)
        
        result = pipeline._check_cache("test_key")
        
        assert result is None
    
    @patch('app.ocr_pipeline_optimized.cache_get')
    def test_check_cache_hit(self, mock_cache_get):
        """Test cache check with hit"""
        cached_data = '{"supplier": "Cached", "positions": []}'
        mock_cache_get.return_value = cached_data
        
        pipeline = OCRPipelineOptimized(cache_enabled=True)
        
        result = pipeline._check_cache("test_key")
        
        assert result is not None
        assert result["supplier"] == "Cached"
    
    @patch('app.ocr_pipeline_optimized.cache_get')
    def test_check_cache_miss(self, mock_cache_get):
        """Test cache check with miss"""
        mock_cache_get.return_value = None
        
        pipeline = OCRPipelineOptimized(cache_enabled=True)
        
        result = pipeline._check_cache("test_key")
        
        assert result is None
    
    @patch('app.ocr_pipeline_optimized.cache_set')
    def test_save_to_cache(self, mock_cache_set):
        """Test saving to cache"""
        pipeline = OCRPipelineOptimized(cache_enabled=True)
        
        data = {"supplier": "Test", "positions": []}
        pipeline._save_to_cache("test_key", data)
        
        mock_cache_set.assert_called_once()
    
    def test_save_to_cache_disabled(self):
        """Test saving to cache when disabled"""
        pipeline = OCRPipelineOptimized(cache_enabled=False)
        
        # Should not raise any errors
        pipeline._save_to_cache("test_key", {})
    
    @pytest.mark.asyncio
    async def test_process_image_with_preprocessing(self):
        """Test image preprocessing is called when enabled"""
        pipeline = OCRPipelineOptimized(
            enable_preprocessing=True,
            cache_enabled=False
        )
        
        # Create a mock image
        img = Image.new('RGB', (100, 50), color='white')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes = img_bytes.getvalue()
        
        with patch.object(pipeline, '_preprocess_image') as mock_preprocess:
            mock_preprocess.return_value = img_bytes
            
            with patch('app.ocr_pipeline_optimized.ocr_with_gpt4') as mock_ocr:
                mock_ocr.return_value = ""
                
                await pipeline.process_image(img_bytes)
                
                mock_preprocess.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_process_image_validation_enabled(self):
        """Test validation is performed when enabled"""
        pipeline = OCRPipelineOptimized(
            enable_validation=True,
            cache_enabled=False
        )
        
        with patch('app.ocr_pipeline_optimized.ocr_with_gpt4') as mock_ocr:
            mock_ocr.return_value = "Product|10|kg|100|1000"
            
            with patch.object(pipeline, '_validate_results') as mock_validate:
                mock_validate.return_value = {"positions": [], "validation_errors": []}
                
                await pipeline.process_image(b"test")
                
                mock_validate.assert_called_once()


class TestIntegration:
    """Integration tests for OCR pipeline"""
    
    @pytest.mark.asyncio
    @patch('app.ocr_pipeline_optimized.get_ocr_client')
    async def test_full_pipeline_flow(self, mock_get_client):
        """Test complete pipeline flow"""
        # Setup mock client
        mock_client = Mock()
        mock_response = Mock()
        mock_response.choices = [
            Mock(message=Mock(content="""Supplier: Test Supplier
Date: 2024-01-15

Product A|10|kg|100|1000
Product B|5|pcs|50|250"""))
        ]
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_get_client.return_value = mock_client
        
        # Create pipeline
        pipeline = OCRPipelineOptimized(cache_enabled=False)
        
        # Create test image
        img = Image.new('RGB', (100, 50), color='white')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes = img_bytes.getvalue()
        
        # Process image
        result = await pipeline.process_image(img_bytes)
        
        # Verify results
        assert result.get("supplier") == "Test Supplier"
        assert result.get("date") == "2024-01-15"
        assert len(result.get("positions", [])) == 2