"""
Common test fixtures and configuration.
"""
import sys
from unittest.mock import MagicMock

# Mock PaddleOCR module to avoid actual import
class MockPaddleOCR:
    def __init__(self, **kwargs):
        pass
    
    def ocr(self, *args, **kwargs):
        return [
            [((0, 0, 100, 30), ("Test Text", 0.95))]
        ]

# Mock the paddleocr module
sys.modules['paddleocr'] = MagicMock()
sys.modules['paddleocr.PaddleOCR'] = MockPaddleOCR

# Mock the paddle module
sys.modules['paddle'] = MagicMock()