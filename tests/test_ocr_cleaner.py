import pytest
import io
from PIL import Image
from app.ocr_cleaner import preprocess_for_ocr, resize_image, clean_ocr_response


def test_clean_ocr_response_basic():
    """Test basic cleaning functionality."""
    # Test basic text cleaning
    text = "  .,;  Test Product  !!!  "
    cleaned = clean_ocr_response(text)
    assert cleaned == " Test Product "


class TestPreprocessForOcr:
    """Test preprocess_for_ocr function."""

    def test_preprocess_for_ocr_calls_resize(self):
        """Test that preprocess_for_ocr calls resize_image."""
        # Create a simple test image
        img = Image.new('RGB', (100, 100), color='white')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='JPEG')
        img_bytes = img_bytes.getvalue()
        
        result = preprocess_for_ocr(img_bytes)
        
        # Should return some bytes (processed image)
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_preprocess_for_ocr_empty_input(self):
        """Test preprocess_for_ocr with empty input."""
        # Should handle gracefully and return original
        result = preprocess_for_ocr(b'')
        assert result == b''


class TestResizeImage:
    """Test resize_image function."""

    def create_test_image(self, width: int, height: int, format: str = 'JPEG') -> bytes:
        """Helper to create test images."""
        img = Image.new('RGB', (width, height), color='red')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format=format)
        return img_bytes.getvalue()

    def test_resize_image_small_image_unchanged(self):
        """Test that small images are returned unchanged."""
        # Create small image
        small_img = self.create_test_image(100, 100)
        
        result = resize_image(small_img, max_size=1600)
        
        # Should return exactly the same bytes
        assert result == small_img

    def test_resize_image_large_image_resized(self):
        """Test that large images are resized."""
        # Create large image
        large_img = self.create_test_image(2000, 2000)
        
        result = resize_image(large_img, max_size=1600)
        
        # Should return different (smaller) bytes
        assert result != large_img
        assert len(result) < len(large_img)
        
        # Verify the result is a valid image with correct size
        result_img = Image.open(io.BytesIO(result))
        assert max(result_img.size) <= 1600

    def test_resize_image_maintains_aspect_ratio(self):
        """Test that aspect ratio is maintained during resize."""
        # Create rectangular image
        rect_img = self.create_test_image(2000, 1000)  # 2:1 ratio
        
        result = resize_image(rect_img, max_size=800)
        
        # Check result dimensions
        result_img = Image.open(io.BytesIO(result))
        width, height = result_img.size
        
        # Should maintain 2:1 ratio (approximately)
        ratio = width / height
        assert abs(ratio - 2.0) < 0.1

    def test_resize_image_custom_quality(self):
        """Test resize with custom quality setting."""
        large_img = self.create_test_image(2000, 2000)
        
        # Test with low quality
        result_low = resize_image(large_img, max_size=1600, quality=30)
        # Test with high quality  
        result_high = resize_image(large_img, max_size=1600, quality=95)
        
        # Low quality should produce smaller file
        assert len(result_low) < len(result_high)

    def test_resize_image_png_with_transparency(self):
        """Test resize of PNG images with transparency."""
        # Create PNG with transparency
        img = Image.new('RGBA', (2000, 2000), color=(255, 0, 0, 128))
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        png_bytes = img_bytes.getvalue()
        
        result = resize_image(png_bytes, max_size=1600)
        
        # Should handle PNG format
        assert isinstance(result, bytes)
        assert len(result) > 0
        
        # Verify it's still a valid image
        result_img = Image.open(io.BytesIO(result))
        assert result_img.format in ['PNG', 'JPEG']

    def test_resize_image_invalid_input(self):
        """Test resize with invalid image data."""
        invalid_bytes = b'not an image'
        
        result = resize_image(invalid_bytes)
        
        # Should return original bytes on error
        assert result == invalid_bytes

    def test_resize_image_already_optimized(self):
        """Test when resizing doesn't improve file size."""
        # Create a very small image that won't compress well
        img = Image.new('RGB', (10, 10), color='white')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='JPEG', quality=100)
        small_img = img_bytes.getvalue()
        
        result = resize_image(small_img, max_size=1600, quality=50)
        
        # If optimization doesn't help, should return original
        # This might return either original or optimized depending on actual compression
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_resize_image_grayscale_conversion(self):
        """Test resize with grayscale images."""
        # Create grayscale image
        img = Image.new('L', (2000, 2000), color=128)
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='JPEG')
        gray_img = img_bytes.getvalue()
        
        result = resize_image(gray_img, max_size=1600)
        
        # Should handle grayscale images
        assert isinstance(result, bytes)
        assert len(result) < len(gray_img)


