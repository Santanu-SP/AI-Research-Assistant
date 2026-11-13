"""Asynchronous-friendly audio transcription service using Groq Whisper with optional Gemini free-tier fallback."""

from __future__ import annotations

import base64
import logging
from pathlib import Path
from uuid import UUID

import httpx

from app.core.config import Settings
from app.domain.documents import MetadataProvenance
from app.domain.ingestion import CanonicalMetadata, ParsedDocument, ParsedNode
from app.services.ingestion.pipeline import DocumentIngestionError, stable_node_id
from app.services.ingestion.youtube import (
    TranscriptSegment,
    chunk_transcript_segments,
)

logger = logging.getLogger(__name__)

SUPPORTED_WHISPER_MODELS = frozenset({"whisper-large-v3", "whisper-large-v3-turbo"})
GROQ_FREE_MAX_AUDIO_BYTES = 25 * 1024 * 1024
GEMINI_MAX_INLINE_AUDIO_BYTES = 15 * 1024 * 1024

AUDIO_MIME_TYPES = {
    ".mp3": "audio/mpeg",
    ".mpga": "audio/mpeg",
    ".mpeg": "audio/mpeg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".mp4": "audio/mp4",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".webm": "audio/webm",
}


class GroqAudioTranscriber:
    """Transcribes audio files using Groq Whisper with optional Gemini Flash audio fallback."""

    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str = "https://api.groq.com/openai/v1",
        model_name: str = "whisper-large-v3-turbo",
        chunk_size_chars: int = 1200,
        timeout_seconds: float = 120.0,
        max_groq_file_bytes: int = GROQ_FREE_MAX_AUDIO_BYTES,
        gemini_api_key: str | None = None,
        gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        gemini_model_name: str = "gemini-3.8-flash",
        client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model_name = (
            model_name if model_name in SUPPORTED_WHISPER_MODELS else "whisper-large-v3-turbo"
        )
        self.chunk_size_chars = chunk_size_chars
        self.max_groq_file_bytes = max_groq_file_bytes
        self.gemini_api_key = gemini_api_key
        self.gemini_base_url = gemini_base_url.rstrip("/")
        self.gemini_model_name = gemini_model_name
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(timeout_seconds, connect=10.0)
        )

    def _transcribe_with_gemini(self, path: Path) -> list[TranscriptSegment]:
        mime_type = AUDIO_MIME_TYPES.get(path.suffix.lower(), "audio/mpeg")
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        url = f"{self.gemini_base_url}/models/{self.gemini_model_name}:generateContent"
        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": (
                                "Transcribe the spoken speech in this audio recording faithfully and verbatim. "
                                "Return plain transcript text only without commentary or timestamps."
                            )
                        },
                        {
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": encoded,
                            }
                        },
                    ]
                }
            ],
            "generationConfig": {"temperature": 0.0, "maxOutputTokens": 4096},
        }
        try:
            response = self._client.post(
                url,
                headers={"x-goog-api-key": self.gemini_api_key or ""},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as exc:
            raise DocumentIngestionError(
                f"Gemini audio fallback failed with HTTP {exc.response.status_code}",
                code="audio_transcription_failed",
                status_code=503 if exc.response.status_code >= 500 else 422,
            ) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise DocumentIngestionError(
                "Gemini audio transcription fallback is unavailable",
                code="audio_transcription_unavailable",
                status_code=503,
            ) from exc

        candidates = data.get("candidates") or []
        parts = candidates[0].get("content", {}).get("parts") if candidates else []
        transcript_text = "\n".join(
            str(p.get("text", "")).strip() for p in (parts or []) if p.get("text")
        ).strip()
        if not transcript_text:
            raise DocumentIngestionError(
                "The audio recording contains no recognizable speech",
                code="empty_audio_transcript",
                status_code=422,
            )
        return [TranscriptSegment(text=transcript_text, start=0.0, duration=0.0)]

    def transcribe_file(self, path: Path) -> list[TranscriptSegment]:
        if not path.is_file() or path.stat().st_size == 0:
            raise DocumentIngestionError(
                "Audio file is missing or empty",
                code="empty_audio_file",
                status_code=400,
            )
        file_size = path.stat().st_size

        if not self.api_key:
            if self.gemini_api_key and file_size <= GEMINI_MAX_INLINE_AUDIO_BYTES:
                return self._transcribe_with_gemini(path)
            raise DocumentIngestionError(
                "GROQ_API_KEY (or GEMINI_API_KEY for audio <= 15 MB) is required for audio transcription",
                code="audio_transcription_key_missing",
                status_code=503,
            )

        if file_size > self.max_groq_file_bytes:
            raise DocumentIngestionError(
                "Audio exceeds Groq Free tier 25 MB limit; compress to 16 kHz mono MP3/FLAC or split into chunks",
                code="audio_file_too_large",
                status_code=413,
            )

        url = f"{self.base_url}/audio/transcriptions"
        try:
            with path.open("rb") as audio_handle:
                files = {"file": (path.name, audio_handle, "application/octet-stream")}
                data = {
                    "model": self.model_name,
                    "response_format": "verbose_json",
                    "temperature": "0",
                }
                response = self._client.post(
                    url,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    files=files,
                    data=data,
                )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 413:
                raise DocumentIngestionError(
                    "Audio exceeds Groq Free tier 25 MB upload limit; compress to 16 kHz mono MP3/FLAC or split",
                    code="audio_file_too_large",
                    status_code=413,
                ) from exc
            if (
                self.gemini_api_key
                and file_size <= GEMINI_MAX_INLINE_AUDIO_BYTES
                and (exc.response.status_code == 429 or exc.response.status_code >= 500)
            ):
                logger.warning(
                    "Groq Whisper returned HTTP %s; falling back to Gemini audio transcription",
                    exc.response.status_code,
                )
                return self._transcribe_with_gemini(path)
            raise DocumentIngestionError(
                f"Groq Whisper transcription failed with HTTP {exc.response.status_code}",
                code="audio_transcription_failed",
                status_code=503 if exc.response.status_code >= 500 else 422,
            ) from exc
        except (httpx.HTTPError, ValueError) as exc:
            if self.gemini_api_key and file_size <= GEMINI_MAX_INLINE_AUDIO_BYTES:
                logger.warning("Groq Whisper unavailable (%s); falling back to Gemini audio transcription", exc)
                return self._transcribe_with_gemini(path)
            raise DocumentIngestionError(
                "Groq Whisper transcription service is unavailable",
                code="audio_transcription_unavailable",
                status_code=503,
            ) from exc

        raw_segments = payload.get("segments") or []
        segments: list[TranscriptSegment] = []
        for seg in raw_segments:
            text_val = str(seg.get("text", "")).strip()
            if not text_val:
                continue
            start_val = float(seg.get("start", 0.0))
            end_val = float(seg.get("end", start_val))
            segments.append(
                TranscriptSegment(
                    text=text_val,
                    start=start_val,
                    duration=max(0.0, end_val - start_val),
                )
            )

        if not segments:
            full_text = str(payload.get("text", "")).strip()
            if full_text:
                duration = float(payload.get("duration", 0.0) or 0.0)
                segments.append(
                    TranscriptSegment(text=full_text, start=0.0, duration=duration)
                )

        if not segments:
            raise DocumentIngestionError(
                "The audio recording contains no recognizable speech",
                code="empty_audio_transcript",
                status_code=422,
            )
        return segments

    def parse(
        self,
        path: Path,
        *,
        document_id: UUID,
        ingestion_version: str,
        original_name: str | None = None,
    ) -> ParsedDocument:
        segments = self.transcribe_file(path)
        title = original_name or path.stem
        nodes: list[ParsedNode] = chunk_transcript_segments(
            document_id,
            segments,
            chunk_size_chars=self.chunk_size_chars,
            video_title=title,
        )
        for node in nodes:
            node.metadata["audio_model"] = self.model_name
            node.metadata["original_file"] = path.name

        return ParsedDocument(
            document_id=document_id,
            metadata=CanonicalMetadata(
                title=title,
                values={
                    "whisper_model": self.model_name,
                    "segment_count": len(segments),
                    "original_file": path.name,
                },
                provenance={"title": MetadataProvenance.WHISPER},
            ),
            page_count=len(nodes),
            parser_name="groq-whisper",
            parser_version=self.model_name,
            ingestion_version=f"{ingestion_version}:whisper",
            nodes=nodes,
        )


def audio_transcriber_for(
    settings: Settings,
    *,
    client: httpx.Client | None = None,
) -> GroqAudioTranscriber:
    return GroqAudioTranscriber(
        api_key=settings.groq_api_key,
        base_url=settings.groq_base_url,
        model_name=settings.groq_whisper_model,
        chunk_size_chars=min(settings.document_chunk_size, 1800),
        gemini_api_key=settings.gemini_api_key,
        gemini_base_url=settings.gemini_base_url,
        gemini_model_name=settings.gemini_model_name,
        client=client,
    )

