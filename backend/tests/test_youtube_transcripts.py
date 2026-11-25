from __future__ import annotations

import sys
import types
from collections.abc import Callable
from typing import Any
from uuid import uuid4

import httpx
import pytest

from app.services.ingestion.pipeline import DocumentIngestionError
from app.services.ingestion.youtube import (
    YouTubeIngestionAdapter,
    _pick_caption_track,
    extract_youtube_video_id,
)

VIDEO_URL = "https://youtu.be/abcdefghijk?si=shareTracking1"


def _caption_xml(text: str) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8" ?><timedtext format="3"><body>'
        f'<p t="1000" d="2000">{text}</p></body></timedtext>'
    )


def _player(status: str = "OK", reason: str = "", tracks: list[dict[str, Any]] | None = None) -> dict:
    data: dict[str, Any] = {
        "playabilityStatus": {"status": status, **({"reason": reason} if reason else {})},
        "videoDetails": {"title": "Test Lecture"},
    }
    if tracks is not None:
        data["captions"] = {"playerCaptionsTracklistRenderer": {"captionTracks": tracks}}
    return data


def _adapter(
    handler: Callable[[httpx.Request], httpx.Response],
    sleeps: list[float] | None = None,
) -> YouTubeIngestionAdapter:
    return YouTubeIngestionAdapter(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=(sleeps.append if sleeps is not None else (lambda _s: None)),
    )


def _parse(adapter: YouTubeIngestionAdapter):
    return adapter.parse_url(VIDEO_URL, document_id=uuid4(), ingestion_version="v1")


def _routes(player: dict, captions: dict[str, Any], watch_html: str = "<html></html>"):
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "youtubei/v1/player" in url:
            return httpx.Response(200, json=player)
        if url.startswith("https://www.youtube.com/watch"):
            return httpx.Response(200, text=watch_html)
        answer = captions.get(url)
        if callable(answer):
            return answer()
        if isinstance(answer, httpx.Response):
            return answer
        if isinstance(answer, str):
            return httpx.Response(200, text=answer)
        return httpx.Response(404)

    return handler


@pytest.fixture(autouse=True)
def _no_transcript_library(monkeypatch: pytest.MonkeyPatch) -> None:
    # Keep these tests offline and independent of whether the optional library is installed.
    monkeypatch.setitem(sys.modules, "youtube_transcript_api", None)


def test_short_link_with_share_tracking_is_parsed() -> None:
    assert extract_youtube_video_id(VIDEO_URL) == "abcdefghijk"


def test_unavailable_video_says_so() -> None:
    handler = _routes(_player("ERROR", "This video is unavailable"), {})
    with pytest.raises(DocumentIngestionError) as err:
        _parse(_adapter(handler))
    assert err.value.code == "youtube_video_unavailable"
    assert "private, deleted, or the link may be wrong" in str(err.value)


def test_bot_check_is_reported_as_server_block() -> None:
    handler = _routes(_player("LOGIN_REQUIRED", "Sign in to confirm you’re not a bot"), {})
    with pytest.raises(DocumentIngestionError) as err:
        _parse(_adapter(handler))
    assert err.value.code == "youtube_rate_limited"
    assert "our server" in str(err.value)


def test_bot_check_on_watch_page_is_reported_as_server_block() -> None:
    handler = _routes(
        _player("OK", tracks=[]),
        {},
        watch_html="<html>Sign in to confirm you&#39;re not a bot</html>",
    )
    with pytest.raises(DocumentIngestionError) as err:
        _parse(_adapter(handler))
    assert err.value.code == "youtube_rate_limited"


def test_age_restricted_video_is_explained() -> None:
    handler = _routes(_player("LOGIN_REQUIRED", "Sign in to confirm your age"), {})
    with pytest.raises(DocumentIngestionError) as err:
        _parse(_adapter(handler))
    assert err.value.code == "youtube_video_restricted"
    assert "confirm your age" in str(err.value)


def test_video_without_any_captions_is_explained() -> None:
    handler = _routes(_player("OK", tracks=[]), {})
    with pytest.raises(DocumentIngestionError) as err:
        _parse(_adapter(handler))
    assert err.value.code == "youtube_transcript_unavailable"
    assert "no captions" in str(err.value)


