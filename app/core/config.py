from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    GEMINI_API_KEY: Optional[str] = ""
    PORT: int = 8000
    ENV: str = "development"
    DATABASE_URL: str = "sqlite:///./agent_hub.db"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
