from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI Research Assistant API"
    app_environment: str = "development"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "sqlite:///./backend/data/research_assistant.db"
    document_upload_dir: Path = Path("backend/data/uploads")
    document_max_upload_bytes: int = Field(default=25 * 1024 * 1024, gt=0)
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
