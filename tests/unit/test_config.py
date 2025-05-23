from app.config import Settings


class MockTestSettings(Settings):
    """Test settings that override default settings for tests."""

    # Override OpenAI settings for tests
    OPENAI_API_KEY: str = "test-api-key"
    OPENAI_MODEL: str = "gpt-4o"
    OPENAI_GPT_MODEL: str = "gpt-4o"  # Added for OCR pipeline
    USE_OPENAI_OCR: bool = True
    OPENAI_OCR_KEY: str = "test-ocr-key"
    OPENAI_CHAT_KEY: str = "test-chat-key"
