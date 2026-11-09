"""Local Qwen cross-encoder reranking with one model instance per process."""

from __future__ import annotations

import math
from functools import lru_cache
from threading import RLock

from app.core.config import Settings
from app.core.errors import AppError
from app.schemas.retrieval import RetrievalCandidate


class RerankerService:
    def __init__(
        self,
        model_name: str,
        *,
        batch_size: int,
        device: str = "auto",
        cache_dir: str | None = None,
    ) -> None:
        self.model_name = model_name
        self.batch_size = batch_size
        self.device = device
        self.cache_dir = cache_dir
        self._model = None
        self._lock = RLock()

    def _load_model(self):
        with self._lock:
            if self._model is not None:
                return self._model
            try:
                from sentence_transformers import CrossEncoder

                kwargs: dict[str, object] = {"trust_remote_code": True}
                if self.device != "auto":
                    kwargs["device"] = self.device
                if self.cache_dir:
                    kwargs["cache_folder"] = self.cache_dir
                self._model = CrossEncoder(self.model_name, **kwargs)
            except Exception as exc:
                raise AppError(
                    "The local reranker is unavailable",
                    status_code=503,
                    code="reranker_unavailable",
                ) from exc
            return self._model

    def rerank(
        self,
        query: str,
        candidates: list[RetrievalCandidate],
    ) -> list[RetrievalCandidate]:
        if not candidates:
            return []
        with self._lock:
            model = self._load_model()
            try:
                raw_scores = model.predict(
                    [(query, candidate.text) for candidate in candidates],
                    batch_size=self.batch_size,
                    show_progress_bar=False,
                )
                scores = [float(score) for score in raw_scores]
            except Exception as exc:
                raise AppError(
                    "The local reranker could not score the retrieved evidence",
                    status_code=503,
                    code="reranker_failed",
                ) from exc
        if len(scores) != len(candidates) or not all(map(math.isfinite, scores)):
            raise AppError(
                "The local reranker returned invalid scores",
                status_code=503,
                code="reranker_invalid_scores",
            )

        scored = [
            candidate.model_copy(update={"rerank_score": score})
            for candidate, score in zip(candidates, scores, strict=True)
        ]
        indexed = list(enumerate(scored))
        indexed.sort(key=lambda item: (-float(item[1].rerank_score), item[0]))
        return [candidate for _, candidate in indexed]


@lru_cache(maxsize=4)
def _cached_reranker(
    model_name: str,
    batch_size: int,
    device: str,
    cache_dir: str | None,
) -> RerankerService:
    return RerankerService(
        model_name,
        batch_size=batch_size,
        device=device,
        cache_dir=cache_dir,
    )


def reranker_service_for(settings: Settings) -> RerankerService:
    return _cached_reranker(
        settings.reranker_model_name,
        settings.reranker_batch_size,
        settings.model_device,
        str(settings.model_cache_dir) if settings.model_cache_dir else None,
    )
