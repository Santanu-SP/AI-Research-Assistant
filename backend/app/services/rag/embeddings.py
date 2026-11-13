"""Local Qwen and Cloudflare Workers AI embedding runtimes used by ingestion and retrieval."""

from collections import OrderedDict
from collections.abc import Callable
from functools import lru_cache
import logging
import math
from threading import RLock
from typing import Protocol

import httpx

from app.core.config import Settings
from app.core.errors import AppError
from app.providers.base import post_json_with_client

logger = logging.getLogger(__name__)


class EmbeddingService(Protocol):
    dimension: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, query: str) -> list[float]: ...


def _embedding_device(requested: str) -> str:
    if requested != "auto":
        return requested

    import torch

    if torch.cuda.is_available():
        return "cuda"
    metal = getattr(torch.backends, "mps", None)
    if metal is not None and metal.is_available():
        return "mps"
    return "cpu"


def _normalize_vector(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm <= 0.0:
        return vec
    return [float(v / norm) for v in vec]


class _QueryEmbeddingCache:
    """Thread-safe bounded LRU cache for repeated or identical query strings."""

    def __init__(self, maxsize: int = 256) -> None:
        self.maxsize = max(0, maxsize)
        self._entries: OrderedDict[str, tuple[float, ...]] = OrderedDict()
        self._lock = RLock()

    def get_or_compute(
        self,
        query: str,
        compute: Callable[[str], list[float]],
    ) -> list[float]:
        if self.maxsize <= 0:
            return compute(query)
        with self._lock:
            cached = self._entries.get(query)
            if cached is not None:
                self._entries.move_to_end(query)
                return list(cached)
        vector = compute(query)
        with self._lock:
            self._entries[query] = tuple(vector)
            self._entries.move_to_end(query)
            while len(self._entries) > self.maxsize:
                self._entries.popitem(last=False)
        return vector


class QwenEmbeddingService:
    """Loads SentenceTransformers once, only when embeddings are requested."""

    def __init__(self, settings: Settings) -> None:
        self.dimension = settings.embedding_dimension
        self.batch_size = settings.embedding_batch_size
        self.model_name = settings.embedding_model_name
        self.model_version = settings.embedding_model_revision
        self._query_cache = _QueryEmbeddingCache(settings.query_embedding_cache_size)
        try:
            from sentence_transformers import SentenceTransformer

            device = _embedding_device(settings.model_device)
            cache_folder = (
                str(settings.model_cache_dir) if settings.model_cache_dir else None
            )
            init_kwargs: dict[str, object] = {
                "cache_folder": cache_folder,
                "device": device,
                "revision": settings.embedding_model_revision,
                "trust_remote_code": settings.model_trust_remote_code,
            }
            try:
                # Prefer cached local weights first to skip HuggingFace Hub network HEAD checks.
                self._model = SentenceTransformer(
                    settings.embedding_model_name,
                    **init_kwargs,
                    local_files_only=True,
                )
            except Exception:
                self._model = SentenceTransformer(
                    settings.embedding_model_name,
                    **init_kwargs,
                )
            logger.info(
                "Loaded embedding model %s on %s",
                settings.embedding_model_name,
                device,
            )
        except Exception as exc:
            raise AppError(
                "The local embedding model is unavailable",
                status_code=503,
                code="embedding_model_unavailable",
            ) from exc

    def _encode(self, texts: list[str]) -> list[list[float]]:
        try:
            vectors = self._model.encode(
                texts,
                batch_size=self.batch_size,
                normalize_embeddings=True,
                convert_to_numpy=True,
            )
        except Exception as exc:
            raise AppError(
                "Embedding generation failed",
                status_code=503,
                code="embedding_generation_failed",
            ) from exc

        result = [vector.astype(float).tolist() for vector in vectors]
        unexpected = any(len(vector) != self.dimension for vector in result)
        if unexpected:
            raise AppError(
                "Embedding model returned an unexpected dimension",
                status_code=500,
                code="embedding_dimension_mismatch",
            )
        return result

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._encode(texts)

    def embed_query(self, query: str) -> list[float]:
        return self._query_cache.get_or_compute(query, lambda q: self._encode([q])[0])


class CloudflareWorkersAIEmbeddingService:
    """Server-side Cloudflare Workers AI embedding service (@cf/baai/bge-m3)."""

    def __init__(
        self,
        *,
        account_id: str | None,
        api_token: str | None,
        model_name: str = "@cf/baai/bge-m3",
        dimension: int = 1024,
        batch_size: int = 16,
        timeout_seconds: float = 30.0,
        client: httpx.Client | None = None,
        query_cache_size: int = 256,
    ) -> None:
        self.account_id = (account_id or "").strip()
        self.api_token = (api_token or "").strip()
        self.model_name = model_name
        self.model_version = "cloudflare-workers-ai-v1"
        self.dimension = dimension
        self.batch_size = max(1, batch_size)
        self.timeout_seconds = timeout_seconds
        self._client = client
        self._query_cache = _QueryEmbeddingCache(query_cache_size)

    def _encode(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if any(not isinstance(t, str) or not t.strip() for t in texts):
            raise AppError(
                "Embedding input texts must be non-empty strings",
                status_code=422,
                code="invalid_embedding_input",
            )
        if not self.account_id or not self.api_token:
            raise AppError(
                "CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN are required for Cloudflare embeddings",
                status_code=503,
                code="cloudflare_embedding_credentials_missing",
            )

        url = f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/ai/run/{self.model_name}"
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }
        all_vectors: list[list[float]] = []
        for idx in range(0, len(texts), self.batch_size):
            batch = texts[idx : idx + self.batch_size]
            try:
                response = post_json_with_client(
                    self._client,
                    url,
                    headers=headers,
                    json={"text": batch},
                    timeout_seconds=self.timeout_seconds,
                )
                response.raise_for_status()
                payload = response.json()
            except httpx.HTTPStatusError as exc:
                raise AppError(
                    f"Cloudflare Workers AI embedding failed with HTTP {exc.response.status_code}",
                    status_code=503,
                    code="embedding_generation_failed",
                ) from exc
            except (httpx.HTTPError, ValueError) as exc:
                raise AppError(
                    "Cloudflare Workers AI embedding service is unavailable",
                    status_code=503,
                    code="embedding_model_unavailable",
                ) from exc

            result_block = payload.get("result") or {}
            raw_vectors = result_block.get("data")
            if not isinstance(raw_vectors, list) or len(raw_vectors) != len(batch):
                raise AppError(
                    "Cloudflare Workers AI returned an invalid embedding batch",
                    status_code=500,
                    code="embedding_batch_mismatch",
                )
            for vec in raw_vectors:
                if not isinstance(vec, list) or len(vec) != self.dimension:
                    raise AppError(
                        "Embedding model returned an unexpected dimension",
                        status_code=500,
                        code="embedding_dimension_mismatch",
                    )
                floats = [float(x) for x in vec]
                if not all(math.isfinite(x) for x in floats):
                    raise AppError(
                        "Embedding model returned non-finite values",
                        status_code=500,
                        code="embedding_generation_failed",
                    )
                all_vectors.append(_normalize_vector(floats))
        return all_vectors

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._encode(texts)

    def embed_query(self, query: str) -> list[float]:
        return self._query_cache.get_or_compute(query, lambda q: self._encode([q])[0])


def active_embedding_model_identity(
    settings: Settings,
    service: EmbeddingService | None = None,
) -> tuple[str, str]:
    """Return (model_name, model_version) for recording on indexed documents."""
    if service is not None:
        name = getattr(service, "model_name", None)
        version = getattr(service, "model_version", None)
        if name and version:
            return str(name), str(version)
    if settings.embedding_provider == "cloudflare":
        return settings.cloudflare_embedding_model, "cloudflare-workers-ai-v1"
    return settings.embedding_model_name, settings.embedding_model_revision


@lru_cache(maxsize=2)
def get_embedding_service(
    model_name: str,
    revision: str,
    trust_remote_code: bool,
    device: str,
    cache_dir: str | None,
    batch_size: int,
    dimension: int,
    query_cache_size: int = 256,
) -> QwenEmbeddingService:
    runtime_settings = Settings(
        embedding_model_name=model_name,
        embedding_model_revision=revision,
        model_trust_remote_code=trust_remote_code,
        model_device=device,
        model_cache_dir=cache_dir,
        embedding_batch_size=batch_size,
        embedding_dimension=dimension,
        query_embedding_cache_size=query_cache_size,
    )
    return QwenEmbeddingService(runtime_settings)


@lru_cache(maxsize=2)
def get_cloudflare_embedding_service(
    account_id: str | None,
    api_token: str | None,
    model_name: str,
    dimension: int,
    batch_size: int,
    query_cache_size: int = 256,
) -> CloudflareWorkersAIEmbeddingService:
    return CloudflareWorkersAIEmbeddingService(
        account_id=account_id,
        api_token=api_token,
        model_name=model_name,
        dimension=dimension,
        batch_size=batch_size,
        query_cache_size=query_cache_size,
    )


def embedding_service_for(settings: Settings) -> EmbeddingService:
    if settings.embedding_provider == "cloudflare":
        return get_cloudflare_embedding_service(
            settings.cloudflare_account_id,
            settings.cloudflare_api_token,
            settings.cloudflare_embedding_model,
            settings.embedding_dimension,
            settings.embedding_batch_size,
            settings.query_embedding_cache_size,
        )
    cache_dir = (
        str(settings.model_cache_dir) if settings.model_cache_dir else None
    )
    return get_embedding_service(
        settings.embedding_model_name,
        settings.embedding_model_revision,
        settings.model_trust_remote_code,
        settings.model_device,
        cache_dir,
        settings.embedding_batch_size,
        settings.embedding_dimension,
        settings.query_embedding_cache_size,
    )
