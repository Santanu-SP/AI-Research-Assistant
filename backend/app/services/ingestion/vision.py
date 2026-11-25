"""Selective Gemini Flash multimodal analyzer for research charts, diagrams, and figures."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from io import BytesIO
import logging
from pathlib import Path
import re
from uuid import UUID

import httpx
import numpy as np
from PIL import Image

from app.core.config import Settings
from app.domain.documents import MetadataProvenance
from app.domain.ingestion import CanonicalMetadata, ParsedDocument, ParsedNode
from app.services.ingestion.pdf import slice_pdf_pages
from app.services.ingestion.pipeline import DocumentIngestionError, stable_node_id

logger = logging.getLogger(__name__)

VISION_SYSTEM_PROMPT = (
    "You are a scientific research assistant analyzing a figure, chart, diagram, or image "
    "from a research source. Provide a concise, factual description of all visible axes, "
    "labels, metrics, trends, structural components, and text. Do not speculate beyond "
    "what is visually present."
)

PDF_OCR_SYSTEM_PROMPT = (
    "You are an exact scientific document OCR engine. Transcribe ALL text from every attached "
    "PDF page in natural reading order without summarizing, paraphrasing, or omitting details. "
    "Preserve headings, equations (in LaTeX notation where appropriate), and render every table "
    "as a clean Markdown table. For multi-page attachments, start each page with an exact marker "
    "line in the form `=== PAGE N ===` matching the 1-based page number within this PDF attachment."
)

_PAGE_MARKER_RE = re.compile(r"^===\s*PAGE\s+(\d+)\s*===$", re.IGNORECASE | re.MULTILINE)


def _map_ocr_output_to_pages(text: str, batch: list[int]) -> dict[int, str]:
    cleaned = text.strip()
    if not cleaned or not batch:
        return {}
    matches = list(_PAGE_MARKER_RE.finditer(cleaned))
    if not matches:
        return {batch[0]: cleaned}

    segments: list[tuple[int, str]] = []
    for idx, match in enumerate(matches):
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(cleaned)
        body = cleaned[start:end].strip()
        if body:
            segments.append((int(match.group(1)), body))
    if not segments:
        return {batch[0]: cleaned}

    marker_nums = {num for num, _ in segments}
    batch_set = set(batch)
    slice_indices = set(range(1, len(batch) + 1))
    use_slice_index = marker_nums.issubset(slice_indices) and not (
        len(batch) > 1 and marker_nums.issubset(batch_set) and batch != list(range(1, len(batch) + 1))
    )

    mapped: dict[int, str] = {}
    for pos, (num, body) in enumerate(segments):
        if use_slice_index and 1 <= num <= len(batch):
            target_page = batch[num - 1]
        elif num in batch_set:
            target_page = num
        elif pos < len(batch):
            target_page = batch[pos]
        else:
            target_page = batch[-1]
        if target_page in mapped:
            mapped[target_page] = f"{mapped[target_page]}\n\n{body}"
        else:
            mapped[target_page] = body
    return mapped


_IMAGE_SKIP_MESSAGES = {
    "low_visual_variance_blank_or_solid": "This image is almost blank or a single colour, so there is nothing to read in it.",
    "image_below_minimum_dimensions": "This image is too small to read. Please upload a larger version.",
    "extreme_aspect_ratio_banner": "This image is a thin strip or banner, not a chart or figure, so it was skipped.",
}


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
            # Flatten transparent diagrams onto white so transparent margins don't read as black.
            if img.mode in {"RGBA", "LA"} or "transparency" in img.info:
                rgba = img.convert("RGBA")
                background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
                composited = Image.alpha_composite(background, rgba).convert("L")
            else:
                composited = img.convert("L")
            grayscale = composited.resize((64, 64))
            arr = np.asarray(grayscale, dtype=np.float32)
            std_dev = float(arr.std())
            if std_dev < min_std_dev:
                return ImageInspection(
                    False, width, height, std_dev, "low_visual_variance_blank_or_solid"
                )
            return ImageInspection(True, width, height, round(std_dev, 2), "informative_figure")
    except Exception as exc:
        raise DocumentIngestionError(
            "This image file could not be opened. It may be damaged or not really an image.",
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

    def _generate_text_with_inline_data(
        self,
        *,
        prompt: str,
        mime_type: str,
        data_bytes: bytes,
        max_output_tokens: int = 512,
        missing_key_message: str = "Reading images needs a Gemini key on the server, and none is set up. Ask the admin to add GEMINI_API_KEY.",
    ) -> str | None:
        if not self.api_key:
            raise DocumentIngestionError(
                missing_key_message,
                code="vision_api_key_missing",
                status_code=503,
            )

        encoded = base64.b64encode(data_bytes).decode("ascii")
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
                "maxOutputTokens": max_output_tokens,
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
                    f"The image-reading service returned an error (HTTP {exc.response.status_code}). Please retry in a few minutes.",
                    code="vision_provider_error",
                    status_code=503,
                ) from exc
            except httpx.HTTPError as exc:
                last_exc = exc
                if idx + 1 < len(candidate_models):
                    continue
                raise DocumentIngestionError(
                    "The image-reading service could not be reached. Please retry in a few minutes.",
                    code="vision_provider_unavailable",
                    status_code=503,
                ) from exc

        if data is None and last_exc is not None:
            raise DocumentIngestionError(
                "The image-reading service could not be reached. Please retry in a few minutes.",
                code="vision_provider_unavailable",
                status_code=503,
            ) from last_exc

        candidates = (data or {}).get("candidates") or []
        if not candidates:
            return None
        parts = candidates[0].get("content", {}).get("parts") or []
        text = "\n".join(p.get("text", "").strip() for p in parts if p.get("text")).strip()
        return text or None

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

        prompt = VISION_SYSTEM_PROMPT
        if context_hint:
            prompt = f"{prompt}\nContext: {context_hint}"

        send_bytes = image_bytes
        send_mime = mime_type
        if mime_type not in {"image/png", "image/jpeg", "image/webp"}:
            with Image.open(BytesIO(image_bytes)) as img:
                png_buf = BytesIO()
                img.convert("RGBA").save(png_buf, format="PNG")
                send_bytes = png_buf.getvalue()
                send_mime = "image/png"

        return self._generate_text_with_inline_data(
            prompt=prompt,
            mime_type=send_mime,
            data_bytes=send_bytes,
            max_output_tokens=512,
            missing_key_message="Reading images needs a Gemini key on the server, and none is set up. Ask the admin to add GEMINI_API_KEY.",
        )

    def ocr_pdf_pages(
        self,
        path: Path,
        page_numbers: list[int],
        *,
        batch_size: int = 4,
        max_batch_bytes: int = 8 * 1024 * 1024,
    ) -> dict[int, str]:
        """Run zero-RAM Gemini Flash OCR on scanned PDF pages in compact slice batches."""
        if not page_numbers:
            return {}
        if not self.api_key:
            raise DocumentIngestionError(
                "This PDF is a scan (pictures of pages), and reading scans needs a Gemini key on the server. "
                "Ask the admin to add GEMINI_API_KEY, or upload a PDF with selectable text.",
                code="vision_api_key_missing",
                status_code=503,
            )

        ordered_pages = sorted(set(page_numbers))
        results: dict[int, str] = {}
        index = 0
        while index < len(ordered_pages):
            batch = ordered_pages[index : index + batch_size]
            pdf_slice = slice_pdf_pages(path, batch)
            while len(pdf_slice) > max_batch_bytes and len(batch) > 1:
                batch = batch[: max(1, len(batch) // 2)]
                pdf_slice = slice_pdf_pages(path, batch)
            index += len(batch)

            prompt = (
                f"{PDF_OCR_SYSTEM_PROMPT}\n"
                f"Attached pages count: {len(batch)} (original document pages: {', '.join(str(p) for p in batch)})."
            )
            text = self._generate_text_with_inline_data(
                prompt=prompt,
                mime_type="application/pdf",
                data_bytes=pdf_slice,
                max_output_tokens=4096,
                missing_key_message="This PDF is a scan (pictures of pages), and reading scans needs a Gemini key on the server. "
                "Ask the admin to add GEMINI_API_KEY, or upload a PDF with selectable text.",
            )
            if not text:
                continue

            results.update(_map_ocr_output_to_pages(text, batch))
        return results

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
                _IMAGE_SKIP_MESSAGES.get(
                    inspection.reason,
                    "This image doesn't look like a chart, figure or diagram, so it was skipped.",
                ),
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
                "The image-reading service could not describe this image.",
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