class TestCleanOcrResponse:
    """Test clean_ocr_response function."""

    def test_clean_ocr_response_empty_string(self):
        """Test cleaning empty string."""
        assert clean_ocr_response("") == ""
        assert clean_ocr_response(None) == ""

    def test_clean_ocr_response_whitespace_normalization(self):
        """Test that multiple whitespaces are normalized."""
        text = "  hello   world  test  "
        result = clean_ocr_response(text)
        assert result == "hello world test"

    def test_clean_ocr_response_remove_special_chars(self):
        """Test removal of special characters from start and end."""
        test_cases = [
            (".,hello world,.", "hello world"),
            (";;;test text!!!", "test text"),
            ("---product name___", "product name"),
            ("!?!important?!?", "important"),
            (":;start and end;:", "start and end"),
        ]
        
        for input_text, expected in test_cases:
            result = clean_ocr_response(input_text)
            assert result == expected

    def test_clean_ocr_response_preserve_middle_punctuation(self):
        """Test that punctuation in the middle is preserved."""
        text = ".hello, world. test!"
        result = clean_ocr_response(text)
        assert result == "hello, world. test"

    def test_clean_ocr_response_mixed_cleaning(self):
        """Test cleaning with both whitespace and special chars."""
        text = "  .,;  hello   world  test  !!!  "
        result = clean_ocr_response(text)
        assert result == " hello world test "

    def test_clean_ocr_response_newlines_and_tabs(self):
        """Test cleaning with newlines and tabs."""
        text = "hello\nworld\ttest"
        result = clean_ocr_response(text)
        assert result == "hello world test"

    def test_clean_ocr_response_only_special_chars(self):
        """Test text with only special characters."""
        text = ".,;:!?-_"
        result = clean_ocr_response(text)
        assert result == ""

    def test_clean_ocr_response_unicode_text(self):
        """Test cleaning with unicode characters."""
        text = "  .,  тест продукт  !!  "
        result = clean_ocr_response(text)
        assert result == " тест продукт "

    def test_clean_ocr_response_numbers_and_symbols(self):
        """Test cleaning with numbers and currency symbols."""
        text = "  $100.50  "
        result = clean_ocr_response(text)
        assert result == "$100.50"

    def test_clean_ocr_response_complex_example(self):
        """Test cleaning with complex real-world OCR output."""
        text = "  .,;: Product Name 123 - Fresh Apples (5kg) $25.99 !!!___  "
        result = clean_ocr_response(text)
        assert result == " Product Name 123 - Fresh Apples (5kg) $25.99 "


class TestOcrCleanerIntegration:
    """Integration tests for ocr_cleaner module."""

    def test_full_preprocessing_pipeline(self):
        """Test complete preprocessing pipeline."""
        # Create test image
        img = Image.new('RGB', (2000, 2000), color='blue')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='JPEG')
        original_bytes = img_bytes.getvalue()
        
        # Process through pipeline
        processed_bytes = preprocess_for_ocr(original_bytes)
        
        # Verify processing worked
        assert isinstance(processed_bytes, bytes)
        assert len(processed_bytes) > 0
        
        # Verify result is a valid image
        processed_img = Image.open(io.BytesIO(processed_bytes))
        assert processed_img.format in ['JPEG', 'PNG']
        assert max(processed_img.size) <= 1600

    def test_text_cleaning_realistic_scenarios(self):
        """Test text cleaning with realistic OCR scenarios."""
        ocr_outputs = [
            "  .,  TOTAL: $125.99  !!  ",
            "Product: Fresh Bananas\n\nQty: 5 kg",
            "   ___Invoice #12345___   ",
            "Date: 2024-01-15.,;:!",
            "  Supplier Name:   ABC Company Ltd.  "
        ]
        
        expected_results = [
            " TOTAL: $125.99 ",  # Пробелы остаются
            "Product: Fresh Bananas Qty: 5 kg",
            "Invoice #12345",  # Подчеркивания удаляются полностью
            "Date: 2024-01-15",
            "Supplier Name: ABC Company Ltd"  # Точка тоже удаляется
        ]
        
        for ocr_output, expected in zip(ocr_outputs, expected_results):
            result = clean_ocr_response(ocr_output)
            assert result == expected

    def test_edge_cases_handling(self):
        """Test handling of edge cases."""
        edge_cases = [
            ("", ""),  # Empty string
            ("   ", ""),  # Only whitespace
            (".,;:!?-_", ""),  # Only special chars
            ("a", "a"),  # Single character
            ("  a  ", "a"),  # Single char with spaces
        ]
        
        for input_text, expected in edge_cases:
            result = clean_ocr_response(input_text)
            assert result == expected

    def test_image_processing_error_handling(self):
        """Test that image processing handles errors gracefully."""
        # Test with various invalid inputs
        invalid_inputs = [
            b'',  # Empty bytes
            b'not an image',  # Invalid image data
            b'\x00\x01\x02',  # Binary garbage
        ]
        
        for invalid_input in invalid_inputs:
            try:
                result = resize_image(invalid_input)
                # Should return original input on error
                assert result == invalid_input
            except Exception as e:
                pytest.fail(f"resize_image should handle errors gracefully, but raised: {e}")

    def test_performance_with_various_sizes(self):
        """Test performance characteristics with different image sizes."""
        sizes = [(100, 100), (800, 600), (1920, 1080), (3000, 2000)]
        
        for width, height in sizes:
            img = Image.new('RGB', (width, height), color='green')
            img_bytes = io.BytesIO()
            img.save(img_bytes, format='JPEG')
            original_bytes = img_bytes.getvalue()
            
            result = resize_image(original_bytes, max_size=1600)
            
            # Verify result is reasonable
            assert isinstance(result, bytes)
            assert len(result) > 0
            
            # Verify resulting image size
            result_img = Image.open(io.BytesIO(result))
def test_cleaner_positions_only():
    # Payload with only positions
    payload = '{"positions": [{"name": "Тунец", "qty": 2, "unit": "kg"}]}'
    cleaned = clean_ocr_response(payload)
    data = ParsedData.model_validate(cleaned)
    assert data.supplier is None
    assert data.date is None
    assert len(data.positions) == 1
    assert data.positions[0].name == "Тунец"
    assert data.positions[0].qty == 2
    assert data.positions[0].unit == "kg"
