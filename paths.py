"""Canonical media and artifact paths for the video-intelligence pipeline."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

VIDEOS_UNPROCESSED = PROJECT_ROOT / "videos" / "unprocessed"
VIDEOS_PROCESSED = PROJECT_ROOT / "videos" / "processed"
AUDIO_DIR = PROJECT_ROOT / "audio"
TRANSCRIPTS_DIR = PROJECT_ROOT / "transcriptions" / "transcripts"
EMBEDDINGS_DIR = PROJECT_ROOT / "transcriptions" / "chunked"


def ensure_media_dirs() -> None:
    for directory in (
        VIDEOS_UNPROCESSED,
        VIDEOS_PROCESSED,
        AUDIO_DIR,
        TRANSCRIPTS_DIR,
        EMBEDDINGS_DIR,
    ):
        directory.mkdir(parents=True, exist_ok=True)


def audio_path(stem: str) -> Path:
    return AUDIO_DIR / f"{stem}.mp3"


def transcript_path(stem: str) -> Path:
    return TRANSCRIPTS_DIR / f"{stem}_transcript.json"


def embeddings_path(stem: str) -> Path:
    return EMBEDDINGS_DIR / f"{stem}_chunks.json"
