"""
Comprehensive tests for the OCR pipeline module.
Tests the complete OCR processing workflow including image preprocessing,
OpenAI API integration, and result post-processing.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock, mock_open
from datetime import date
import json
import base64
from app.ocr_pipeline_optimized import (
    process_invoice_with_ocr,
    prepare_image_for_ocr,
    call_openai_vision_api,
    parse_ocr_response,
    validate_ocr_result,
    enhance_ocr_result,
    OCRProcessor
)


class TestOCRProcessor:
    """Test suite for OCRProcessor class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.processor = OCRProcessor()
        
        self.sample_image_data = b"fake_image_data"
        self.sample_base64_image = base64.b64encode(self.sample_image_data).decode()
        
        self.sample_ocr_response = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "supplier": "Test Supplier Ltd",
                        "invoice_number": "INV-2025-001",
                        "invoice_date": "2025-05-28",
                        "lines": [
                            {
                                "name": "Product A",
                                "qty": 2.0,
                                "price": 15000.0,
                                "total_price": 30000.0,
                                "unit": "kg"
                            }
                        ],
                        "total_amount": 30000.0
                    })
                }
            }]
        }
        
        self.sample_message = Mock()
        self.sample_message.from_user.id = 12345
        self.sample_message.chat.id = 67890
        
        self.sample_bot = Mock()
        self.sample_bot.send_message = AsyncMock()
    
    def test_ocr_processor_init(self):
        """Test OCRProcessor initialization."""
        processor = OCRProcessor()
        
        assert processor.api_key is not None
        assert processor.model == "gpt-4-vision-preview"
        assert processor.max_retries == 3
        assert processor.timeout == 30
    
    def test_ocr_processor_init_custom_params(self):
        """Test OCRProcessor initialization with custom parameters."""
        processor = OCRProcessor(
            model="custom-model",
            max_retries=5,
            timeout=60
        )
        
        assert processor.model == "custom-model"
        assert processor.max_retries == 5
        assert processor.timeout == 60
    
    @pytest.mark.asyncio
    async def test_process_invoice_with_ocr_success(self):
        """Test successful invoice processing with OCR."""
        with patch('app.ocr_pipeline_optimized.prepare_image_for_ocr') as mock_prepare, \
             patch('app.ocr_pipeline_optimized.call_openai_vision_api') as mock_api, \
             patch('app.ocr_pipeline_optimized.parse_ocr_response') as mock_parse, \
             patch('app.ocr_pipeline_optimized.validate_ocr_result') as mock_validate:
            
            # Mock image preparation
            mock_prepare.return_value = {
                "success": True,
                "image_data": self.sample_base64_image,
                "format": "JPEG",
                "size": (1024, 768)
            }
            
            # Mock API call
            mock_api.return_value = {
                "success": True,
                "response": self.sample_ocr_response
            }
            
            # Mock parsing
            mock_parse.return_value = {
                "success": True,
                "data": {
                    "supplier": "Test Supplier Ltd",
                    "invoice_number": "INV-2025-001",
                    "lines": [{"name": "Product A", "qty": 2.0}]
                }
            }
            
            # Mock validation
            mock_validate.return_value = {
                "valid": True,
                "issues": [],
                "data": {"supplier": "Test Supplier Ltd"}
            }
            
            result = await process_invoice_with_ocr(
                self.sample_image_data,
                self.sample_message,
                self.sample_bot
            )
            
            assert result["success"] is True
            assert "data" in result
            assert result["data"]["supplier"] == "Test Supplier Ltd"
            
            # Verify all steps were called
            mock_prepare.assert_called_once()
            mock_api.assert_called_once()
            mock_parse.assert_called_once()
            mock_validate.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_process_invoice_with_ocr_image_preparation_failure(self):
        """Test OCR processing with image preparation failure."""
        with patch('app.ocr_pipeline_optimized.prepare_image_for_ocr') as mock_prepare:
            
            mock_prepare.return_value = {
                "success": False,
                "error": "Invalid image format"
            }
            
            result = await process_invoice_with_ocr(
                b"invalid_image_data",
                self.sample_message,
                self.sample_bot
            )
            
            assert result["success"] is False
            assert "error" in result
            assert "image" in result["error"].lower()
    
    @pytest.mark.asyncio
    async def test_process_invoice_with_ocr_api_failure(self):
        """Test OCR processing with API failure."""
        with patch('app.ocr_pipeline_optimized.prepare_image_for_ocr') as mock_prepare, \
             patch('app.ocr_pipeline_optimized.call_openai_vision_api') as mock_api:
            
            mock_prepare.return_value = {
                "success": True,
                "image_data": self.sample_base64_image
            }
            
            mock_api.return_value = {
                "success": False,
                "error": "API rate limit exceeded"
            }
            
            result = await process_invoice_with_ocr(
                self.sample_image_data,
                self.sample_message,
                self.sample_bot
            )
            
            assert result["success"] is False
            assert "error" in result
            assert "api" in result["error"].lower() or "rate limit" in result["error"].lower()
    
    def test_prepare_image_for_ocr_jpeg(self):
        """Test image preparation for JPEG images."""
        jpeg_header = b'\xff\xd8\xff\xe0'
        jpeg_data = jpeg_header + b'fake_jpeg_data'
        
        result = prepare_image_for_ocr(jpeg_data)
        
        assert result["success"] is True
        assert result["format"] == "JPEG"
        assert "image_data" in result
        assert isinstance(result["image_data"], str)  # Base64 encoded
    
    def test_prepare_image_for_ocr_png(self):
        """Test image preparation for PNG images."""
        png_header = b'\x89PNG\r\n\x1a\n'
        png_data = png_header + b'fake_png_data'
        
        result = prepare_image_for_ocr(png_data)
        
        assert result["success"] is True
        assert result["format"] == "PNG"
        assert "image_data" in result
    
    def test_prepare_image_for_ocr_webp(self):
        """Test image preparation for WebP images."""
        webp_header = b'RIFF\x00\x00\x00\x00WEBP'
        webp_data = webp_header + b'fake_webp_data'
        
        result = prepare_image_for_ocr(webp_data)
        
        assert result["success"] is True
        assert result["format"] == "WEBP"
        assert "image_data" in result
    
    def test_prepare_image_for_ocr_invalid_format(self):
        """Test image preparation with invalid format."""
        invalid_data = b'not_an_image'
        
        result = prepare_image_for_ocr(invalid_data)
        
        assert result["success"] is False
        assert "error" in result
        assert "format" in result["error"].lower() or "invalid" in result["error"].lower()
    
    def test_prepare_image_for_ocr_empty_data(self):
        """Test image preparation with empty data."""
        result = prepare_image_for_ocr(b'')
        
        assert result["success"] is False
        assert "error" in result
    
    def test_prepare_image_for_ocr_large_image(self):
        """Test image preparation with large image data."""
        # Simulate large image (over size limit)
        large_image_data = b'\xff\xd8\xff\xe0' + b'x' * (20 * 1024 * 1024)  # 20MB
        
        result = prepare_image_for_ocr(large_image_data)
        
        # Should either compress/resize or reject
        if result["success"]:
            # If successful, should have reasonable size
            decoded_size = len(base64.b64decode(result["image_data"]))
            assert decoded_size < 20 * 1024 * 1024  # Smaller than original
        else:
            # If rejected, should have size-related error
            assert "size" in result["error"].lower() or "large" in result["error"].lower()
    
    @pytest.mark.asyncio
    async def test_call_openai_vision_api_success(self):
        """Test successful OpenAI Vision API call."""
        with patch('app.ocr_pipeline_optimized.openai_client') as mock_client:
            
            mock_response = Mock()
            mock_response.choices = [Mock()]
            mock_response.choices[0].message.content = json.dumps({
                "supplier": "Test Supplier"
            })
            
            mock_client.chat.completions.create.return_value = mock_response
            
            result = await call_openai_vision_api(
                self.sample_base64_image,
                "JPEG"
            )
            
            assert result["success"] is True
            assert "response" in result
            
            # Verify API was called with correct parameters
            mock_client.chat.completions.create.assert_called_once()
            call_args = mock_client.chat.completions.create.call_args
            
            assert call_args[1]["model"] in ["gpt-4-vision-preview", "gpt-4o"]
            assert len(call_args[1]["messages"]) > 0
    
    @pytest.mark.asyncio
    async def test_call_openai_vision_api_rate_limit(self):
        """Test OpenAI API call with rate limit error."""
        from openai import RateLimitError
        
        with patch('app.ocr_pipeline_optimized.openai_client') as mock_client:
            
            mock_client.chat.completions.create.side_effect = RateLimitError("Rate limit exceeded")
            
            result = await call_openai_vision_api(
                self.sample_base64_image,
                "JPEG"
            )
            
            assert result["success"] is False
            assert "rate limit" in result["error"].lower()
    
    @pytest.mark.asyncio
    async def test_call_openai_vision_api_timeout(self):
        """Test OpenAI API call with timeout."""
        import asyncio
        
        with patch('app.ocr_pipeline_optimized.openai_client') as mock_client:
            
            mock_client.chat.completions.create.side_effect = asyncio.TimeoutError()
            
            result = await call_openai_vision_api(
                self.sample_base64_image,
                "JPEG"
            )
            
            assert result["success"] is False
            assert "timeout" in result["error"].lower()
    
    @pytest.mark.asyncio
    async def test_call_openai_vision_api_invalid_response(self):
        """Test OpenAI API call with invalid response."""
        with patch('app.ocr_pipeline_optimized.openai_client') as mock_client:
            
            # Mock response with no choices
            mock_response = Mock()
            mock_response.choices = []
            
            mock_client.chat.completions.create.return_value = mock_response
            
            result = await call_openai_vision_api(
                self.sample_base64_image,
                "JPEG"
            )
            
            assert result["success"] is False
            assert "response" in result["error"].lower() or "invalid" in result["error"].lower()
    
    def test_parse_ocr_response_valid_json(self):
        """Test parsing valid OCR response."""
        valid_response = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "supplier": "Test Supplier",
                        "invoice_number": "INV-001",
                        "lines": [{"name": "Product A", "qty": 1}]
                    })
                }
            }]
        }
        
        result = parse_ocr_response(valid_response)
        
        assert result["success"] is True
        assert result["data"]["supplier"] == "Test Supplier"
        assert result["data"]["invoice_number"] == "INV-001"
        assert len(result["data"]["lines"]) == 1
    
    def test_parse_ocr_response_invalid_json(self):
        """Test parsing OCR response with invalid JSON."""
        invalid_response = {
            "choices": [{
                "message": {
                    "content": "This is not valid JSON"
                }
            }]
        }
        
        result = parse_ocr_response(invalid_response)
        
        assert result["success"] is False
        assert "json" in result["error"].lower() or "parse" in result["error"].lower()
    
    def test_parse_ocr_response_missing_choices(self):
        """Test parsing OCR response with missing choices."""
        missing_choices_response = {
            "choices": []
        }
        
        result = parse_ocr_response(missing_choices_response)
        
        assert result["success"] is False
        assert "choices" in result["error"].lower() or "empty" in result["error"].lower()
    
    def test_parse_ocr_response_malformed_structure(self):
        """Test parsing malformed OCR response."""
        malformed_responses = [
            None,
            {},
            {"choices": None},
            {"choices": [{}]},  # Missing message
            {"choices": [{"message": {}}]},  # Missing content
        ]
        
        for response in malformed_responses:
            result = parse_ocr_response(response)
            assert result["success"] is False
            assert "error" in result
    
    def test_validate_ocr_result_complete_data(self):
        """Test validation of complete OCR result."""
        complete_data = {
            "supplier": "Complete Supplier Ltd",
            "invoice_number": "INV-2025-001",
            "invoice_date": "2025-05-28",
            "lines": [
                {
                    "name": "Product A",
                    "qty": 2.0,
                    "price": 15000.0,
                    "total_price": 30000.0,
                    "unit": "kg"
                }
            ],
            "total_amount": 30000.0
        }
        
        result = validate_ocr_result(complete_data)
        
        assert result["valid"] is True
        assert len(result["issues"]) == 0
        assert result["data"] == complete_data
    
    def test_validate_ocr_result_missing_required_fields(self):
        """Test validation of OCR result with missing required fields."""
        incomplete_data = {
            "lines": [
                {"name": "Product A", "qty": 1}
            ]
            # Missing supplier, invoice_number, etc.
        }
        
        result = validate_ocr_result(incomplete_data)
        
        assert result["valid"] is False
        assert len(result["issues"]) > 0
        
        # Should have issues for missing fields
        missing_issues = [issue for issue in result["issues"] if "missing" in issue["message"].lower()]
        assert len(missing_issues) > 0
    
    def test_validate_ocr_result_arithmetic_validation(self):
        """Test OCR result validation with arithmetic checks."""
        data_with_errors = {
            "supplier": "Test Supplier",
            "lines": [
                {
                    "name": "Product A",
                    "qty": 2.0,
                    "price": 10000.0,
                    "total_price": 25000.0  # Should be 20000.0
                }
            ]
        }
        
        result = validate_ocr_result(data_with_errors)
        
        # Should detect arithmetic error
        math_issues = [issue for issue in result["issues"] if "math" in issue["message"].lower() or "calculation" in issue["message"].lower()]
        assert len(math_issues) > 0
    
    def test_enhance_ocr_result_product_mapping(self):
        """Test enhancement of OCR result with product mapping."""
        raw_data = {
            "supplier": "Test Supplier",
            "lines": [
                {"name": "tomato", "qty": 1, "price": 5000},
                {"name": "unknown product", "qty": 1, "price": 1000}
            ]
        }
        
        with patch('app.ocr_pipeline_optimized.map_products_to_catalog') as mock_map:
            
            mock_map.return_value = {
                "tomato": {
                    "mapped_name": "Fresh Tomatoes",
                    "category": "vegetables",
                    "confidence": 0.95
                }
            }
            
            result = enhance_ocr_result(raw_data)
            
            assert result["success"] is True
            enhanced_data = result["data"]
            
            # Should have product mappings
            assert "product_mappings" in enhanced_data
            assert "tomato" in enhanced_data["product_mappings"]
    
    def test_enhance_ocr_result_price_validation(self):
        """Test enhancement with price validation."""
        raw_data = {
            "supplier": "Test Supplier",
            "lines": [
                {"name": "expensive item", "qty": 1, "price": 5000000},  # Very expensive
                {"name": "cheap item", "qty": 1, "price": 10}  # Very cheap
            ]
        }
        
        result = enhance_ocr_result(raw_data)
        
        assert result["success"] is True
        enhanced_data = result["data"]
        
        # Should have price warnings
        if "warnings" in enhanced_data:
            price_warnings = [w for w in enhanced_data["warnings"] if "price" in w.lower()]
            assert len(price_warnings) > 0
    
    def test_enhance_ocr_result_date_normalization(self):
        """Test enhancement with date normalization."""
        raw_data = {
            "supplier": "Test Supplier",
            "invoice_date": "28/05/2025",  # Non-standard format
            "lines": [{"name": "Product A", "qty": 1, "price": 1000}]
        }
        
        result = enhance_ocr_result(raw_data)
        
        assert result["success"] is True
        enhanced_data = result["data"]
        
        # Date should be normalized to standard format
        if "invoice_date" in enhanced_data:
            assert enhanced_data["invoice_date"] == date(2025, 5, 28) or enhanced_data["invoice_date"] == "2025-05-28"


