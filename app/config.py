from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
import os

class Settings(BaseSettings):
    TELEGRAM_BOT_TOKEN: str
    OPENAI_API_KEY: str
    OPENAI_MODEL: str = "gpt-4o"
    MATCH_THRESHOLD: float = 0.75

    class Config:
        env_file = os.getenv("ENV_FILE", ".env")
        env_file_encoding = 'utf-8'

settings = Settings()