def test_auto_generated_non_english_track_is_kept_when_no_translation() -> None:
    tracks = [{"baseUrl": "https://yt.test/hi", "languageCode": "hi", "kind": "asr", "isTranslatable": True}]
    handler = _routes(_player(tracks=tracks), {"https://yt.test/hi": _caption_xml("नमस्ते बच्चों")})
    parsed = _parse(_adapter(handler))
    assert "नमस्ते बच्चों" in parsed.nodes[0].text
    assert parsed.metadata.values["transcript_language"] == "hi"
    assert parsed.metadata.values["transcript_auto_generated"] is True
    assert "transcript_translated_from" not in parsed.metadata.values


def test_non_english_track_is_translated_to_english_when_youtube_offers_it() -> None:
    tracks = [{"baseUrl": "https://yt.test/hi", "languageCode": "hi", "kind": "asr", "isTranslatable": True}]
    handler = _routes(
        _player(tracks=tracks),
        {
            "https://yt.test/hi": _caption_xml("नमस्ते"),
            "https://yt.test/hi&tlang=en": _caption_xml("Hello children"),
        },
    )
    parsed = _parse(_adapter(handler))
    assert "Hello children" in parsed.nodes[0].text
    assert parsed.metadata.values["transcript_language"] == "en"
    assert parsed.metadata.values["transcript_translated_from"] == "hi"


def test_caption_rate_limit_is_retried() -> None:
    answers = iter([httpx.Response(429), httpx.Response(429), httpx.Response(200, text=_caption_xml("Works now"))])
    tracks = [{"baseUrl": "https://yt.test/en", "languageCode": "en"}]
    sleeps: list[float] = []
    handler = _routes(_player(tracks=tracks), {"https://yt.test/en": lambda: next(answers)})
    parsed = _parse(_adapter(handler, sleeps))
    assert "Works now" in parsed.nodes[0].text
    assert len(sleeps) == 2


def test_caption_rate_limit_that_does_not_clear_gives_clear_error() -> None:
    tracks = [
        {"baseUrl": "https://yt.test/en", "languageCode": "en"},
        {"baseUrl": "https://yt.test/de", "languageCode": "de"},
    ]
    sleeps: list[float] = []
    handler = _routes(
        _player(tracks=tracks),
        {"https://yt.test/en": httpx.Response(429), "https://yt.test/de": httpx.Response(429)},
    )
    with pytest.raises(DocumentIngestionError) as err:
        _parse(_adapter(handler, sleeps))
    assert err.value.code == "youtube_rate_limited"
    assert sum(sleeps) < 30


def test_empty_track_falls_through_to_next_track() -> None:
    tracks = [
        {"baseUrl": "https://yt.test/en", "languageCode": "en"},
        {"baseUrl": "https://yt.test/de", "languageCode": "de"},
    ]
    handler = _routes(
        _player(tracks=tracks),
        {"https://yt.test/en": "", "https://yt.test/de": _caption_xml("Guten Tag")},
    )
    parsed = _parse(_adapter(handler))
    assert "Guten Tag" in parsed.nodes[0].text
    assert parsed.metadata.values["transcript_language"] == "de"


def test_english_auto_captions_beat_other_language_manual_captions() -> None:
    tracks = [
        {"baseUrl": "https://yt.test/de", "languageCode": "de"},
        {"baseUrl": "https://yt.test/en-auto", "languageCode": "en", "kind": "asr"},
        {"baseUrl": "https://yt.test/en", "languageCode": "en"},
    ]
    assert _pick_caption_track(tracks)["baseUrl"] == "https://yt.test/en"
    assert _pick_caption_track(tracks[:2])["baseUrl"] == "https://yt.test/en-auto"


def test_transcript_library_error_no_longer_stops_other_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    class VideoUnplayable(Exception):
        pass

    class FakeApi:
        def list(self, video_id: str):
            raise VideoUnplayable("blocked here")

    fake = types.ModuleType("youtube_transcript_api")
    fake.YouTubeTranscriptApi = FakeApi  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "youtube_transcript_api", fake)

    tracks = [{"baseUrl": "https://yt.test/en", "languageCode": "en"}]
    handler = _routes(_player(tracks=tracks), {"https://yt.test/en": _caption_xml("Still imported")})
    parsed = _parse(_adapter(handler))
    assert "Still imported" in parsed.nodes[0].text


# --- yt-dlp source ---------------------------------------------------------