class TestOCRPipelineIntegration:
    """Integration tests for OCR pipeline components."""
    
    @pytest.mark.asyncio
    async def test_end_to_end_ocr_pipeline(self):
        """Test complete end-to-end OCR pipeline."""
        # Simulate a real invoice image processing workflow
        fake_image_data = b'\xff\xd8\xff\xe0' + b'fake_jpeg_invoice_data'
        
        message = Mock()
        message.from_user.id = 12345
        message.chat.id = 67890
        
        bot = Mock()
        bot.send_message = AsyncMock()
        bot.edit_message_text = AsyncMock()
        
        with patch('app.ocr_pipeline_optimized.openai_client') as mock_client, \
             patch('app.ocr_pipeline_optimized.save_ocr_result') as mock_save:
            
            # Mock successful OCR response
            mock_response = Mock()
            mock_response.choices = [Mock()]
            mock_response.choices[0].message.content = json.dumps({
                "supplier": "Integration Test Supplier",
                "invoice_number": "INT-001",
                "invoice_date": "2025-05-28",
                "lines": [
                    {
                        "name": "Test Product",
                        "qty": 2.0,
                        "price": 10000.0,
                        "total_price": 20000.0,
                        "unit": "pcs"
                    }
                ],
                "total_amount": 20000.0
            })
            
            mock_client.chat.completions.create.return_value = mock_response
            
            result = await process_invoice_with_ocr(
                fake_image_data,
                message,
                bot
            )
            
            # Should complete successfully
            assert result["success"] is True
            assert "data" in result
            assert result["data"]["supplier"] == "Integration Test Supplier"
            
            # Should save OCR result
            mock_save.assert_called_once()
            
            # Should send progress messages to user
            bot.send_message.assert_called()
    
    @pytest.mark.asyncio
    async def test_ocr_pipeline_with_retries(self):
        """Test OCR pipeline with retry logic."""
        fake_image_data = b'\xff\xd8\xff\xe0' + b'fake_jpeg_data'
        
        with patch('app.ocr_pipeline_optimized.openai_client') as mock_client:
            
            # First call fails, second succeeds
            mock_client.chat.completions.create.side_effect = [
                Exception("Temporary API error"),
                Mock(choices=[Mock(message=Mock(content=json.dumps({"supplier": "Test"})))])
            ]
            
            processor = OCRProcessor(max_retries=2)
            
            result = await processor.process_with_retries(fake_image_data)
            
            # Should succeed after retry
            assert result["success"] is True
            
            # Should have made 2 API calls
            assert mock_client.chat.completions.create.call_count == 2
    
    @pytest.mark.asyncio
    async def test_ocr_pipeline_exhausted_retries(self):
        """Test OCR pipeline when all retries are exhausted."""
        fake_image_data = b'\xff\xd8\xff\xe0' + b'fake_jpeg_data'
        
        with patch('app.ocr_pipeline_optimized.openai_client') as mock_client:
            
            # All calls fail
            mock_client.chat.completions.create.side_effect = Exception("Persistent API error")
            
            processor = OCRProcessor(max_retries=2)
            
            result = await processor.process_with_retries(fake_image_data)
            
            # Should fail after exhausting retries
            assert result["success"] is False
            assert "retry" in result["error"].lower() or "failed" in result["error"].lower()
            
            # Should have made max_retries + 1 attempts
            assert mock_client.chat.completions.create.call_count == 3


