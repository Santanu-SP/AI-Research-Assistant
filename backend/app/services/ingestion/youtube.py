"""YouTube transcript extraction and timestamp-aware chunking."""

from __future__ import annotations

from dataclasses import dataclass
from html import unescape
import re
from typing import Any
from urllib.parse import parse_qs, urlparse
from uuid import UUID
import xml.etree.ElementTree as ET

import httpx

from app.domain.documents import MetadataProvenance
from app.domain.ingestion import CanonicalMetadata, ParsedDocument, ParsedNode
from app.services.ingestion.pipeline import DocumentIngestionError, stable_node_id

VIDEO_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{11}$")
CAPTION_TRACKS_PATTERN = re.compile(r'"captionTracks":\s*(\[.*?\])')
TITLE_PATTERN = re.compile(r"<title>(.*?)</title>", re.IGNORECASE | re.DOTALL)


@dataclass(frozen=True)
class TranscriptSegment:
    text: str
    start: float
    duration: float

    @property
    def end(self) -> float:
        return self.start + max(self.duration, 0.0)


def format_timestamp(seconds: float) -> str:
    total = max(int(round(seconds)), 0)
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def extract_youtube_video_id(url: str) -> str:
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    video_id: str | None = None
    if host in {"youtu.be", "www.youtu.be"}:
        video_id = parsed.path.strip("/").split("/")[0]
    elif host in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        if parsed.path == "/watch":
            qs = parse_qs(parsed.query)
            video_id = (qs.get("v") or [None])[0]
        elif parsed.path.startswith(("/shorts/", "/embed/", "/v/")):
            parts = [p for p in parsed.path.split("/") if p]
            if len(parts) >= 2:
                video_id = parts[1]

    if not video_id or not VIDEO_ID_PATTERN.match(video_id):
        raise DocumentIngestionError(
            "Invalid or unsupported YouTube video URL",
            code="invalid_youtube_url",
            status_code=400,
        )
    return video_id


def chunk_transcript_segments(
    document_id: UUID,
    segments: list[TranscriptSegment],
    *,
    chunk_size_chars: int = 1200,
    overlap_segments: int = 1,
    video_title: str | None = None,
    video_id: str | None = None,
    source_url: str | None = None,
) -> list[ParsedNode]:
    """Group timestamped transcript segments into coherent chunks while preserving timecodes."""
    cleaned = [
        TranscriptSegment(
            text=" ".join(seg.text.split()).strip(),
            start=seg.start,
            duration=seg.duration,
        )
        for seg in segments
        if seg.text and seg.text.strip()
    ]
    if not cleaned:
        raise DocumentIngestionError(
            "No accessible transcript is available for this YouTube video",
            code="youtube_transcript_unavailable",
            status_code=422,
        )

    nodes: list[ParsedNode] = []
    idx = 0
    n = len(cleaned)
    while idx < n:
        bucket: list[TranscriptSegment] = []
        char_count = 0
        cursor = idx
        while cursor < n:
            seg = cleaned[cursor]
            if bucket and char_count + len(seg.text) + 1 > chunk_size_chars:
                break
            bucket.append(seg)
            char_count += len(seg.text) + 1
            cursor += 1

        start_sec = bucket[0].start
        end_sec = bucket[-1].end
        time_label = f"{format_timestamp(start_sec)} - {format_timestamp(end_sec)}"
        chunk_text = " ".join(s.text for s in bucket)
        section_path = [video_title, time_label] if video_title else [time_label]
        node_index = len(nodes)
        meta: dict[str, Any] = {
            "content_kind": "transcript",
            "timestamp_start": round(start_sec, 2),
            "timestamp_end": round(end_sec, 2),
            "time_range": time_label,
        }
        if video_id:
            meta["video_id"] = video_id
        if source_url:
            meta["source_url"] = source_url

        nodes.append(
            ParsedNode(
                node_id=stable_node_id(document_id, node_index, chunk_text),
                text=chunk_text,
                chunk_index=node_index,
                page=node_index + 1,
                page_end=node_index + 1,
                section=time_label,
                section_path=section_path,
                token_count=len(chunk_text.split()),
                metadata=meta,
            )
        )
        if cursor >= n:
            break
        idx = max(idx + 1, cursor - overlap_segments)

    return nodes


