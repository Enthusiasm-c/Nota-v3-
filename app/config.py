from pydantic_settings import BaseSettings, SettingsConfigDict
import os

import logging


class Settings(BaseSettings):
    TELEGRAM_BOT_TOKEN: str = ""
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-3.5-turbo"

    # Fuzzy matching configuration
    MATCH_THRESHOLD: float = 0.85  # Повышаем порог сравнения с 0.75 до 0.85
    MATCH_EXACT_BONUS: float = 0.05  # Bonus for substring matches (0-1.0)
    MATCH_LENGTH_PENALTY: float = 0.15  # Увеличиваем штраф за разницу в длине
    MATCH_MIN_SCORE: float = 0.6  # Повышаем минимальный порог для предложений
    
    # Часто ошибочно распознаваемые слова
    SIMILAR_WORD_PAIRS: list[tuple[str, str]] = [
        ("rice", "milk"),
        ("milk", "rice"),
        ("cream", "crean"),
        ("salt", "solt"),
        ("sugar", "suger")
    ]

    # OpenAI API configuration
    USE_OPENAI_OCR: bool = False
    OPENAI_OCR_KEY: str = os.getenv("OPENAI_OCR_KEY", "")
    OPENAI_CHAT_KEY: str = os.getenv("OPENAI_CHAT_KEY", "")
    
    # Image preprocessing configuration
    USE_IMAGE_PREPROCESSING: bool = False  # True=enable, False=disable image preprocessing

    # Business logic configuration
    OWN_COMPANY_ALIASES: list[str] = ["Bali Veg Ltd", "Nota AI Cafe"]

    # Base URL for server (used for image links)
    BASE_URL: str = os.environ.get("BASE_URL", "")

    MAX_PRODUCTS_IN_PROMPT: int = 50

    model_config = SettingsConfigDict(
        extra="allow", env_file=os.getenv("ENV_FILE", ".env"), env_file_encoding="utf-8"
    )


settings = Settings()


# Cache for OpenAI clients - initialized on first use
_ocr_client = None
_chat_client = None


def get_ocr_client():
    """
    Get OpenAI client for OCR with lazy initialization.
    Initializes client only on first call.

    Returns:
        openai.OpenAI: Initialized client or None on error
    """
    global _ocr_client

    if _ocr_client is not None:
        return _ocr_client

    try:
        import openai

        if settings.OPENAI_OCR_KEY:
            _ocr_client = openai.OpenAI(api_key=settings.OPENAI_OCR_KEY)
            return _ocr_client
        else:
            logging.error("OPENAI_OCR_KEY not set; OCR unavailable")
            return None
    except ImportError:
        logging.error("openai package not installed; OCR unavailable")
        return None
    except Exception as e:
        logging.error(f"Error initializing OCR client: {e}")
        return None


def get_chat_client():
    """
    Get OpenAI client for chat with lazy initialization.
    Initializes client only on first call.

    Returns:
        openai.OpenAI: Initialized client or None on error
    """
    global _chat_client

    if _chat_client is not None:
        return _chat_client

    try:
        import openai

        if settings.OPENAI_CHAT_KEY:
            _chat_client = openai.OpenAI(api_key=settings.OPENAI_CHAT_KEY)
            return _chat_client
        else:
            logging.error("OPENAI_CHAT_KEY not set; Chat unavailable")
            return None
    except ImportError:
        logging.error("openai package not installed; Chat unavailable")
        return None
    except Exception as e:
        logging.error(f"Error initializing Chat client: {e}")
        return None
