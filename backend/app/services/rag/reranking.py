"""Cross-encoder reranking supporting Local Qwen, Jina Reranker API, and Cloudflare BGE Reranker."""

from __future__ import annotations

import logging
import math
from functools import lru_cache
from threading import RLock

import httpx

from app.core.config import Settings
from app.core.errors import AppError
from app.schemas.retrieval import RetrievalCandidate

logger = logging.getLogger(__name__)


def _apply_scores_and_sort(
    candidates: list[RetrievalCandidate],
    scores: list[float],
) -> list[RetrievalCandidate]:
    if len(scores) != len(candidates) or not all(map(math.isfinite, scores)):
        raise AppError(
            "The reranker returned invalid scores",
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


class RerankerService:
    def __init__(
        self,
        model_name: str,
        *,
        batch_size: int,
        device: str = "auto",
        cache_dir: str | None = None,
        revision: str | None = None,
        trust_remote_code: bool = False,
    ) -> None:
        self.model_name = model_name
        self.revision = revision
        self.trust_remote_code = trust_remote_code
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

                kwargs: dict[str, object] = {"trust_remote_code": self.trust_remote_code}
                if self.revision:
                    kwargs["revision"] = self.revision
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
        return _apply_scores_and_sort(candidates, scores)


class JinaRerankerService:
    """Jina Reranker API service (e.g., jina-reranker-v2-base-multilingual)."""

    def __init__(
        self,
        *,
        api_key: str,
        model_name: str = "jina-reranker-v2-base-multilingual",
        timeout_seconds: float = 20.0,
        client: httpx.Client | None = None,
        fallback_reranker: object | None = None,
    ) -> None:
        self.api_key = api_key
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds
        self._client = client
        self._fallback_reranker = fallback_reranker

    def rerank(
        self,
        query: str,
        candidates: list[RetrievalCandidate],
    ) -> list[RetrievalCandidate]:
        if not candidates:
            return []
        if not self.api_key:
            if self._fallback_reranker is not None:
                return self._fallback_reranker.rerank(query, candidates)
            raise AppError(
                "JINA_API_KEY is required for Jina Reranker",
                status_code=503,
                code="reranker_unavailable",
            )

        payload = {
            "model": self.model_name,
            "query": query,
            "documents": [candidate.text for candidate in candidates],
            "top_n": len(candidates),
            "return_documents": False,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            if self._client is not None:
                response = self._client.post(
                    "https://api.jina.ai/v1/rerank",
                    headers=headers,
                    json=payload,
                    timeout=self.timeout_seconds,
                )
            else:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    response = client.post(
                        "https://api.jina.ai/v1/rerank",
                        headers=headers,
                        json=payload,
                    )
            response.raise_for_status()
            data = response.json()
            results = data.get("results", [])
            scores = [0.0] * len(candidates)
            for item in results:
                idx = int(item["index"])
                if 0 <= idx < len(candidates):
                    scores[idx] = float(item["relevance_score"])
            return _apply_scores_and_sort(candidates, scores)
        except Exception as exc:
            logger.warning("Jina reranker failed: %s", exc)
            if self._fallback_reranker is not None:
                return self._fallback_reranker.rerank(query, candidates)
            raise AppError(
                "The Jina reranker could not score the retrieved evidence",
                status_code=503,
                code="reranker_failed",
            ) from exc


class CloudflareBGERerankerService:
    """Cloudflare Workers AI BGE Reranker (@cf/baai/bge-reranker-base)."""

    def __init__(
        self,
        *,
        account_id: str,
        api_token: str,
        model_name: str = "@cf/baai/bge-reranker-base",
        timeout_seconds: float = 20.0,
        client: httpx.Client | None = None,
        fallback_reranker: object | None = None,
    ) -> None:
        self.account_id = account_id
        self.api_token = api_token
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds
        self._client = client
        self._fallback_reranker = fallback_reranker

    def rerank(
        self,
        query: str,
        candidates: list[RetrievalCandidate],
    ) -> list[RetrievalCandidate]:
        if not candidates:
            return []
        if not self.account_id or not self.api_token:
            if self._fallback_reranker is not None:
                return self._fallback_reranker.rerank(query, candidates)
            raise AppError(
                "Cloudflare credentials are required for Cloudflare BGE Reranker",
                status_code=503,
                code="reranker_unavailable",
            )

        url = f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/ai/run/{self.model_name}"
        payload = {
            "query": query,
            "contexts": [{"text": candidate.text} for candidate in candidates],
        }
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }
        try:
            if self._client is not None:
                response = self._client.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=self.timeout_seconds,
                )
            else:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            body = response.json()
            result_data = body.get("result", body)
            items = (
                result_data.get("response", [])
                if isinstance(result_data, dict)
                else result_data
            )
            scores = [0.0] * len(candidates)
            for idx, item in enumerate(items):
                target_idx = int(item.get("id", idx)) if isinstance(item, dict) else idx
                score_val = float(item.get("score", 0.0)) if isinstance(item, dict) else float(item)
                if 0 <= target_idx < len(candidates):
                    scores[target_idx] = score_val
            return _apply_scores_and_sort(candidates, scores)
        except Exception as exc:
            logger.warning("Cloudflare BGE reranker failed: %s", exc)
            if self._fallback_reranker is not None:
                return self._fallback_reranker.rerank(query, candidates)
            raise AppError(
                "The Cloudflare BGE reranker could not score the retrieved evidence",
                status_code=503,
                code="reranker_failed",
            ) from exc


class LexicalFallbackReranker:
    """Zero-cost deterministic fallback when a remote free-tier reranker hits quota or network errors."""

    def rerank(
        self,
        query: str,
        candidates: list[RetrievalCandidate],
    ) -> list[RetrievalCandidate]:
        query_terms = {
            token
            for token in query.lower().split()
            if len(token) > 2
        }
        scores: list[float] = []
        for candidate in candidates:
            base = float(candidate.hybrid_score or 0.0)
            if not query_terms:
                scores.append(base)
                continue
            text_lower = candidate.text.lower()
            overlap = sum(1 for term in query_terms if term in text_lower) / len(query_terms)
            scores.append(round(base + overlap, 6))
        return _apply_scores_and_sort(candidates, scores)


@lru_cache(maxsize=4)
def _cached_reranker(
    model_name: str,
    batch_size: int,
    device: str,
    cache_dir: str | None,
    revision: str | None = None,
    trust_remote_code: bool = False,
) -> RerankerService:
    return RerankerService(
        model_name,
        batch_size=batch_size,
        device=device,
        cache_dir=cache_dir,
        revision=revision,
        trust_remote_code=trust_remote_code,
    )


def reranker_service_for(settings: Settings):
    provider = settings.reranker_provider.strip().lower()
    if provider == "jina" and settings.jina_api_key:
        return JinaRerankerService(
            api_key=settings.jina_api_key,
            model_name=settings.jina_reranker_model,
            fallback_reranker=LexicalFallbackReranker(),
        )
    if provider == "cloudflare":
        return CloudflareBGERerankerService(
            account_id=settings.cloudflare_account_id or "",
            api_token=settings.cloudflare_api_token or "",
            model_name=settings.cloudflare_reranker_model,
            fallback_reranker=LexicalFallbackReranker(),
        )
    return _cached_reranker(
        settings.reranker_model_name,
        settings.reranker_batch_size,
        settings.model_device,
        str(settings.model_cache_dir) if settings.model_cache_dir else None,
        settings.reranker_model_revision,
        settings.model_trust_remote_code,
    )
