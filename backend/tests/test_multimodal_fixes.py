from io import BytesIO
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
import httpx
from PIL import Image, ImageDraw
from pptx import Presentation
from pptx.util import Inches
import pytest

from app.domain.documents import DocumentStatus
from app.services.ingestion.audio import GroqAudioTranscriber
from app.services.ingestion.office_html import parse_pptx_document
from app.services.ingestion.video import ExtractedKeyframe, VideoIngestionAdapter
from app.services.ingestion.vision import GeminiVisionAnalyzer, inspect_image_for_vision
from app.services.ingestion.youtube import YouTubeIngestionAdapter


def test_browser_generic_and_alias_mime_types_accepted_while_mismatches_fail(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.domain.documents import MetadataProvenance
    from app.domain.ingestion import CanonicalMetadata, ParsedDocument, ParsedNode
    from app.services.ingestion.pipeline import stable_node_id

    monkeypatch.setattr(
        "app.services.ingestion.audio.GroqAudioTranscriber.parse",
        lambda self, path, *, document_id, ingestion_version, original_name=None: ParsedDocument(
            document_id=document_id,
            metadata=CanonicalMetadata(
                title=original_name or "lecture.m4a",
                values={},
                provenance={"title": MetadataProvenance.WHISPER},
            ),
            page_count=1,
            parser_name="groq-whisper",
            parser_version="whisper-large-v3-turbo",
            ingestion_version=f"{ingestion_version}:whisper",
            nodes=[
                ParsedNode(
                    node_id=stable_node_id(document_id, 0, "Audio transcript sample."),
                    text="Audio transcript sample.",
                    chunk_index=0,
                    page=1,
                    page_end=1,
                    token_count=3,
                    metadata={},
                )
            ],
        ),
    )

    # Generic application/octet-stream (commonly sent by macOS/Brave for .mkv / .m4a / .pptx)
    res_m4a = client.post(
        "/api/v1/documents",
        files={"file": ("lecture.m4a", b"\x00\x00\x00\x18ftypM4A ", "application/octet-stream")},
    )
    assert res_m4a.status_code == 201
    assert res_m4a.json()["type"] == "audio"
    assert res_m4a.json()["mimeType"] == "audio/mp4"

    # Explicit mismatched MIME still rejected with 400 document_type_mismatch
    res_bad = client.post(
        "/api/v1/documents",
        files={"file": ("lecture.m4a", b"not audio", "text/plain")},
    )
    assert res_bad.status_code == 400
    assert res_bad.json()["error"]["code"] == "document_type_mismatch"


def test_pptx_parser_extracts_grouped_shape_text(tmp_path: Path) -> None:
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    group = slide.shapes.add_group_shape()
    textbox = group.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1))
    textbox.text_frame.text = "Grouped Architecture Node inside Diagram"
    pptx_path = tmp_path / "grouped.pptx"
    prs.save(pptx_path)

    parsed = parse_pptx_document(
        pptx_path,
        document_id=uuid4(),
        ingestion_version="v1",
    )
    combined = "\n".join(node.text for node in parsed.nodes)
    assert "Grouped Architecture Node inside Diagram" in combined


def test_youtube_innertube_android_format3_transcript_preferred_english() -> None:
    seen_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        if "youtubei/v1/player" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "videoDetails": {"title": "Attention Lecture"},
                    "captions": {
                        "playerCaptionsTracklistRenderer": {
                            "captionTracks": [
                                {"languageCode": "ar", "baseUrl": "https://yt.test/ar"},
                                {"languageCode": "en", "kind": "asr", "baseUrl": "https://yt.test/en-asr"},
                                {"languageCode": "en", "baseUrl": "https://yt.test/en-manual"},
                            ]
                        }
                    },
                },
            )
        if str(request.url) == "https://yt.test/en-manual":
            return httpx.Response(
                200,
                text=(
                    '<?xml version="1.0" encoding="utf-8" ?>'
                    '<timedtext format="3"><body>'
                    '<p t="1500" d="2500"><s>Multi-head </s><s>attention scales well.</s></p>'
                    "</body></timedtext>"
                ),
            )
        return httpx.Response(404)

    adapter = YouTubeIngestionAdapter(
        client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    parsed = adapter.parse_url(
        "https://www.youtube.com/watch?v=aircAruvnKk",
        document_id=uuid4(),
        ingestion_version="v1",
    )
    assert parsed.metadata.title == "Attention Lecture"
    assert "Multi-head attention scales well." in parsed.nodes[0].text
    assert any(u == "https://yt.test/en-manual" for u in seen_urls)


def test_silent_video_falls_back_to_visual_keyframes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    video_path = tmp_path / "silent_recording.mp4"
    video_path.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    frame_path = tmp_path / "frame_000.png"
    img = Image.new("RGB", (240, 240), (255, 255, 255))
    ImageDraw.Draw(img).line([(20, 20), (220, 220)], fill=(0, 0, 0), width=4)
    img.save(frame_path)

    transcriber = GroqAudioTranscriber(api_key="groq-test")
    vision = GeminiVisionAnalyzer(
        api_key="gm-test",
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda _req: httpx.Response(
                    200,
                    json={
                        "candidates": [
                            {"content": {"parts": [{"text": "Benchmark screen showing 98% accuracy."}]}}
                        ]
                    },
                )
            )
        ),
    )
    adapter = VideoIngestionAdapter(transcriber=transcriber, vision_analyzer=vision)

    def no_audio(self, _vp: Path, _out: Path) -> Path:
        from app.services.ingestion.pipeline import DocumentIngestionError

        raise DocumentIngestionError(
            "Could not extract an audio track from the uploaded video",
            code="video_audio_extraction_failed",
            status_code=422,
        )

    monkeypatch.setattr(VideoIngestionAdapter, "extract_audio", no_audio)
    monkeypatch.setattr(
        VideoIngestionAdapter,
        "extract_selective_keyframes",
        lambda self, _vp, _dir: [ExtractedKeyframe(path=frame_path, timestamp_seconds=0.0)],
    )

    parsed = adapter.parse(
        video_path,
        document_id=uuid4(),
        ingestion_version="v1",
        original_name="silent_recording.mp4",
    )
    assert len(parsed.nodes) == 1
    assert "98% accuracy" in parsed.nodes[0].text


