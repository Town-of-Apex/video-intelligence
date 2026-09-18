"""Render transcript JSON as plain text and subtitle files."""

from __future__ import annotations

import json
from pathlib import Path


def transcript_text(payload: dict) -> str:
    """Return transcript segments as readable plain text."""
    lines = [segment["text"].strip() for segment in payload["segments"]]
    return "\n\n".join(line for line in lines if line) + "\n"


def _srt_timestamp(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def transcript_srt(payload: dict) -> str:
    """Return transcript segments in SubRip (SRT) format."""
    blocks = []
    for index, segment in enumerate(payload["segments"], start=1):
        blocks.append(
            "\n".join(
                (
                    str(index),
                    (
                        f"{_srt_timestamp(segment['start_time'])} --> "
                        f"{_srt_timestamp(segment['end_time'])}"
                    ),
                    segment["text"].strip(),
                )
            )
        )
    return "\n\n".join(blocks) + "\n"


def write_transcript_exports(payload: dict, output_dir: str | Path) -> dict[str, Path]:
    """Write JSON, TXT, and SRT files and return their paths by format."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(str(payload["video_id"])).stem
    paths = {
        "json": output_dir / f"{stem}_transcript.json",
        "txt": output_dir / f"{stem}_transcript.txt",
        "srt": output_dir / f"{stem}_transcript.srt",
    }
    paths["json"].write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    paths["txt"].write_text(transcript_text(payload), encoding="utf-8")
    paths["srt"].write_text(transcript_srt(payload), encoding="utf-8")
    return paths
