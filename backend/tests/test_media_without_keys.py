"""Audio, video and image imports, tested with fake AI services so no real keys are used."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
import shutil
import subprocess
from uuid import uuid4

import httpx
from PIL import Image
import pytest

from app.services.ingestion.audio import GroqAudioTranscriber
from app.services.ingestion.pipeline import DocumentIngestionError
from app.services.ingestion.video import VideoIngestionAdapter
from app.services.ingestion.vision import GeminiVisionAnalyzer


def _fake_groq(request: httpx.Request) -> httpx.Response:
    assert request.url.path.endswith("/audio/transcriptions")
    return httpx.Response(
        200,
        json={
            "text": "Photosynthesis turns light into sugar.",
            "segments": [
                {"start": 0.0, "end": 2.5, "text": "Photosynthesis turns light"},
                {"start": 2.5, "end": 4.0, "text": " into sugar."},
            ],
        },
    )


def _fake_gemini(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={"candidates": [{"content": {"parts": [{"text": "A bar chart of yearly rainfall, highest in July."}]}}]},
    )


def test_audio_without_any_key_explains_what_is_missing(tmp_path: Path) -> None:
    audio = tmp_path / "talk.mp3"
    audio.write_bytes(b"ID3fake-audio")
    transcriber = GroqAudioTranscriber(api_key=None, gemini_api_key=None)
    with pytest.raises(DocumentIngestionError) as caught:
        transcriber.parse(audio, document_id=uuid4(), ingestion_version="v1")
    assert caught.value.code == "audio_transcription_key_missing"
    assert "speech-to-text key" in str(caught.value)


def test_audio_is_transcribed_with_a_fake_groq_service(tmp_path: Path) -> None:
    audio = tmp_path / "talk.mp3"
    audio.write_bytes(b"ID3fake-audio")
    transcriber = GroqAudioTranscriber(
        api_key="test-key-not-real", client=httpx.Client(transport=httpx.MockTransport(_fake_groq))
    )
    parsed = transcriber.parse(audio, document_id=uuid4(), ingestion_version="v1", original_name="talk.mp3")
    text = " ".join(node.text for node in parsed.nodes)
    assert "Photosynthesis turns light" in text and "into sugar." in text


def test_blank_image_is_skipped_with_a_plain_reason(tmp_path: Path) -> None:
    buffer = BytesIO()
    Image.new("RGB", (400, 300), (255, 255, 255)).save(buffer, format="PNG")
    image = tmp_path / "blank.png"
    image.write_bytes(buffer.getvalue())
    analyzer = GeminiVisionAnalyzer(api_key="test-key-not-real")
    with pytest.raises(DocumentIngestionError) as caught:
        analyzer.parse_image_document(image, document_id=uuid4(), ingestion_version="v1")
    assert caught.value.code == "uninformative_image"
    assert "almost blank" in str(caught.value)


def test_chart_image_is_described_with_a_fake_gemini_service(tmp_path: Path) -> None:
    img = Image.new("RGB", (400, 300), (255, 255, 255))
    for x in range(40, 360, 40):
        for y in range(300 - x // 2, 300):
            for dx in range(20):
                img.putpixel((x + dx, y), (30, 90, 160))
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    image = tmp_path / "chart.png"
    image.write_bytes(buffer.getvalue())
    analyzer = GeminiVisionAnalyzer(
        api_key="test-key-not-real", client=httpx.Client(transport=httpx.MockTransport(_fake_gemini))
    )
    parsed = analyzer.parse_image_document(image, document_id=uuid4(), ingestion_version="v1")
    assert "yearly rainfall" in " ".join(node.text for node in parsed.nodes)


def test_image_without_key_explains_what_is_missing(tmp_path: Path) -> None:
    img = Image.effect_noise((400, 300), 80).convert("RGB")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    image = tmp_path / "photo.png"
    image.write_bytes(buffer.getvalue())
    with pytest.raises(DocumentIngestionError) as caught:
        GeminiVisionAnalyzer(api_key=None).parse_image_document(image, document_id=uuid4(), ingestion_version="v1")
    assert caught.value.code == "vision_api_key_missing"
    assert "Gemini key" in str(caught.value)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is not installed")
def test_video_sound_is_extracted_and_transcribed_with_a_fake_service(tmp_path: Path) -> None:
    video = tmp_path / "clip.mp4"
    subprocess.run(
        [
            "ffmpeg", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "color=c=blue:size=320x240:rate=10:duration=2",
            "-f", "lavfi", "-i", "sine=frequency=330:duration=2",
            "-shortest", "-c:v", "libx264", "-c:a", "aac", str(video),
        ],
        check=True,
    )
    transcriber = GroqAudioTranscriber(
        api_key="test-key-not-real", client=httpx.Client(transport=httpx.MockTransport(_fake_groq))
    )
    parsed = VideoIngestionAdapter(transcriber=transcriber).parse(
        video, document_id=uuid4(), ingestion_version="v1", original_name="clip.mp4"
    )
    assert "Photosynthesis turns light" in " ".join(node.text for node in parsed.nodes)