class YouTubeIngestionAdapter:
    """Ingests YouTube video transcripts with timestamps and metadata."""

    def __init__(
        self,
        *,
        chunk_size_chars: int = 1200,
        client: httpx.Client | None = None,
        transcript_fetcher: Any | None = None,
    ) -> None:
        self.chunk_size_chars = chunk_size_chars
        self._client = client or httpx.Client(timeout=httpx.Timeout(20.0, connect=5.0))
        self._transcript_fetcher = transcript_fetcher

    def _fetch_segments(self, video_id: str) -> tuple[list[TranscriptSegment], str | None]:
        if self._transcript_fetcher is not None:
            raw_segments, title = self._transcript_fetcher(video_id)
            return (
                [
                    TranscriptSegment(
                        text=str(item["text"]),
                        start=float(item.get("start", 0.0)),
                        duration=float(item.get("duration", 0.0)),
                    )
                    for item in raw_segments
                ],
                title,
            )

        # 1. Try youtube_transcript_api if installed
        try:
            from youtube_transcript_api import YouTubeTranscriptApi  # type: ignore[import-not-found]

            api = YouTubeTranscriptApi()
            if hasattr(api, "fetch"):
                fetched = api.fetch(video_id)
                raw = fetched.to_raw_data() if hasattr(fetched, "to_raw_data") else list(fetched)
            else:
                raw = YouTubeTranscriptApi.get_transcript(video_id)
            segments = [
                TranscriptSegment(
                    text=str(item.get("text", "")),
                    start=float(item.get("start", 0.0)),
                    duration=float(item.get("duration", 0.0)),
                )
                for item in raw
            ]
            return segments, f"YouTube Video ({video_id})"
        except ImportError:
            pass
        except Exception as exc:
            raise DocumentIngestionError(
                "No accessible transcript is available for this YouTube video",
                code="youtube_transcript_unavailable",
                status_code=422,
            ) from exc

        # 2. Built-in HTTP timedtext / watch page caption extraction
        try:
            watch_resp = self._client.get(
                f"https://www.youtube.com/watch?v={video_id}",
                headers={"Accept-Language": "en-US,en;q=0.9"},
            )
            watch_resp.raise_for_status()
            html = watch_resp.text
            title_match = TITLE_PATTERN.search(html)
            title = (
                unescape(title_match.group(1)).replace("- YouTube", "").strip()
                if title_match
                else f"YouTube Video ({video_id})"
            )
            import json

            tracks_match = CAPTION_TRACKS_PATTERN.search(html)
            if not tracks_match:
                raise DocumentIngestionError(
                    "No accessible transcript is available for this YouTube video",
                    code="youtube_transcript_unavailable",
                    status_code=422,
                )
            tracks = json.loads(tracks_match.group(1))
            if not tracks:
                raise DocumentIngestionError(
                    "No accessible transcript is available for this YouTube video",
                    code="youtube_transcript_unavailable",
                    status_code=422,
                )
            base_url = tracks[0].get("baseUrl")
            if not base_url:
                raise DocumentIngestionError(
                    "Transcript track URL missing for YouTube video",
                    code="youtube_transcript_unavailable",
                    status_code=422,
                )
            xml_resp = self._client.get(base_url)
            xml_resp.raise_for_status()
            root = ET.fromstring(xml_resp.text)
            segments: list[TranscriptSegment] = []
            for elem in root.findall(".//text"):
                text_val = unescape(elem.text or "").strip()
                if not text_val:
                    continue
                start_val = float(elem.attrib.get("start", "0") or 0.0)
                dur_val = float(elem.attrib.get("dur", "0") or 0.0)
                segments.append(
                    TranscriptSegment(text=text_val, start=start_val, duration=dur_val)
                )
            return segments, title
        except DocumentIngestionError:
            raise
        except Exception as exc:
            raise DocumentIngestionError(
                "No accessible transcript is available for this YouTube video",
                code="youtube_transcript_unavailable",
                status_code=422,
            ) from exc

    def parse_url(
        self,
        url: str,
        *,
        document_id: UUID,
        ingestion_version: str,
    ) -> ParsedDocument:
        video_id = extract_youtube_video_id(url)
        segments, title = self._fetch_segments(video_id)
        resolved_title = title or f"YouTube Video ({video_id})"
        nodes = chunk_transcript_segments(
            document_id,
            segments,
            chunk_size_chars=self.chunk_size_chars,
            video_title=resolved_title,
            video_id=video_id,
            source_url=url,
        )
        return ParsedDocument(
            document_id=document_id,
            metadata=CanonicalMetadata(
                title=resolved_title,
                values={
                    "video_id": video_id,
                    "source_url": url,
                    "segment_count": len(segments),
                },
                provenance={"title": MetadataProvenance.YOUTUBE},
            ),
            page_count=len(nodes),
            parser_name="youtube-transcript",
            parser_version="1.0",
            ingestion_version=f"{ingestion_version}:youtube",
            nodes=nodes,
        )

    def parse(
        self,
        path,
        *,
        document_id: UUID,
        ingestion_version: str,
    ) -> ParsedDocument:
        url = path.read_text(encoding="utf-8").strip()
        return self.parse_url(url, document_id=document_id, ingestion_version=ingestion_version)

