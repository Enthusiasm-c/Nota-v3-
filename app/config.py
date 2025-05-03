from pydantic_settings import BaseSettings, SettingsConfigDict
import os

import logging


class Settings(BaseSettings):
    TELEGRAM_BOT_TOKEN: str = ""
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o"
    MATCH_THRESHOLD: float = 0.75
    USE_OPENAI_OCR: bool = False
    OPENAI_OCR_KEY: str = os.getenv("OPENAI_OCR_KEY", "")
    OPENAI_CHAT_KEY: str = os.getenv("OPENAI_CHAT_KEY", "")
    OPENAI_ASSISTANT_ID: str = os.getenv("OPENAI_ASSISTANT_ID", "")
    OWN_COMPANY_ALIASES: list[str] = [
        "Bali Veg Ltd", "Nota AI Cafe"
    ]

    model_config = SettingsConfigDict(
        extra="allow",
        env_file=os.getenv("ENV_FILE", ".env"),
        env_file_encoding="utf-8"
    )


settings = Settings()


# OpenAI clients (None if keys missing)
ocr_client = None
chat_client = None

try:
    import openai
    if settings.OPENAI_OCR_KEY:
        ocr_client = openai.OpenAI(api_key=settings.OPENAI_OCR_KEY)
    else:
        logging.error("OPENAI_OCR_KEY not set; OCR unavailable")
    if settings.OPENAI_CHAT_KEY:
        chat_client = openai.OpenAI(api_key=settings.OPENAI_CHAT_KEY)
    else:
        logging.error("OPENAI_CHAT_KEY not set; Chat unavailable")
except ImportError:
    logging.error("openai package not installed; OCR/Chat unavailable")


def get_ocr_client():
    return ocr_client


def get_chat_client():
    return chat_client
