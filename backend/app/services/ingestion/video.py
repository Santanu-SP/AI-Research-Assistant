"""Video ingestion pipeline using FFmpeg for audio extraction and selective keyframe analysis."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
import subprocess
import tempfile
from uuid import UUID

from app.core.config import Settings
from app.domain.documents import MetadataProvenance
from app.domain.ingestion import CanonicalMetadata, ParsedDocument, ParsedNode
from app.services.ingestion.audio import GroqAudioTranscriber, audio_transcriber_for
from app.services.ingestion.pipeline import DocumentIngestionError, stable_node_id
from app.services.ingestion.vision import GeminiVisionAnalyzer, vision_analyzer_for
from app.services.ingestion.youtube import format_timestamp

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExtractedKeyframe:
    path: Path
    timestamp_seconds: float


class VideoIngestionAdapter:
    """Extracts audio and selective scene keyframes with FFmpeg and indexes both modalities."""

    def __init__(
        self,
        *,
        transcriber: GroqAudioTranscriber,
        vision_analyzer: GeminiVisionAnalyzer | None = None,
        ffmpeg_binary: str = "ffmpeg",
        max_frames: int = 6,
        scene_threshold: float = 0.35,
        timeout_seconds: float = 120.0,
    ) -> None:
        self.transcriber = transcriber
        self.vision_analyzer = vision_analyzer
        self.ffmpeg_binary = ffmpeg_binary
        self.max_frames = max_frames
        self.scene_threshold = scene_threshold
        self.timeout_seconds = timeout_seconds

    def extract_audio(self, video_path: Path, output_audio_path: Path) -> Path:
        """Extract mono 16kHz WAV audio track from video using FFmpeg."""
        cmd = [
            self.ffmpeg_binary,
            "-y",
            "-i",
            str(video_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-f",
            "wav",
            str(output_audio_path),
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except FileNotFoundError as exc:
            raise DocumentIngestionError(
                "FFmpeg binary is not installed or not on PATH",
                code="ffmpeg_unavailable",
                status_code=503,
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise DocumentIngestionError(
                "FFmpeg timed out while extracting audio from the video",
                code="video_processing_timeout",
                status_code=504,
            ) from exc

        if result.returncode != 0 or not output_audio_path.is_file() or output_audio_path.stat().st_size == 0:
            raise DocumentIngestionError(
                "Could not extract an audio track from the uploaded video",
                code="video_audio_extraction_failed",
                status_code=422,
            )
        return output_audio_path

    def extract_selective_keyframes(
        self,
        video_path: Path,
        frames_dir: Path,
    ) -> list[ExtractedKeyframe]:
        """Extract up to ``max_frames`` representative keyframes without dumping every frame."""
        pattern = str(frames_dir / "frame_%03d.png")
        # Scene-change filter or 1 frame every 15s, capped strictly at max_frames
        vf_expr = f"select='eq(n\\,0)+gt(scene\\,{self.scene_threshold})',scale='min(1280,iw)':-2"
        cmd = [
            self.ffmpeg_binary,
            "-y",
            "-i",
            str(video_path),
            "-vf",
            vf_expr,
            "-vsync",
            "vfr",
            "-frames:v",
            str(self.max_frames),
            pattern,
        ]
        try:
            subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return []

        files = sorted(frames_dir.glob("frame_*.png"))[: self.max_frames]
        # Assign approximate progressive timestamps if scene pts are not parsed
        return [
            ExtractedKeyframe(path=frame_path, timestamp_seconds=float(index * 15))
            for index, frame_path in enumerate(files)
        ]

    def parse(
        self,
        path: Path,
        *,
        document_id: UUID,
        ingestion_version: str,
        original_name: str | None = None,
    ) -> ParsedDocument:
        title = original_name or path.stem
        with tempfile.TemporaryDirectory(prefix="ara_video_") as tmp_dir_str:
            tmp_dir = Path(tmp_dir_str)
            audio_path = tmp_dir / "extracted_audio.wav"
            frames_dir = tmp_dir / "frames"
            frames_dir.mkdir(parents=True, exist_ok=True)

            self.extract_audio(path, audio_path)
            audio_parsed = self.transcriber.parse(
                audio_path,
                document_id=document_id,
                ingestion_version=ingestion_version,
                original_name=title,
            )
            nodes: list[ParsedNode] = []
            for idx, node in enumerate(audio_parsed.nodes):
                meta = dict(node.metadata)
                meta["original_video"] = path.name
                meta["modality"] = "audio_transcript"
                nodes.append(
                    ParsedNode(
                        node_id=stable_node_id(document_id, idx, node.text),
                        text=node.text,
                        chunk_index=idx,
                        page=node.page,
                        page_end=node.page_end,
                        section=node.section,
                        section_path=node.section_path,
                        token_count=node.token_count,
                        metadata=meta,
                    )
                )

            analyzed_frames = 0
            if self.vision_analyzer is not None and self.vision_analyzer.api_key:
                keyframes = self.extract_selective_keyframes(path, frames_dir)
                for kf in keyframes:
                    try:
                        desc = self.vision_analyzer.analyze_image_bytes(
                            kf.path.read_bytes(),
                            mime_type="image/png",
                            context_hint=f"Video '{title}' at {format_timestamp(kf.timestamp_seconds)}",
                        )
                    except DocumentIngestionError:
                        logger.warning("Skipping frame vision analysis after provider error", exc_info=True)
                        break
                    if not desc:
                        continue
                    analyzed_frames += 1
                    time_label = format_timestamp(kf.timestamp_seconds)
                    section_label = f"Frame @ {time_label}"
                    node_idx = len(nodes)
                    frame_text = f"[Visual Frame @ {time_label}] {desc}"
                    nodes.append(
                        ParsedNode(
                            node_id=stable_node_id(document_id, node_idx, frame_text),
                            text=frame_text,
                            chunk_index=node_idx,
                            page=node_idx + 1,
                            page_end=node_idx + 1,
                            section=section_label,
                            section_path=[title, section_label],
                            token_count=len(frame_text.split()),
                            metadata={
                                "content_kind": "video_frame_description",
                                "modality": "visual_frame",
                                "timestamp_start": kf.timestamp_seconds,
                                "timestamp_end": kf.timestamp_seconds,
                                "time_range": time_label,
                                "original_video": path.name,
                            },
                        )
                    )

        return ParsedDocument(
            document_id=document_id,
            metadata=CanonicalMetadata(
                title=title,
                values={
                    "original_video": path.name,
                    "whisper_model": self.transcriber.model_name,
                    "analyzed_keyframes": analyzed_frames,
                },
                provenance={"title": MetadataProvenance.WHISPER},
            ),
            page_count=len(nodes),
            parser_name="ffmpeg-whisper-vision",
            parser_version="1.0",
            ingestion_version=f"{ingestion_version}:video",
            nodes=nodes,
        )


def video_adapter_for(settings: Settings) -> VideoIngestionAdapter:
    transcriber = audio_transcriber_for(settings)
    vision = vision_analyzer_for(settings) if settings.vision_enabled else None
    return VideoIngestionAdapter(
        transcriber=transcriber,
        vision_analyzer=vision,
        ffmpeg_binary=settings.ffmpeg_binary,
        max_frames=settings.video_max_frames,
        scene_threshold=settings.video_scene_threshold,
    )

