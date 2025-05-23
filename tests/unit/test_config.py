import os
import pytest
from unittest.mock import Mock, patch, MagicMock
from app.config import Settings, settings, get_ocr_client, get_chat_client


class MockTestSettings(Settings):
    """Test settings that override default settings for tests."""

    # Override OpenAI settings for tests
    OPENAI_API_KEY: str = "test-api-key"
    OPENAI_MODEL: str = "gpt-4o"
    OPENAI_GPT_MODEL: str = "gpt-4o"  # Added for OCR pipeline
    USE_OPENAI_OCR: bool = True
    OPENAI_OCR_KEY: str = "test-ocr-key"
    OPENAI_CHAT_KEY: str = "test-chat-key"