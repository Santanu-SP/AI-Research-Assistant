"""YouTube transcript extraction and timestamp-aware chunking."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from html import unescape
import json
import logging
import re
import time
from typing import Any
from urllib.parse import parse_qs, urlparse
from uuid import UUID
import xml.etree.ElementTree as ET

import httpx

from app.domain.documents import MetadataProvenance
from app.domain.ingestion import CanonicalMetadata, ParsedDocument, ParsedNode
from app.services.ingestion.pipeline import DocumentIngestionError, stable_node_id

logger = logging.getLogger(__name__)

VIDEO_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{11}$")
CAPTION_TRACKS_PATTERN = re.compile(r'"captionTracks":\s*(\[.*?\])')
TITLE_PATTERN = re.compile(r"<title>(.*?)</title>", re.IGNORECASE | re.DOTALL)
INNERTUBE_PLAYER_URL = "https://www.youtube.com/youtubei/v1/player"
INNERTUBE_CLIENT_CONTEXT = {
    "context": {
        "client": {
            "clientName": "ANDROID",
            "clientVersion": "20.10.38",
        }
    }
}
INNERTUBE_USER_AGENT = "com.google.android.youtube/20.10.38 (Linux; U; Android 11) gzip"
BOT_CHECK_PATTERN = re.compile(r"confirm you(?:'|\\u0026#39;|&#39;|’)?re not a bot", re.IGNORECASE)
CAPTION_RETRY_DELAYS = (1.5, 4.0, 8.0)


def _usable_tracks(tracks: Any) -> list[dict[str, Any]]:
    if not isinstance(tracks, list):
        return []
    return [track for track in tracks if isinstance(track, dict) and track.get("baseUrl")]


def _order_caption_tracks(tracks: Any) -> list[dict[str, Any]]:
    """English first, human-made before auto-generated, then every other language."""

    def rank(track: dict[str, Any]) -> int:
        is_english = str(track.get("languageCode") or "").lower().startswith("en")
        is_auto = track.get("kind") == "asr"
        return (0 if is_english else 2) + (1 if is_auto else 0)

    return sorted(_usable_tracks(tracks), key=rank)


def _pick_caption_track(tracks: list[dict[str, Any]]) -> dict[str, Any] | None:
    ordered = _order_caption_tracks(tracks)
    return ordered[0] if ordered else None


def _parse_caption_xml(xml_text: str) -> list[TranscriptSegment]:
    if not xml_text or not xml_text.strip():
        return []
    root = ET.fromstring(xml_text)
    segments: list[TranscriptSegment] = []
    for elem in root.findall(".//text"):
        text_val = unescape("".join(elem.itertext())).strip()
        if not text_val:
            continue
        start_val = float(elem.attrib.get("start", "0") or 0.0)
        dur_val = float(elem.attrib.get("dur", "0") or 0.0)
        segments.append(TranscriptSegment(text=text_val, start=start_val, duration=dur_val))
    if segments:
        return segments
    # TimedText format="3" (returned by Innertube ANDROID tracks) stores <p t="ms" d="ms">.
    for elem in root.findall(".//p"):
        text_val = unescape("".join(elem.itertext())).strip()
        if not text_val:
            continue
        start_ms = float(elem.attrib.get("t", "0") or 0.0)
        dur_ms = float(elem.attrib.get("d", "0") or 0.0)
        segments.append(
            TranscriptSegment(
                text=text_val,
                start=start_ms / 1000.0,
                duration=dur_ms / 1000.0,
            )
        )
    return segments


@dataclass(frozen=True)
class TranscriptSegment:
    text: str
    start: float
    duration: float

    @property
    def end(self) -> float:
        return self.start + max(self.duration, 0.0)


def _segments_from_raw(raw: Any) -> list[TranscriptSegment]:
    return [
        TranscriptSegment(
            text=str(item.get("text", "")),
            start=float(item.get("start", 0.0)),
            duration=float(item.get("duration", 0.0)),
        )
        for item in raw or []
        if str(item.get("text", "")).strip()
    ]


class _QuietYtDlpLogger:
    """Keep yt-dlp from printing to stdout; its errors are handled by the caller."""

    def debug(self, msg: str) -> None:
        pass

    def info(self, msg: str) -> None:
        pass

    def warning(self, msg: str) -> None:
        pass

    def error(self, msg: str) -> None:
        logger.info("yt-dlp: %s", msg)


def _order_yt_dlp_tracks(
    subtitles: Any, automatic: Any
) -> list[tuple[str, bool, dict[str, Any]]]:
    """Return (language, auto_generated, format) choices, best first.

    Order: English made by people, English auto-generated (or auto-translated),
    then any other language made by people, then the original auto captions.
    """

    def best_format(formats: Any) -> dict[str, Any] | None:
        if not isinstance(formats, list):
            return None
        by_ext = {f.get("ext"): f for f in formats if isinstance(f, dict) and f.get("url")}
        return by_ext.get("json3") or by_ext.get("srv1")

    choices: list[tuple[int, str, bool, dict[str, Any]]] = []
    for source, auto in ((subtitles, False), (automatic, True)):
        if not isinstance(source, dict):
            continue
        for lang, formats in source.items():
            fmt = best_format(formats)
            if fmt is None or str(lang) == "live_chat":
                continue
            lowered = str(lang).lower()
            english = lowered == "en" or lowered.startswith("en-")
            if auto and not english and not lowered.endswith("-orig"):
                continue  # skip machine translations into other languages
            rank = (0 if english else 2) + (1 if auto else 0)
            choices.append((rank, str(lang), auto, fmt))
    choices.sort(key=lambda item: (item[0], item[1].endswith("-orig") is False))
    return [(lang, auto, fmt) for _rank, lang, auto, fmt in choices]


def _parse_json3(body: str) -> list[TranscriptSegment]:
    try:
        payload = json.loads(body)
    except ValueError:
        return []
    segments: list[TranscriptSegment] = []
    for event in payload.get("events") or []:
        if not isinstance(event, dict):
            continue
        text = "".join(str(seg.get("utf8", "")) for seg in event.get("segs") or [] if isinstance(seg, dict))
        text = " ".join(text.split())
        if not text:
            continue
        segments.append(
            TranscriptSegment(
                text=text,
                start=float(event.get("tStartMs", 0) or 0) / 1000.0,
                duration=float(event.get("dDurationMs", 0) or 0) / 1000.0,
            )
        )
    return segments


def _safe_parse_xml(body: str) -> list[TranscriptSegment]:
    try:
        return _parse_caption_xml(body)
    except ET.ParseError:
        return []


class _FetchProblems:
    """What went wrong while looking for a transcript, so the final error can say why."""

    def __init__(self) -> None:
        self.unavailable_reason: str | None = None
        self.restricted_reason: str | None = None
        self.blocked = False
        self.rate_limited = False
        self.captions_unreadable = False
        self.no_captions = False

    def note_playability(self, status: dict[str, Any]) -> bool:
        """Record a non-OK playability status. Returns True if it explains the failure."""
        state = str(status.get("status") or "").upper()
        reason = str(status.get("reason") or "").strip()
        if not state or state == "OK":
            return False
        lowered = reason.lower()
        if "not a bot" in lowered or "unusual traffic" in lowered:
            self.blocked = True
        elif state == "ERROR" or "private" in lowered or "removed" in lowered or "unavailable" in lowered:
            self.unavailable_reason = reason or "This video is unavailable"
        else:
            self.restricted_reason = reason or state.replace("_", " ").lower()
        return True

    def note_library_error(self, exc: Exception) -> None:
        name = type(exc).__name__
        if name in {"VideoUnavailable", "InvalidVideoId"}:
            self.unavailable_reason = self.unavailable_reason or "This video is unavailable"
        elif name in {"TranscriptsDisabled", "NoTranscriptFound"}:
            self.no_captions = True
        elif name in {"RequestBlocked", "IpBlocked", "TooManyRequests"}:
            self.blocked = True
        elif name in {"AgeRestricted", "VideoUnplayable", "PoTokenRequired"}:
            self.restricted_reason = self.restricted_reason or name
        elif "429" in str(exc):
            self.rate_limited = True

    def note_yt_dlp_error(self, exc: Exception) -> None:
        message = str(exc)
        lowered = message.lower()
        reason = re.sub(r"^(error:\s*)?\[youtube\]\s*[\w-]{11}:\s*", "", message.strip(), flags=re.IGNORECASE)
        reason = reason.split("\n", 1)[0].strip()[:200]
        if "not a bot" in lowered or "429" in lowered or "too many requests" in lowered:
            self.blocked = True
        elif "private video" in lowered or "unavailable" in lowered or "removed" in lowered or "terminated" in lowered:
            self.unavailable_reason = self.unavailable_reason or reason or "This video is unavailable"
        elif "sign in" in lowered or "age" in lowered or "members" in lowered:
            self.restricted_reason = self.restricted_reason or reason
        elif "live event" in lowered or "premiere" in lowered:
            self.restricted_reason = self.restricted_reason or reason

    def to_error(self) -> DocumentIngestionError:
        if self.unavailable_reason:
            return DocumentIngestionError(
                "This YouTube video can't be opened. It may be private, deleted, or the link may "
                f"be wrong. YouTube says: \"{self.unavailable_reason}\"",
                code="youtube_video_unavailable",
                status_code=422,
            )
        if self.restricted_reason:
            return DocumentIngestionError(
                "YouTube only shows this video to signed-in viewers (for example age-restricted "
                f"or members-only videos), so its transcript can't be read. YouTube says: "
                f"\"{self.restricted_reason}\"",
                code="youtube_video_restricted",
                status_code=422,
            )
        if self.blocked or self.rate_limited:
            return DocumentIngestionError(
                "YouTube is temporarily blocking transcript requests from our server (this "
                "sometimes happens to apps hosted in the cloud). The video itself is fine. Please "
                "try again in a few minutes.",
                code="youtube_rate_limited",
                status_code=422,
            )
        if self.captions_unreadable:
            return DocumentIngestionError(
                "YouTube lists captions for this video but did not send them. Please try again "
                "in a few minutes.",
                code="youtube_transcript_unavailable",
                status_code=422,
            )
        return DocumentIngestionError(
            "This YouTube video has no captions (not even auto-generated ones), so there is "
            "no transcript to import.",
            code="youtube_transcript_unavailable",
            status_code=422,
        )


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
        sleep: Callable[[float], None] = time.sleep,
        use_yt_dlp: bool | None = None,
    ) -> None:
        self.chunk_size_chars = chunk_size_chars
        # yt-dlp makes its own network calls, so it is skipped when a test
        # passes in its own HTTP client unless asked for explicitly.
        self._use_yt_dlp = (client is None) if use_yt_dlp is None else use_yt_dlp
        self._client = client or httpx.Client(timeout=httpx.Timeout(20.0, connect=5.0))
        self._transcript_fetcher = transcript_fetcher
        self._sleep = sleep

    def _fetch_segments(self, video_id: str) -> tuple[list[TranscriptSegment], str | None]:
        segments, title, _info = self._fetch_transcript(video_id)
        return segments, title

    def _fetch_transcript(
        self, video_id: str
    ) -> tuple[list[TranscriptSegment], str | None, dict[str, Any]]:
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
                {},
            )

        problems = _FetchProblems()
        for source in (
            self._from_yt_dlp,
            self._from_transcript_library,
            self._from_innertube,
            self._from_watch_page,
        ):
            try:
                result = source(video_id, problems)
            except Exception as exc:  # one broken source must not hide the others
                logger.info("YouTube transcript source %s failed for %s: %s", source.__name__, video_id, exc)
                result = None
            if result is not None:
                segments, title, info = result
                return segments, title or self._lookup_title(video_id), info
        raise problems.to_error()

    def _lookup_title(self, video_id: str) -> str | None:
        try:
            resp = self._client.get(
                "https://www.youtube.com/oembed",
                params={"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"},
            )
            if resp.status_code == 200:
                return str(resp.json().get("title") or "").strip() or None
        except Exception:
            pass
        return None

    # 1. yt-dlp. It keeps up with YouTube's player changes and still gets
    # captions when the plain caption endpoints answer "blocked" or 429.
    def _from_yt_dlp(
        self, video_id: str, problems: _FetchProblems
    ) -> tuple[list[TranscriptSegment], str | None, dict[str, Any]] | None:
        if not self._use_yt_dlp:
            return None
        try:
            import yt_dlp  # type: ignore[import-untyped]
        except ImportError:
            return None

        options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
            "socket_timeout": 15,
            "logger": _QuietYtDlpLogger(),
        }
        with yt_dlp.YoutubeDL(options) as ydl:
            try:
                info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
            except Exception as exc:
                problems.note_yt_dlp_error(exc)
                return None
            if not isinstance(info, dict):
                return None
            title = str(info.get("title") or "").strip() or None
            tracks = _order_yt_dlp_tracks(info.get("subtitles"), info.get("automatic_captions"))
            if not tracks:
                problems.no_captions = True
                return None
            for lang, auto, fmt in tracks[:4]:
                try:
                    body = ydl.urlopen(fmt["url"]).read().decode("utf-8", "replace")
                except Exception as exc:
                    if "429" in str(exc):
                        problems.rate_limited = True
                        break
                    problems.captions_unreadable = True
                    continue
                segments = _parse_json3(body) if fmt.get("ext") == "json3" else _safe_parse_xml(body)
                if segments:
                    base_lang = lang.removesuffix("-orig")
                    return segments, title, {
                        "transcript_language": base_lang or None,
                        "transcript_auto_generated": auto,
                    }
                problems.captions_unreadable = True
        return None

    # 2. youtube_transcript_api, only when it is installed
    def _from_transcript_library(
        self, video_id: str, problems: _FetchProblems
    ) -> tuple[list[TranscriptSegment], str | None, dict[str, Any]] | None:
        try:
            from youtube_transcript_api import YouTubeTranscriptApi  # type: ignore[import-not-found]
        except ImportError:
            return None

        api = YouTubeTranscriptApi()
        try:
            listing = list(api.list(video_id))
        except Exception as exc:
            problems.note_library_error(exc)
            return None
        if not listing:
            problems.no_captions = True
            return None

        def _rank(t: Any) -> int:
            lang = str(getattr(t, "language_code", "")).lower()
            generated = bool(getattr(t, "is_generated", False))
            return (0 if lang.startswith("en") else 2) + (1 if generated else 0)

        for transcript in sorted(listing, key=_rank):
            lang = str(getattr(transcript, "language_code", "") or "")
            info: dict[str, Any] = {
                "transcript_language": lang or None,
                "transcript_auto_generated": bool(getattr(transcript, "is_generated", False)),
            }
            try:
                target = transcript
                if not lang.lower().startswith("en") and getattr(transcript, "is_translatable", False):
                    try:
                        raw = transcript.translate("en").fetch().to_raw_data()
                        segments = _segments_from_raw(raw)
                        if segments:
                            info["transcript_translated_from"] = lang
                            info["transcript_language"] = "en"
                            return segments, None, info
                    except Exception:
                        pass  # keep the original language instead
                raw = target.fetch().to_raw_data()
            except Exception as exc:
                problems.note_library_error(exc)
                continue
            segments = _segments_from_raw(raw)
            if segments:
                return segments, None, info
        return None

    # 3. Innertube ANDROID player API (desktop timedtext baseUrls often return 0 bytes without pot)
    def _from_innertube(
        self, video_id: str, problems: _FetchProblems
    ) -> tuple[list[TranscriptSegment], str | None, dict[str, Any]] | None:
        player_resp = self._client.post(
            INNERTUBE_PLAYER_URL,
            json={**INNERTUBE_CLIENT_CONTEXT, "videoId": video_id},
            headers={"User-Agent": INNERTUBE_USER_AGENT},
        )
        if player_resp.status_code == 429:
            problems.blocked = True
            return None
        if player_resp.status_code != 200:
            return None
        player_data = player_resp.json()
        title = (player_data.get("videoDetails") or {}).get("title") or None
        tracks = (
            (player_data.get("captions") or {})
            .get("playerCaptionsTracklistRenderer", {})
            .get("captionTracks")
            or []
        )
        if not _usable_tracks(tracks):
            if not problems.note_playability(player_data.get("playabilityStatus") or {}):
                problems.no_captions = True
            return None
        return self._read_tracks(tracks, title, problems)

    # 4. Watch-page captionTracks
    def _from_watch_page(
        self, video_id: str, problems: _FetchProblems
    ) -> tuple[list[TranscriptSegment], str | None, dict[str, Any]] | None:
        watch_resp = self._client.get(
            f"https://www.youtube.com/watch?v={video_id}",
            headers={"Accept-Language": "en-US,en;q=0.9"},
        )
        if watch_resp.status_code == 429:
            problems.blocked = True
            return None
        watch_resp.raise_for_status()
        html = watch_resp.text
        title_match = TITLE_PATTERN.search(html)
        title = (
            unescape(title_match.group(1)).replace("- YouTube", "").strip() if title_match else None
        )
        tracks_match = CAPTION_TRACKS_PATTERN.search(html)
        if not tracks_match:
            if BOT_CHECK_PATTERN.search(html):
                problems.blocked = True
            return None
        tracks = json.loads(tracks_match.group(1))
        if not _usable_tracks(tracks):
            return None
        return self._read_tracks(tracks, title, problems)

    def _read_tracks(
        self,
        tracks: list[dict[str, Any]],
        title: str | None,
        problems: _FetchProblems,
    ) -> tuple[list[TranscriptSegment], str | None, dict[str, Any]] | None:
        for track in _order_caption_tracks(tracks):
            lang = str(track.get("languageCode") or "")
            info: dict[str, Any] = {
                "transcript_language": lang or None,
                "transcript_auto_generated": track.get("kind") == "asr",
            }
            base_url = str(track["baseUrl"])
            if not lang.lower().startswith("en") and track.get("isTranslatable"):
                # Best effort: one try at an English translation, otherwise keep the original.
                translated = self._get_caption_segments(f"{base_url}&tlang=en", problems, retries=0)
                if translated:
                    info["transcript_translated_from"] = lang
                    info["transcript_language"] = "en"
                    return translated, title, info
            segments = self._get_caption_segments(base_url, problems)
            if segments is None:
                break  # still rate-limited after retries; other tracks will be too
            if segments:
                return segments, title, info
        return None

    def _get_caption_segments(
        self, url: str, problems: _FetchProblems, *, retries: int = 3
    ) -> list[TranscriptSegment] | None:
        """Fetch one caption track. YouTube often answers 429 for a moment, so retry briefly.

        Returns None when every try was rate-limited.
        """
        for attempt in range(retries + 1):
            resp = self._client.get(url)
            if resp.status_code == 200:
                try:
                    segments = _parse_caption_xml(resp.text)
                except ET.ParseError:
                    segments = []
                if not segments:
                    problems.captions_unreadable = True
                return segments
            if resp.status_code != 429:
                problems.captions_unreadable = True
                return []
            problems.rate_limited = True
            if attempt < retries:
                self._sleep(CAPTION_RETRY_DELAYS[min(attempt, len(CAPTION_RETRY_DELAYS) - 1)])
        return None

    def parse_url(
        self,
        url: str,
        *,
        document_id: UUID,
        ingestion_version: str,
    ) -> ParsedDocument:
        video_id = extract_youtube_video_id(url)
        segments, title, transcript_info = self._fetch_transcript(video_id)
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
                    **{k: v for k, v in transcript_info.items() if v is not None},
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