def test_transparent_png_inspection_and_tiff_normalization() -> None:
    transparent = Image.new("RGBA", (220, 220), (0, 0, 0, 0))
    ImageDraw.Draw(transparent).rectangle([30, 30, 190, 190], outline=(10, 10, 10, 255), width=6)
    buf = BytesIO()
    transparent.save(buf, format="PNG")
    inspection = inspect_image_for_vision(buf.getvalue())
    assert inspection.should_analyze is True

    tiff_buf = BytesIO()
    white_bg = Image.new("RGBA", transparent.size, (255, 255, 255, 255))
    Image.alpha_composite(white_bg, transparent).convert("RGB").save(tiff_buf, format="TIFF")
    sent_mimes: list[str] = []

    def vision_handler(request: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(request.content.decode("utf-8"))
        sent_mimes.append(body["contents"][0]["parts"][1]["inline_data"]["mime_type"])
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": "TIFF diagram summary."}]}}]},
        )

    vision = GeminiVisionAnalyzer(
        api_key="gm-key",
        client=httpx.Client(transport=httpx.MockTransport(vision_handler)),
    )
    desc = vision.analyze_image_bytes(tiff_buf.getvalue(), mime_type="image/tiff")
    assert desc == "TIFF diagram summary."
    assert sent_mimes == ["image/png"]


def test_duplicate_url_returns_document_id_and_failed_url_is_retryable(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.ingestion.web.validate_public_url",
        lambda url, **_kw: url,
    )

    def fail_once(self, url: str, *, document_id, ingestion_version):
        from app.services.ingestion.pipeline import DocumentIngestionError

        raise DocumentIngestionError("Temporary fetch error", code="website_unreachable", status_code=422)

    monkeypatch.setattr("app.services.ingestion.web.WebsiteIngestionAdapter.parse_url", fail_once)
    failed = client.post("/api/v1/documents/url", json={"url": "https://example.org/test-article"})
    assert failed.status_code == 422

    docs_res = client.get("/api/v1/documents")
    doc_id = docs_res.json()["items"][0]["id"]
    assert docs_res.json()["items"][0]["status"] == DocumentStatus.FAILED.value

    # Delete local descriptor to simulate R2/remote worker retry without local copy
    for p in Path(client.app.state.settings.document_upload_dir).glob("*.web"):
        p.unlink()

    from app.domain.documents import MetadataProvenance
    from app.domain.ingestion import CanonicalMetadata, ParsedDocument, ParsedNode
    from app.services.ingestion.pipeline import stable_node_id

    monkeypatch.setattr(
        "app.services.ingestion.web.WebsiteIngestionAdapter.parse_url",
        lambda self, url, *, document_id, ingestion_version: ParsedDocument(
            document_id=document_id,
            metadata=CanonicalMetadata(title="Example Article", values={}, provenance={"title": MetadataProvenance.EXTRACTED}),
            page_count=1,
            parser_name="beautifulsoup-html",
            parser_version="1.0",
            ingestion_version=f"{ingestion_version}:web",
            nodes=[
                ParsedNode(
                    node_id=stable_node_id(document_id, 0, "Extracted webpage text."),
                    text="Extracted webpage text.",
                    chunk_index=0,
                    page=1,
                    page_end=1,
                    token_count=3,
                    metadata={},
                )
            ],
        ),
    )

    retried = client.post(f"/api/v1/documents/{doc_id}/retry")
    assert retried.status_code == 201
    assert retried.json()["status"] == "indexed"

    dupe = client.post("/api/v1/documents/url", json={"url": "https://example.org/test-article"})
    assert dupe.status_code == 409
    assert dupe.json()["error"]["code"] == "duplicate_document"
    assert dupe.json()["error"]["details"]["documentId"] == doc_id
