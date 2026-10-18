"""Lazy local Qwen embedding runtime used by ingestion and retrieval."""

from functools import lru_cache
import logging
from typing import Protocol

from app.core.config import Settings
from app.core.errors import AppError

logger = logging.getLogger(__name__)


class EmbeddingService(Protocol):
    """Protocol for generating normalized dense vector embeddings."""

    dimension: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, query: str) -> list[float]: ...


def _resolve_compute_device(configured_device: str, torch_module: object) -> str:
    """Resolve 'auto' to 'cuda', 'mps', or 'cpu' based on local hardware."""
    if configured_device != "auto":
        return configured_device
    if torch_module.cuda.is_available():  # type: ignore[attr-defined]
        return "cuda"
    mps_backend = getattr(torch_module.backends, "mps", None)  # type: ignore[attr-defined]
    if mps_backend and mps_backend.is_available():
        return "mps"
    return "cpu"


class QwenEmbeddingService:
    """Loads SentenceTransformers once, only when embeddings are requested."""

    def __init__(self, settings: Settings) -> None:
        self.dimension = settings.embedding_dimension
        self.batch_size = settings.embedding_batch_size
        try:
            import torch
            from sentence_transformers import SentenceTransformer

            device = _resolve_compute_device(settings.model_device, torch)
            cache_folder = (
                str(settings.model_cache_dir) if settings.model_cache_dir else None
            )
            self._model = SentenceTransformer(
                settings.embedding_model_name,
                cache_folder=cache_folder,
                device=device,
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

    @property
    def _batch_size(self) -> int:
        return self.__dict__.get("batch_size", 8)

    def _encode(self, texts: list[str]) -> list[list[float]]:
        """Encode a list of texts into L2-normalized float vectors."""
        try:
            vectors = self._model.encode(
                texts,
                batch_size=self._batch_size,
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
        if any(len(vector) != self.dimension for vector in result):
            raise AppError(
                "Embedding model returned an unexpected dimension",
                status_code=500,
                code="embedding_dimension_mismatch",
            )
        return result

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Generate normalized embeddings for a batch of document chunks."""
        return self._encode(texts)

    def embed_query(self, query: str) -> list[float]:
        """Generate a normalized embedding for a single user search query."""
        return self._encode([query])[0]


@lru_cache(maxsize=1)
def get_embedding_service(
    model_name: str,
    device: str,
    cache_dir: str | None,
    batch_size: int,
    dimension: int,
) -> QwenEmbeddingService:
    """Return a cached singleton of ``QwenEmbeddingService``."""
    settings = Settings(
        embedding_model_name=model_name,
        model_device=device,
        model_cache_dir=cache_dir,
        embedding_batch_size=batch_size,
        embedding_dimension=dimension,
    )
    service = QwenEmbeddingService(settings)
    service.batch_size = batch_size
    return service


def embedding_service_for(settings: Settings) -> EmbeddingService:
    """Resolve the configured ``EmbeddingService`` instance for ``settings``."""
    return get_embedding_service(
        settings.embedding_model_name,
        settings.model_device,
        str(settings.model_cache_dir) if settings.model_cache_dir else None,
        settings.embedding_batch_size,
        settings.embedding_dimension,
    )