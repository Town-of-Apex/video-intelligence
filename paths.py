"""Canonical media and artifact paths for the video-intelligence pipeline."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

VIDEOS_UNPROCESSED = PROJECT_ROOT / "videos" / "unprocessed"
VIDEOS_PROCESSED = PROJECT_ROOT / "videos" / "processed"
AUDIO_DIR = PROJECT_ROOT / "audio"
TRANSCRIPTS_DIR = PROJECT_ROOT / "transcriptions" / "transcripts"
OWUI_FORMAT_DIR = PROJECT_ROOT / "transcriptions" / "owui_format"

# Legacy location (read-only migration source; pipeline no longer writes here).
CHUNKED_DIR = PROJECT_ROOT / "transcriptions" / "chunked"

# Back-compat alias for older imports / docs.
EMBEDDINGS_DIR = CHUNKED_DIR


def ensure_media_dirs() -> None:
    for directory in (
        VIDEOS_UNPROCESSED,
        VIDEOS_PROCESSED,
        AUDIO_DIR,
        TRANSCRIPTS_DIR,
        OWUI_FORMAT_DIR,
    ):
        directory.mkdir(parents=True, exist_ok=True)


def audio_path(stem: str) -> Path:
    return AUDIO_DIR / f"{stem}.mp3"


def transcript_path(stem: str) -> Path:
    return TRANSCRIPTS_DIR / f"{stem}_transcript.json"


def owui_chunks_path(stem: str) -> Path:
    """Open WebUI Knowledge export: ``{stem}_chunks_for_owui.json``."""
    return OWUI_FORMAT_DIR / f"{stem}_chunks_for_owui.json"


def chunks_path(stem: str) -> Path:
    """Deprecated: legacy internal chunk JSON under ``transcriptions/chunked/``."""
    return CHUNKED_DIR / f"{stem}_chunks.json"


def embeddings_path(stem: str) -> Path:
    """Deprecated alias for ``chunks_path``."""
    return chunks_path(stem)
