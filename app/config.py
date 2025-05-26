import logging
import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    TELEGRAM_BOT_TOKEN: str = ""
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o"  # Updated to match actual usage
    OPENAI_GPT_MODEL: str = "gpt-4o"  # Updated to match actual usage

    # Fuzzy matching configuration
    MATCH_THRESHOLD: float = 0.75  # Default match threshold (0-1.0)
    MATCH_EXACT_BONUS: float = 0.05  # Bonus for substring matches (0-1.0)
    MATCH_LENGTH_PENALTY: float = 0.1  # Penalty weight for length differences (0-1.0)
    MATCH_MIN_SCORE: float = 0.5  # Minimum score to show in suggestions (0-1.0)
    
    # Syrve API configuration
    SYRVE_SERVER_URL: str = ""
    SYRVE_LOGIN: str = ""
    SYRVE_PASSWORD: str = ""  # Plain text password (dev/test only)
    SYRVE_PASS_SHA1: str = ""  # SHA1 hashed password (production)
    VERIFY_SSL: bool = False  # SSL verification (enable for production)

    # OpenAI API configuration
    USE_OPENAI_OCR: bool = True  # Enable OpenAI OCR by default
    OPENAI_OCR_KEY: str = os.getenv("OPENAI_OCR_KEY", os.getenv("OPENAI_API_KEY", ""))
    OPENAI_CHAT_KEY: str = os.getenv("OPENAI_CHAT_KEY", "")
    OPENAI_ASSISTANT_ID: str = os.getenv("OPENAI_ASSISTANT_ID", "")
    OPENAI_VISION_ASSISTANT_ID: str = os.getenv(
        "OPENAI_VISION_ASSISTANT_ID", ""
    )  # Added from app/config/settings.py

    # Image preprocessing configuration
    USE_IMAGE_PREPROCESSING: bool = True  # Enable image preprocessing by default

    # Business logic configuration
    OWN_COMPANY_ALIASES: list[str] = ["Bali Veg Ltd", "Nota AI Cafe"]

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

        # Используем OPENAI_OCR_KEY, а если его нет - OPENAI_API_KEY
        ocr_key = settings.OPENAI_OCR_KEY
        if not ocr_key:
            logging.warning("OPENAI_OCR_KEY не установлен, пытаемся использовать OPENAI_API_KEY")
            ocr_key = os.getenv("OPENAI_API_KEY", "")

        if ocr_key:
            _ocr_client = openai.OpenAI(api_key=ocr_key)
            logging.info("OCR клиент инициализирован успешно")
            return _ocr_client
        else:
            logging.error("OPENAI_OCR_KEY и OPENAI_API_KEY не установлены; OCR недоступен")
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
