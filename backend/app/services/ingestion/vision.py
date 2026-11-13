"""Selective Gemini Flash multimodal analyzer for research charts, diagrams, and figures."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from io import BytesIO
import logging
from pathlib import Path
from uuid import UUID

import httpx
import numpy as np
from PIL import Image

from app.core.config import Settings
from app.domain.documents import MetadataProvenance
from app.domain.ingestion import CanonicalMetadata, ParsedDocument, ParsedNode
from app.services.ingestion.pipeline import DocumentIngestionError, stable_node_id

logger = logging.getLogger(__name__)

VISION_SYSTEM_PROMPT = (
    "You are a scientific research assistant analyzing a figure, chart, diagram, or image "
    "from a research source. Provide a concise, factual description of all visible axes, "
    "labels, metrics, trends, structural components, and text. Do not speculate beyond "
    "what is visually present."
)


@dataclass(frozen=True)
class ImageInspection:
    should_analyze: bool
    width: int
    height: int
    std_dev: float
    reason: str


def inspect_image_for_vision(
    image_bytes: bytes,
    *,
    min_dimension: int = 160,
    min_std_dev: float = 8.0,
    max_aspect_ratio: float = 8.0,
) -> ImageInspection:
    """Decide whether an image contains enough visual information to warrant a Vision API call.

    Filters out tiny icons, decorative dividers, blank pages, and solid-color banners.
    """
    try:
        with Image.open(BytesIO(image_bytes)) as img:
            width, height = img.size
            if width < min_dimension or height < min_dimension:
                return ImageInspection(
                    False, width, height, 0.0, "image_below_minimum_dimensions"
                )
            aspect = max(width / max(height, 1), height / max(width, 1))
            if aspect > max_aspect_ratio:
                return ImageInspection(
                    False, width, height, 0.0, "extreme_aspect_ratio_banner"
                )
            grayscale = img.convert("L").resize((64, 64))
            arr = np.asarray(grayscale, dtype=np.float32)
            std_dev = float(arr.std())
            if std_dev < min_std_dev:
                return ImageInspection(
                    False, width, height, std_dev, "low_visual_variance_blank_or_solid"
                )
            return ImageInspection(True, width, height, round(std_dev, 2), "informative_figure")
    except Exception as exc:
        raise DocumentIngestionError(
            "The image could not be decoded for analysis",
            code="invalid_image_content",
        ) from exc


class GeminiVisionAnalyzer:
    """Calls Google Gemini Flash multimodal endpoint for selective figure/chart understanding."""

    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        model_name: str = "gemini-3.8-flash",
        fallback_model_name: str | None = "gemini-3.1-flash-lite",
        min_dimension: int = 160,
        timeout_seconds: float = 45.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.fallback_model_name = fallback_model_name
        self.min_dimension = min_dimension
        self._client = client or httpx.Client(timeout=httpx.Timeout(timeout_seconds, connect=10.0))

    def _call_model(self, model_name: str, payload: dict[str, object]) -> dict[str, object]:
        url = f"{self.base_url}/models/{model_name}:generateContent"
        response = self._client.post(
            url,
            headers={"x-goog-api-key": self.api_key or ""},
            json=payload,
        )
        response.raise_for_status()
        return response.json()

    def analyze_image_bytes(
        self,
        image_bytes: bytes,
        mime_type: str = "image/png",
        *,
        context_hint: str | None = None,
    ) -> str | None:
        inspection = inspect_image_for_vision(
            image_bytes, min_dimension=self.min_dimension
        )
        if not inspection.should_analyze:
            logger.debug(
                "Skipping uninformative image for vision model",
                extra={"reason": inspection.reason, "width": inspection.width, "height": inspection.height},
            )
            return None

        if not self.api_key:
            raise DocumentIngestionError(
                "GEMINI_API_KEY is required for image and diagram analysis",
                code="vision_api_key_missing",
                status_code=503,
            )

        prompt = VISION_SYSTEM_PROMPT
        if context_hint:
            prompt = f"{prompt}\nContext: {context_hint}"

        encoded = base64.b64encode(image_bytes).decode("ascii")
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": encoded,
                            }
                        },
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 512,
            },
        }
        candidate_models = [self.model_name]
        if self.fallback_model_name and self.fallback_model_name != self.model_name:
            candidate_models.append(self.fallback_model_name)

        data: dict[str, object] | None = None
        last_exc: Exception | None = None
        for idx, model_name in enumerate(candidate_models):
            try:
                data = self._call_model(model_name, payload)
                break
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                can_retry_fallback = idx + 1 < len(candidate_models) and (
                    exc.response.status_code == 429 or exc.response.status_code >= 500
                )
                if can_retry_fallback:
                    logger.warning(
                        "Gemini vision model %s returned HTTP %s; falling back to %s",
                        model_name,
                        exc.response.status_code,
                        candidate_models[idx + 1],
                    )
                    continue
                raise DocumentIngestionError(
                    f"Gemini Vision API returned HTTP {exc.response.status_code}",
                    code="vision_provider_error",
                    status_code=503,
                ) from exc
            except httpx.HTTPError as exc:
                last_exc = exc
                if idx + 1 < len(candidate_models):
                    continue
                raise DocumentIngestionError(
                    "Gemini Vision API is unreachable",
                    code="vision_provider_unavailable",
                    status_code=503,
                ) from exc

        if data is None and last_exc is not None:
            raise DocumentIngestionError(
                "Gemini Vision API is unreachable",
                code="vision_provider_unavailable",
                status_code=503,
            ) from last_exc

        candidates = (data or {}).get("candidates") or []
        if not candidates:
            return None
        parts = candidates[0].get("content", {}).get("parts") or []
        text = "\n".join(p.get("text", "").strip() for p in parts if p.get("text")).strip()
        return text or None

    def parse_image_document(
        self,
        path: Path,
        *,
        document_id: UUID,
        ingestion_version: str,
        mime_type: str = "image/png",
        original_name: str | None = None,
    ) -> ParsedDocument:
        image_bytes = path.read_bytes()
        inspection = inspect_image_for_vision(
            image_bytes, min_dimension=self.min_dimension
        )
        if not inspection.should_analyze:
            raise DocumentIngestionError(
                f"Image does not meet minimum research figure requirements ({inspection.reason})",
                code="uninformative_image",
                status_code=422,
            )
        description = self.analyze_image_bytes(
            image_bytes,
            mime_type=mime_type,
            context_hint=original_name or path.name,
        )
        if not description:
            raise DocumentIngestionError(
                "Vision model returned an empty description for the image",
                code="vision_empty_description",
                status_code=422,
            )
        title = original_name or path.stem
        node = ParsedNode(
            node_id=stable_node_id(document_id, 0, description),
            text=description,
            chunk_index=0,
            page=1,
            page_end=1,
            section="Visual Analysis",
            section_path=[title, "Visual Analysis"],
            token_count=len(description.split()),
            metadata={
                "content_kind": "figure_description",
                "image_width": inspection.width,
                "image_height": inspection.height,
                "vision_model": self.model_name,
                "original_image": path.name,
            },
        )
        return ParsedDocument(
            document_id=document_id,
            metadata=CanonicalMetadata(
                title=title,
                values={
                    "width": inspection.width,
                    "height": inspection.height,
                    "vision_model": self.model_name,
                },
                provenance={"title": MetadataProvenance.GEMINI_VISION},
            ),
            page_count=1,
            parser_name="gemini-vision",
            parser_version=self.model_name,
            ingestion_version=f"{ingestion_version}:gemini-vision",
            nodes=[node],
        )


def vision_analyzer_for(
    settings: Settings,
    *,
    client: httpx.Client | None = None,
) -> GeminiVisionAnalyzer:
    return GeminiVisionAnalyzer(
        api_key=settings.gemini_api_key,
        base_url=settings.gemini_base_url,
        model_name=settings.gemini_model_name,
        fallback_model_name=settings.gemini_fallback_model_name,
        min_dimension=settings.vision_min_image_dimension,
        client=client,
    )

