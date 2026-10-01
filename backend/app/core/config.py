from functools import lru_cache
from pathlib import Path
import re

from dotenv import dotenv_values
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATABASE_URL = "sqlite:///./backend/data/research_assistant.db"


def _legacy_supabase_defaults() -> dict[str, str | None]:
    """Read legacy lowercase database fields without colliding with OS vars.

    In particular, a macOS/Linux ``USER`` environment variable overrides an
    env-file key called ``user`` in Pydantic's normal case-insensitive lookup.
    The explicit ``SUPABASE_DB_*`` names below are preferred. This fallback
    lets existing local .env files keep working while they are migrated.
    """
    values = dotenv_values(PROJECT_ROOT / ".env")
    return {
        "user": values.get("user"),
        "password": values.get("password"),
        "host": values.get("host"),
        "port": values.get("port"),
        "dbname": values.get("dbname"),
    }


LEGACY_SUPABASE_DEFAULTS = _legacy_supabase_defaults()
LOCAL_NETWORK_ORIGIN_REGEX = (
    r"^http://(?:localhost|127\.0\.0\.1|"
    r"10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|"
    r"172\.(?:1[6-9]|2\d|3[0-1])(?:\.\d{1,3}){2})(?::\d{1,5})?$"
)


class Settings(BaseSettings):
    app_name: str = "AI Research Assistant API"
    app_environment: str = "development"
    api_v1_prefix: str = "/api/v1"
    database_url: str = DEFAULT_DATABASE_URL
    # These optional values support the connection details copied from the
    # Supabase Connect dialog.  ``DATABASE_URL`` remains the preferred generic
    # setting; when all five values are present, this app safely constructs it
    # with the psycopg driver, URL-encoded credentials, and TLS enabled.
    supabase_db_user: str | None = Field(
        default=LEGACY_SUPABASE_DEFAULTS["user"],
        validation_alias="SUPABASE_DB_USER",
    )
    supabase_db_password: str | None = Field(
        default=LEGACY_SUPABASE_DEFAULTS["password"],
        validation_alias="SUPABASE_DB_PASSWORD",
    )
    supabase_db_host: str | None = Field(
        default=LEGACY_SUPABASE_DEFAULTS["host"],
        validation_alias="SUPABASE_DB_HOST",
    )
    supabase_db_port: int | None = Field(
        default=LEGACY_SUPABASE_DEFAULTS["port"],
        validation_alias="SUPABASE_DB_PORT",
    )
    supabase_db_name: str | None = Field(
        default=LEGACY_SUPABASE_DEFAULTS["dbname"],
        validation_alias="SUPABASE_DB_NAME",
    )
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
    reranker_model_name: str = "Qwen/Qwen3-Reranker-0.6B"
    reranker_batch_size: int = Field(default=8, ge=1, le=64)
    final_context_k: int = Field(default=8, ge=1, le=12)
    minimum_evidence_count: int = Field(default=1, ge=1, le=8)
    reranker_min_score: float = 0.0
    generation_runtime: str = "ollama"
    generation_model_name: str = "qwen3.5:9b"
    ollama_base_url: str = "http://localhost:11434"
    generation_max_new_tokens: int = Field(default=768, ge=64, le=4096)
    generation_temperature: float = Field(default=0.1, ge=0.0, le=1.0)
    generation_timeout_seconds: float = Field(default=120.0, gt=0.0, le=600.0)
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]
    )
    cors_origin_regex: str | None = None
    cors_allow_local_network: bool = True

    @field_validator("google_client_id", "google_client_secret", mode="before")
    @classmethod
    def blank_google_values_are_unset(cls, value: str | None) -> str | None:
        """Allow the checked-in example env file to leave OAuth disabled."""
        if value is None:
            return None
        value = value.strip()
        return value or None

    model_config = SettingsConfigDict(
        # Resolve the shared development env file from the repository root,
        # not from the shell's current working directory.
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        protected_namespaces=("settings_",),
    )

    @model_validator(mode="after")
    def validate_chunk_settings(self) -> "Settings":
        supabase_values = (
            self.supabase_db_user,
            self.supabase_db_password,
            self.supabase_db_host,
            self.supabase_db_port,
            self.supabase_db_name,
        )
        # An explicitly supplied DATABASE_URL always wins.  This keeps the
        # generic deployment setting authoritative and lets tests select their
        # own isolated SQLite database even when a developer's .env contains
        # Supabase fields.
        if (
            any(value is not None for value in supabase_values)
            and self.database_url == DEFAULT_DATABASE_URL
        ):
            if any(value is None for value in supabase_values):
                raise ValueError(
                    "Supabase database settings require user, password, host, port, and database name"
                )
            self.database_url = URL.create(
                "postgresql+psycopg",
                username=self.supabase_db_user,
                password=self.supabase_db_password,
                host=self.supabase_db_host,
                port=self.supabase_db_port,
                database=self.supabase_db_name,
                query={"sslmode": "require"},
            ).render_as_string(hide_password=False)
        if self.document_chunk_overlap >= self.document_chunk_size:
            raise ValueError(
                "document_chunk_overlap must be smaller than document_chunk_size"
            )
        if self.app_environment == "production" and not self.auth_cookie_secure:
            raise ValueError("AUTH_COOKIE_SECURE must be true in production")
        if (self.google_client_id is None) != (self.google_client_secret is None):
            raise ValueError("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set together")
        if self.generation_runtime != "ollama":
            raise ValueError("GENERATION_RUNTIME must be ollama")
        return self

    @property
    def effective_cors_origin_regex(self) -> str | None:
        """Allow private LAN origins only for local development by default."""
        if self.app_environment == "development" and self.cors_allow_local_network:
            return self.cors_origin_regex or LOCAL_NETWORK_ORIGIN_REGEX
        return self.cors_origin_regex

    def is_allowed_origin(self, origin: str) -> bool:
        if origin in self.cors_origins:
            return True
        pattern = self.effective_cors_origin_regex
        return bool(pattern and re.fullmatch(pattern, origin))


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