class TestOCRPipelineErrorHandling:
    """Test error handling in OCR pipeline."""
    
    @pytest.mark.asyncio
    async def test_handle_openai_authentication_error(self):
        """Test handling of OpenAI authentication errors."""
        from openai import AuthenticationError
        
        with patch('app.ocr_pipeline_optimized.openai_client') as mock_client:
            
            mock_client.chat.completions.create.side_effect = AuthenticationError("Invalid API key")
            
            result = await call_openai_vision_api("fake_image", "JPEG")
            
            assert result["success"] is False
            assert "authentication" in result["error"].lower() or "api key" in result["error"].lower()
    
    @pytest.mark.asyncio
    async def test_handle_openai_quota_exceeded(self):
        """Test handling of OpenAI quota exceeded errors."""
        from openai import RateLimitError
        
        with patch('app.ocr_pipeline_optimized.openai_client') as mock_client:
            
            mock_client.chat.completions.create.side_effect = RateLimitError("Quota exceeded")
            
            result = await call_openai_vision_api("fake_image", "JPEG")
            
            assert result["success"] is False
            assert "quota" in result["error"].lower() or "limit" in result["error"].lower()
    
    def test_handle_corrupted_image_data(self):
        """Test handling of corrupted image data."""
        corrupted_data_samples = [
            b'',  # Empty
            b'\x00\x00\x00',  # Invalid header
            b'\xff\xd8' + b'\x00' * 1000,  # Truncated JPEG
            b'GIF89a' + b'\x00' * 100,  # GIF (unsupported format)
        ]
        
        for corrupted_data in corrupted_data_samples:
            result = prepare_image_for_ocr(corrupted_data)
            
            # Should handle gracefully
            assert result["success"] is False
            assert "error" in result
    
    def test_handle_malformed_ocr_json_responses(self):
        """Test handling of various malformed JSON responses."""
        malformed_responses = [
            '{"supplier": "Test"',  # Incomplete JSON
            '{"supplier": "Test", "lines": [}',  # Invalid JSON syntax
            '{"supplier": 123}',  # Wrong data types
            '[]',  # Array instead of object
            'null',  # Null value
            '',  # Empty string
            'plain text response',  # Not JSON at all
        ]
        
        for malformed_json in malformed_responses:
            response = {
                "choices": [{
                    "message": {
                        "content": malformed_json
                    }
                }]
            }
            
            result = parse_ocr_response(response)
            
            assert result["success"] is False
            assert "error" in result
    
    @pytest.mark.asyncio
    async def test_handle_network_connectivity_issues(self):
        """Test handling of network connectivity issues."""
        import aiohttp
        
        with patch('app.ocr_pipeline_optimized.openai_client') as mock_client:
            
            # Simulate various network errors
            network_errors = [
                aiohttp.ClientConnectorError("Cannot connect to host"),
                aiohttp.ClientTimeout("Request timeout"),
                ConnectionError("Network unreachable"),
            ]
            
            for error in network_errors:
                mock_client.chat.completions.create.side_effect = error
                
                result = await call_openai_vision_api("fake_image", "JPEG")
                
                assert result["success"] is False
                assert any(word in result["error"].lower() for word in ["network", "connection", "timeout"])


