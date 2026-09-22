from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI Research Assistant API"
    app_environment: str = "development"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "sqlite:///./backend/data/research_assistant.db"
    document_upload_dir: Path = Path("backend/data/uploads")
    document_max_upload_bytes: int = Field(default=25 * 1024 * 1024, gt=0)
    document_chunk_size: int = Field(default=4000, ge=256)
    document_chunk_overlap: int = Field(default=400, ge=0)
    auth_session_days: int = Field(default=7, ge=1, le=30)
    auth_cookie_secure: bool = False
    frontend_url: str = "http://localhost:3000"
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str = "http://localhost:8000/api/v1/auth/google/callback"
    google_oauth_state_minutes: int = Field(default=10, ge=1, le=30)
    embedding_model_name: str = "Qwen/Qwen3-Embedding-0.6B"
    model_device: str = "auto"
    model_cache_dir: Path | None = None
    embedding_batch_size: int = Field(default=8, ge=1, le=128)
    embedding_dimension: int = Field(default=1024, ge=32, le=1024)
    vector_top_k: int = Field(default=24, ge=1, le=100)
    keyword_top_k: int = Field(default=24, ge=1, le=100)
    hybrid_candidate_k: int = Field(default=24, ge=1, le=30)
    embedding_enabled: bool = True
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
        protected_namespaces=("settings_",),
    )

    @model_validator(mode="after")
    def validate_chunk_settings(self) -> "Settings":
        if self.document_chunk_overlap >= self.document_chunk_size:
            raise ValueError(
                "document_chunk_overlap must be smaller than document_chunk_size"
            )
        if self.app_environment == "production" and not self.auth_cookie_secure:
            raise ValueError("AUTH_COOKIE_SECURE must be true in production")
        if (self.google_client_id is None) != (self.google_client_secret is None):
            raise ValueError("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set together")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