_JSON3 = (
    '{"events": [{"tStartMs": 0, "dDurationMs": 2000, "segs": [{"utf8": "Neural networks "}, {"utf8": "learn."}]},'
    ' {"tStartMs": 2000, "dDurationMs": 1500, "segs": [{"utf8": "\\n"}]},'
    ' {"tStartMs": 3500, "dDurationMs": 1000, "segs": [{"utf8": "Layers stack."}]}]}'
)


def _fake_yt_dlp(monkeypatch: pytest.MonkeyPatch, *, info: dict | None = None, error: str | None = None,
                 bodies: dict[str, str] | None = None) -> list[str]:
    opened: list[str] = []

    class FakeYDL:
        def __init__(self, options: dict) -> None:
            self.options = options

        def __enter__(self) -> "FakeYDL":
            return self

        def __exit__(self, *exc: object) -> None:
            return None

        def extract_info(self, url: str, download: bool = False) -> dict:
            if error:
                raise RuntimeError(error)
            return info or {}

        def urlopen(self, url: str):
            opened.append(url)
            body = (bodies or {}).get(url)
            if body is None:
                raise RuntimeError("HTTP Error 404")
            return types.SimpleNamespace(read=lambda: body.encode())

    monkeypatch.setitem(sys.modules, "yt_dlp", types.SimpleNamespace(YoutubeDL=FakeYDL))
    monkeypatch.setitem(sys.modules, "youtube_transcript_api", None)
    return opened


def _no_network(request: httpx.Request) -> httpx.Response:
    return httpx.Response(404)


def _yt_dlp_adapter() -> YouTubeIngestionAdapter:
    return YouTubeIngestionAdapter(
        client=httpx.Client(transport=httpx.MockTransport(_no_network)),
        sleep=lambda _s: None,
        use_yt_dlp=True,
    )


def test_yt_dlp_reads_english_auto_captions(monkeypatch: pytest.MonkeyPatch) -> None:
    opened = _fake_yt_dlp(
        monkeypatch,
        info={
            "title": "Neural nets, explained",
            "subtitles": {"hi": [{"ext": "json3", "url": "https://yt.test/hi"}]},
            "automatic_captions": {
                "en": [{"ext": "srv1", "url": "https://yt.test/en-srv1"}, {"ext": "json3", "url": "https://yt.test/en"}],
                "fr": [{"ext": "json3", "url": "https://yt.test/fr-translated"}],
            },
        },
        bodies={"https://yt.test/en": _JSON3},
    )
    parsed = _parse(_yt_dlp_adapter())
    assert opened == ["https://yt.test/en"]
    assert parsed.metadata.title == "Neural nets, explained"
    assert parsed.metadata.values["transcript_auto_generated"] is True
    assert "Neural networks learn." in parsed.nodes[0].text
    assert "Layers stack." in parsed.nodes[0].text


def test_yt_dlp_uses_other_language_when_no_english(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_yt_dlp(
        monkeypatch,
        info={"title": "Hindi talk", "subtitles": {}, "automatic_captions": {"hi-orig": [{"ext": "json3", "url": "https://yt.test/hi"}]}},
        bodies={"https://yt.test/hi": _JSON3},
    )
    parsed = _parse(_yt_dlp_adapter())
    assert parsed.metadata.values["transcript_language"] == "hi"


def test_yt_dlp_unavailable_video_gives_a_clear_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_yt_dlp(monkeypatch, error="ERROR: [youtube] abcdefghijk: This video is unavailable")
    with pytest.raises(DocumentIngestionError) as caught:
        _parse(_yt_dlp_adapter())
    assert caught.value.code == "youtube_video_unavailable"
    assert "This video is unavailable" in str(caught.value)


def test_yt_dlp_bot_check_reports_blocking(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_yt_dlp(monkeypatch, error="ERROR: [youtube] abcdefghijk: Sign in to confirm you're not a bot")
    with pytest.raises(DocumentIngestionError) as caught:
        _parse(_yt_dlp_adapter())
    assert caught.value.code == "youtube_rate_limited"


def test_yt_dlp_is_skipped_when_a_test_client_is_passed(monkeypatch: pytest.MonkeyPatch) -> None:
    opened = _fake_yt_dlp(monkeypatch, info={"automatic_captions": {"en": [{"ext": "json3", "url": "https://yt.test/en"}]}},
                          bodies={"https://yt.test/en": _JSON3})
    adapter = YouTubeIngestionAdapter(client=httpx.Client(transport=httpx.MockTransport(_no_network)))
    with pytest.raises(DocumentIngestionError):
        _parse(adapter)
    assert opened == []