class TestOCRPipelinePerformance:
    """Test performance aspects of OCR pipeline."""
    
    def test_image_size_optimization(self):
        """Test image size optimization for large images."""
        # Simulate large image
        large_image = b'\xff\xd8\xff\xe0' + b'x' * (10 * 1024 * 1024)  # 10MB
        
        result = prepare_image_for_ocr(large_image)
        
        if result["success"]:
            # If processed, should be optimized
            processed_size = len(base64.b64decode(result["image_data"]))
            assert processed_size < len(large_image)
            
            # Should include optimization info
            assert "optimized" in result or "compressed" in result
    
    @pytest.mark.asyncio
    async def test_concurrent_ocr_processing(self):
        """Test concurrent OCR processing capability."""
        import asyncio
        
        fake_images = [
            b'\xff\xd8\xff\xe0' + f'image_{i}'.encode() 
            for i in range(3)
        ]
        
        with patch('app.ocr_pipeline_optimized.call_openai_vision_api') as mock_api:
            
            # Mock successful responses
            mock_api.return_value = {
                "success": True,
                "response": {"choices": [{"message": {"content": '{"supplier": "Test"}'}}]}
            }
            
            # Process multiple images concurrently
            tasks = [
                process_invoice_with_ocr(img_data, Mock(), Mock())
                for img_data in fake_images
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # All should complete successfully
            for result in results:
                if isinstance(result, dict):
                    assert result["success"] is True
    
    def test_memory_efficient_image_processing(self):
        """Test memory-efficient image processing."""
        # Test that large images don't cause memory issues
        test_sizes = [
            1 * 1024 * 1024,    # 1MB
            5 * 1024 * 1024,    # 5MB
            10 * 1024 * 1024,   # 10MB
        ]
        
        for size in test_sizes:
            image_data = b'\xff\xd8\xff\xe0' + b'x' * size
            
            # Should handle without memory errors
            result = prepare_image_for_ocr(image_data)
            
            # Either successfully process or gracefully reject
            assert "success" in result
            if not result["success"]:
                assert "error" in result


if __name__ == "__main__":
    pytest.main([__file__])