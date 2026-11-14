from functools import lru_cache
from pathlib import Path
import re
from typing import Literal

from dotenv import dotenv_values
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

from app.db.session import normalize_database_url


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATABASE_URL = "sqlite:///./backend/data/research_assistant.db"
DEV_BYOK_ENCRYPTION_SECRET = "dev-only-byok-encryption-secret-change-in-production"
_WEAK_BYOK_SECRETS = frozenset(
    {
        DEV_BYOK_ENCRYPTION_SECRET,
        "change-me",
        "changeme",
        "secret",
        "dev-secret",
        "development",
    }
)


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
    # Production is the safe default. Local development opts in explicitly
    # with APP_ENVIRONMENT=development (see .env.example).
    app_environment: Literal["production", "development", "test"] = "production"
    log_level: str = "INFO"
    log_json: bool = False
    enable_api_docs: bool | None = None
    api_v1_prefix: str = "/api/v1"
    database_url: str = DEFAULT_DATABASE_URL
    # Neon PostgreSQL configuration (pooled URL for runtime, direct URL for migrations).
    neon_database_url: str | None = None
    neon_direct_database_url: str | None = None
    database_url_unpooled: str | None = None
    # Legacy Supabase configuration preserved for backward compatibility and migration.
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
    # Storage configuration (local filesystem or Cloudflare R2 S3-compatible storage).
    storage_backend: Literal["local", "r2"] = "local"
    document_upload_dir: Path = Path("backend/data/uploads")
    document_max_upload_bytes: int = Field(default=25 * 1024 * 1024, gt=0)
    r2_account_id: str | None = None
    r2_access_key_id: str | None = None
    r2_secret_access_key: str | None = None
    r2_bucket_name: str | None = None
    r2_endpoint_url: str | None = None
    r2_region: str = "auto"
    r2_signed_url_ttl_seconds: int = Field(default=900, ge=60, le=86400)

    # Ingestion & chunking configuration.
    document_chunk_size: int = Field(default=4000, ge=256)
    document_chunk_overlap: int = Field(default=400, ge=0)
    document_ingestion_backend: Literal["docling", "legacy"] = "docling"
    ingestion_version: str = Field(default="docling-llamaindex-v1", min_length=1)
    document_chunk_max_tokens: int = Field(default=512, ge=64, le=8192)
    docling_ocr_mode: Literal["auto", "disabled", "force"] = "auto"

    # Authentication & security.
    auth_session_days: int = Field(default=7, ge=1, le=30)
    auth_inactivity_days: int = Field(default=3, ge=1, le=30)
    auth_cookie_secure: bool | None = None
    auth_max_sessions_per_user: int = Field(default=10, ge=1, le=100)
    frontend_url: str = "http://localhost:3000"
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str = "http://localhost:8000/api/v1/auth/google/callback"
    google_oauth_state_minutes: int = Field(default=10, ge=1, le=30)
    api_key_encryption_secret: str | None = None

    # Embeddings configuration (local Qwen3-Embedding-0.6B or Cloudflare Workers AI).
    embedding_provider: Literal["local", "cloudflare"] = "local"
    embedding_model_name: str = "Qwen/Qwen3-Embedding-0.6B"
    embedding_model_revision: str = "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3"
    cloudflare_account_id: str | None = None
    cloudflare_api_token: str | None = None
    cloudflare_embedding_model: str = "@cf/baai/bge-m3"
    cloudflare_reranker_model: str = "@cf/baai/bge-reranker-base"
    model_trust_remote_code: bool = False
    model_device: str = "auto"
    model_cache_dir: Path | None = None
    embedding_batch_size: int = Field(default=8, ge=1, le=128)
    embedding_dimension: int = Field(default=1024, ge=32, le=1024)
    vector_top_k: int = Field(default=24, ge=1, le=100)
    keyword_top_k: int = Field(default=24, ge=1, le=100)
    hybrid_candidate_k: int = Field(default=24, ge=1, le=30)
    rrf_k: int = Field(default=60, ge=1, le=200)
    embedding_enabled: bool = True
    allow_sqlite_retrieval_fallback: bool = False

    # Reranking configuration (local Qwen3-Reranker-0.6B, Jina Reranker API, Cloudflare BGE, or fast lexical).
    reranker_provider: Literal["local", "jina", "cloudflare", "lexical"] = "local"
    reranker_model_name: str = "Qwen/Qwen3-Reranker-0.6B"
    reranker_model_revision: str = "e61197ed45024b0ed8a2d74b80b4d909f1255473"
    reranker_batch_size: int = Field(default=8, ge=1, le=64)
    jina_api_key: str | None = None
    jina_reranker_model: str = "jina-reranker-v2-base-multilingual"
    jina_reader_base_url: str = "https://r.jina.ai"
    final_context_k: int = Field(default=8, ge=1, le=12)
    minimum_evidence_count: int = Field(default=1, ge=1, le=8)
    reranker_min_score: float = 0.0
    adaptive_fast_path_enabled: bool = True
    query_embedding_cache_size: int = Field(default=256, ge=0, le=4096)

    # Multimodal ingestion (Groq Whisper, FFmpeg, Gemini Flash Vision).
    groq_api_key: str | None = None
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_whisper_model: str = "whisper-large-v3-turbo"
    ffmpeg_binary: str = "ffmpeg"
    ffprobe_binary: str = "ffprobe"
    video_max_frames: int = Field(default=3, ge=1, le=30)
    video_scene_threshold: float = Field(default=0.35, ge=0.05, le=0.95)
    vision_enabled: bool = True
    vision_min_image_dimension: int = Field(default=160, ge=32, le=4096)

    # Centralized LLM Router & Generation providers.
    generation_runtime: Literal["ollama", "router"] = "ollama"
    generation_model_name: str = "qwen3.5:9b"
    ollama_base_url: str = "http://localhost:11434"
    llm_router_providers: list[str] = Field(
        default_factory=lambda: ["gemini", "openrouter", "cerebras", "mistral"]
    )
    cerebras_api_key: str | None = None
    cerebras_base_url: str = "https://api.cerebras.ai/v1"
    cerebras_model_name: str = "gpt-oss-120b"
    gemini_api_key: str | None = None
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_model_name: str = "gemini-3.8-flash"
    gemini_fallback_model_name: str = "gemini-3.1-flash-lite"
    mistral_api_key: str | None = None
    mistral_base_url: str = "https://api.mistral.ai/v1"
    mistral_model_name: str = "mistral-small-4"
    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model_name: str = "openrouter/free"
    groq_llm_model_name: str = "llama-3.3-70b-versatile"
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model_name: str = "gpt-4o-mini"
    claude_api_key: str | None = None
    claude_base_url: str = "https://api.anthropic.com/v1"
    claude_model_name: str = "claude-3-5-haiku-latest"
    grok_api_key: str | None = None
    grok_base_url: str = "https://api.x.ai/v1"
    grok_model_name: str = "grok-3-mini-fast"
    llm_circuit_breaker_threshold: int = Field(default=3, ge=1, le=20)
    llm_circuit_breaker_cooldown_seconds: float = Field(default=60.0, ge=1.0, le=3600.0)
    llm_daily_token_quota_per_provider: int = Field(default=250_000, ge=1000)
    llm_daily_requests_per_provider: int = Field(default=100, ge=1, le=100_000)
    llm_daily_system_request_pool: int | None = Field(default=None, ge=1)

    generation_max_new_tokens: int = Field(default=768, ge=64, le=4096)
    generation_temperature: float = Field(default=0.1, ge=0.0, le=1.0)
    generation_timeout_seconds: float = Field(default=120.0, gt=0.0, le=600.0)
    llm_quick_timeout_seconds: float = Field(default=12.0, gt=0.0, le=120.0)
    llm_provider_timeout_seconds: float = Field(default=18.0, gt=0.0, le=300.0)
    llm_deep_timeout_seconds: float = Field(default=60.0, gt=0.0, le=600.0)
    gemini_primary_timeout_seconds: float = Field(default=8.0, gt=0.0, le=120.0)
    gemini_fallback_cooldown_seconds: float = Field(default=300.0, ge=0.0, le=3600.0)
    generation_connect_timeout_seconds: float = Field(default=5.0, gt=0.0, le=60.0)
    generation_max_retries: int = Field(default=2, ge=0, le=5)
    generation_retry_backoff_seconds: float = Field(default=0.5, ge=0.0, le=30.0)
    generation_model_check_ttl_seconds: float = Field(default=300, ge=0)

    # Optional client-side AI integrations (Puter.js, WebLLM).
    enable_puter_ai: bool = True
    enable_webllm: bool = True
    webllm_default_model: str = "Qwen2.5-1.5B-Instruct-q4f16_1-MLC"

    # Observability (Langfuse & internal telemetry).
    telemetry_enabled: bool = True
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"
    langfuse_enabled: bool = False

    # HTTP & CORS settings.
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]
    )
    cors_origin_regex: str | None = None
    cors_allow_local_network: bool = False
    require_origin_header: bool = True
    max_json_body_bytes: int = Field(default=1024 * 1024, ge=1024)

    # Database connection pool (tuned for Neon PostgreSQL & concurrent FastAPI requests).
    db_pool_size: int = Field(default=10, ge=1, le=200)
    db_max_overflow: int = Field(default=20, ge=0, le=200)
    db_pool_timeout_seconds: float = Field(default=10.0, gt=0.0, le=120.0)
    db_pool_recycle_seconds: int = Field(default=300, ge=30, le=7200)
    db_pool_use_lifo: bool = True

    # Rate limiting.
    rate_limit_enabled: bool = True
    rate_limit_login_per_minute: int = Field(default=10, ge=1)
    rate_limit_login_per_account_per_hour: int = Field(default=30, ge=1)
    rate_limit_register_per_hour: int = Field(default=20, ge=1)
    rate_limit_query_per_minute: int = Field(default=12, ge=1)
    rate_limit_upload_per_minute: int = Field(default=20, ge=1)
    rate_limit_oauth_start_per_minute: int = Field(default=20, ge=1)
    trust_forwarded_for: bool = False

    # Background jobs, Redis & Celery.
    ingestion_mode: Literal["background", "inline"] = "background"
    queue_backend: Literal["database", "celery"] = "database"
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None
    celery_task_time_limit_seconds: int = Field(default=600, ge=30, le=3600)
    celery_task_soft_time_limit_seconds: int = Field(default=540, ge=15, le=3500)
    worker_enabled: bool = True
    worker_threads: int = Field(default=1, ge=1, le=8)
    worker_poll_seconds: float = Field(default=2.0, gt=0.0, le=60.0)
    job_max_attempts: int = Field(default=3, ge=1, le=10)
    job_stale_after_seconds: int = Field(default=900, ge=30)
    maintenance_interval_seconds: int = Field(default=600, ge=10)
    model_warmup_on_startup: bool = False

    @field_validator(
        "api_key_encryption_secret",
        "google_client_id",
        "google_client_secret",
        "neon_database_url",
        "neon_direct_database_url",
        "database_url_unpooled",
        "r2_account_id",
        "r2_access_key_id",
        "r2_secret_access_key",
        "r2_bucket_name",
        "r2_endpoint_url",
        "cloudflare_account_id",
        "cloudflare_api_token",
        "jina_api_key",
        "groq_api_key",
        "cerebras_api_key",
        "gemini_api_key",
        "mistral_api_key",
        "openrouter_api_key",
        "openai_api_key",
        "claude_api_key",
        "grok_api_key",
        "langfuse_public_key",
        "langfuse_secret_key",
        "celery_broker_url",
        "celery_result_backend",
        mode="before",
    )
    @classmethod
    def blank_optional_values_are_unset(cls, value: str | None) -> str | None:
        """Allow the checked-in example env file to leave optional credentials unset."""
        if value is None:
            return None
        value = value.strip()
        return value or None

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        protected_namespaces=("settings_",),
    )

    def _apply_database_url_fallbacks(self) -> None:
        # 1. Explicit DATABASE_URL overrides everything.
        if self.database_url != DEFAULT_DATABASE_URL:
            self.database_url = normalize_database_url(self.database_url)
            return
        # 2. Neon PostgreSQL URL takes precedence over legacy Supabase fields.
        if self.neon_database_url:
            self.database_url = normalize_database_url(self.neon_database_url)
            return
        # 3. Legacy Supabase configuration fallback.
        supabase_values = (
            self.supabase_db_user,
            self.supabase_db_password,
            self.supabase_db_host,
            self.supabase_db_port,
            self.supabase_db_name,
        )
        if not any(value is not None for value in supabase_values):
            return
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

    @model_validator(mode="after")
    def validate_chunk_settings(self) -> "Settings":
        self._apply_database_url_fallbacks()
        if self.document_chunk_overlap >= self.document_chunk_size:
            raise ValueError(
                "document_chunk_overlap must be smaller than document_chunk_size"
            )
        if self.auth_cookie_secure is None:
            self.auth_cookie_secure = self.app_environment == "production"
        if self.app_environment == "production" and not self.auth_cookie_secure:
            raise ValueError("AUTH_COOKIE_SECURE must be true in production")
        if (self.google_client_id is None) != (self.google_client_secret is None):
            raise ValueError("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set together")
        if (
            self.app_environment == "production"
            and self.api_key_encryption_secret is not None
            and self._is_weak_encryption_secret(self.api_key_encryption_secret)
        ):
            raise ValueError(
                "API_KEY_ENCRYPTION_SECRET must not use a default or weak value (min 16 characters) in production"
            )
        return self

    @staticmethod
    def _is_weak_encryption_secret(secret: str | None) -> bool:
        cleaned = (secret or "").strip()
        return not cleaned or len(cleaned) < 16 or cleaned.lower() in _WEAK_BYOK_SECRETS

    def validate_production_startup(self) -> None:
        """Fail fast when production runs without an explicit strong BYOK encryption key."""
        if self.app_environment == "production" and self._is_weak_encryption_secret(
            self.api_key_encryption_secret
        ):
            raise ValueError(
                "API_KEY_ENCRYPTION_SECRET must be set to a strong non-default secret "
                "(at least 16 characters) before starting in production"
            )

    def effective_byok_encryption_secret(self) -> str:
        """Return the active BYOK encryption passphrase, refusing insecure defaults in production."""
        self.validate_production_startup()
        return (self.api_key_encryption_secret or "").strip() or DEV_BYOK_ENCRYPTION_SECRET

    @property
    def migration_database_url(self) -> str:
        """Direct connection URL for DDL/Alembic migrations (bypasses Neon pooler when provided)."""
        direct_url = self.neon_direct_database_url or self.database_url_unpooled
        if direct_url:
            return normalize_database_url(direct_url)
        return self.database_url

    @property
    def effective_celery_broker_url(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def effective_celery_result_backend(self) -> str:
        return self.celery_result_backend or self.redis_url

    @property
    def api_docs_enabled(self) -> bool:
        if self.enable_api_docs is not None:
            return self.enable_api_docs
        return self.app_environment != "production"

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
