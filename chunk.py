"""Chunk transcript JSON into overlapping temporal windows for Open WebUI export."""

from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULT_TARGET_SECONDS = 120.0
DEFAULT_OVERLAP_SECONDS = 15.0

METADATA_KEYS = ("video_id", "title", "duration_seconds", "transcribed_at")


def chunk_settings(
    *,
    target_seconds: float | None = None,
    overlap_seconds: float | None = None,
) -> tuple[float, float]:
    """Resolve chunk window and overlap from args or environment."""
    resolved_target = target_seconds
    if resolved_target is None:
        resolved_target = float(
            os.getenv("CHUNK_TARGET_SECONDS", str(DEFAULT_TARGET_SECONDS))
        )

    resolved_overlap = overlap_seconds
    if resolved_overlap is None:
        resolved_overlap = float(
            os.getenv("CHUNK_OVERLAP_SECONDS", str(DEFAULT_OVERLAP_SECONDS))
        )

    if resolved_target <= 0:
        raise ValueError(f"target_seconds must be > 0, got {resolved_target}")
    if resolved_overlap < 0:
        raise ValueError(f"overlap_seconds must be >= 0, got {resolved_overlap}")
    if resolved_overlap >= resolved_target:
        raise ValueError(
            f"overlap_seconds ({resolved_overlap}) must be less than "
            f"target_seconds ({resolved_target})"
        )

    return resolved_target, resolved_overlap


def window_duration(segments: list[dict]) -> float:
    if not segments:
        return 0.0
    return float(segments[-1]["end_time"]) - float(segments[0]["start_time"])


def overlap_segments(segments: list[dict], overlap_seconds: float) -> list[dict]:
    """Return trailing segments that cover the last ``overlap_seconds`` of the window."""
    if not segments or overlap_seconds <= 0:
        return []

    end = float(segments[-1]["end_time"])
    threshold = end - overlap_seconds
    overlap: list[dict] = []
    for segment in reversed(segments):
        overlap.insert(0, segment)
        if float(segment["start_time"]) <= threshold:
            break
    return overlap


def _normalize_segment_id(segment_id):
    return int(segment_id) if isinstance(segment_id, str) else segment_id


def create_chunk(segments: list[dict], chunk_id: int) -> dict:
    """Build a chunk dict from a list of transcript segments."""
    text = " ".join(segment["text"].strip() for segment in segments)
    return {
        "chunk_id": chunk_id,
        "start_time": segments[0]["start_time"],
        "end_time": segments[-1]["end_time"],
        "segment_ids": [_normalize_segment_id(segment["segment_id"]) for segment in segments],
        "text": text,
        "word_count": len(text.split()),
    }


def save_chunks(chunks: list[dict], output_path: str | Path, metadata: dict) -> Path:
    """Write internal chunk JSON (includes segment_ids / word_count)."""
    payload = {
        **metadata,
        "chunk_count": len(chunks),
        "chunks": chunks,
    }
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
    return path


def extract_metadata(transcript: dict) -> dict:
    return {key: transcript[key] for key in METADATA_KEYS if key in transcript}


def load_transcript(path: str | Path) -> dict:
    with Path(path).open(encoding="utf-8") as handle:
        return json.load(handle)


def chunkify_segments(
    segments: list[dict],
    *,
    target_seconds: float | None = None,
    overlap_seconds: float | None = None,
) -> list[dict]:
    """Split transcript segments into overlapping time-bounded chunks."""
    target_seconds, overlap_seconds = chunk_settings(
        target_seconds=target_seconds,
        overlap_seconds=overlap_seconds,
    )

    if not segments:
        return []

    chunks: list[dict] = []
    current_segments: list[dict] = []
    chunk_id = 1

    for segment in segments:
        current_segments.append(segment)

        if window_duration(current_segments) >= target_seconds:
            chunks.append(create_chunk(current_segments, chunk_id))
            chunk_id += 1
            current_segments = overlap_segments(current_segments, overlap_seconds)

    if current_segments:
        if chunks:
            last_segment_ids = set(chunks[-1]["segment_ids"])
            current_segment_ids = {
                _normalize_segment_id(segment["segment_id"]) for segment in current_segments
            }
            if current_segment_ids.issubset(last_segment_ids):
                return chunks
        chunks.append(create_chunk(current_segments, chunk_id))

    return chunks


def chunkify_transcript(
    transcript: dict,
    *,
    target_seconds: float | None = None,
    overlap_seconds: float | None = None,
) -> tuple[list[dict], dict]:
    metadata = extract_metadata(transcript)
    chunks = chunkify_segments(
        transcript.get("segments", []),
        target_seconds=target_seconds,
        overlap_seconds=overlap_seconds,
    )
    return chunks, metadata


def format_watch_prefix(title: str, link: str, start_time: float, end_time: float) -> str:
    return (
        f"[Watch: {title}]({link}) "
        f"(~{start_time:.0f}s–{end_time:.0f}s)"
    )


def build_owui_payload(
    chunks: list[dict],
    metadata: dict,
    *,
    watch_prefix: bool = False,
) -> dict:
    """
    Build the slim Open WebUI Knowledge JSON shape.

    Matches ``*_chunks_for_owui.json`` examples: no embeddings or segment_ids.
    """
    from sharepoint_nav import build_video_timestamp_url

    video_id = metadata["video_id"]
    title = metadata.get("title") or Path(str(video_id)).stem
    owui_chunks = []

    for chunk in chunks:
        link = build_video_timestamp_url(video_id, float(chunk["start_time"]))
        text = chunk["text"]
        if watch_prefix and link:
            prefix = format_watch_prefix(
                title,
                link,
                float(chunk["start_time"]),
                float(chunk["end_time"]),
            )
            text = f"{prefix}\n\n{text}"

        owui_chunks.append(
            {
                "chunk_id": chunk["chunk_id"],
                "start_time": chunk["start_time"],
                "end_time": chunk["end_time"],
                "text": text,
                "link": link,
            }
        )

    return {
        "video_id": video_id,
        "title": metadata.get("title"),
        "total_duration_seconds": metadata.get("duration_seconds"),
        "transcribed_at": metadata.get("transcribed_at"),
        "chunk_count": len(owui_chunks),
        "chunks": owui_chunks,
    }


def save_owui_chunks(payload: dict, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return path


def stem_from_transcript_path(transcript_path: Path) -> str:
    stem = transcript_path.stem
    if stem.endswith("_transcript"):
        return stem[: -len("_transcript")]
    return stem


def main(
    transcript_path: str | Path,
    output_path: str | Path | None = None,
    *,
    target_seconds: float | None = None,
    overlap_seconds: float | None = None,
    watch_prefix: bool = False,
    for_owui: bool = True,
) -> Path:
    transcript_path = Path(transcript_path)
    if output_path is None:
        from paths import chunks_path, owui_chunks_path

        stem = stem_from_transcript_path(transcript_path)
        output_path = owui_chunks_path(stem) if for_owui else chunks_path(stem)
    else:
        output_path = Path(output_path)

    target_seconds, overlap_seconds = chunk_settings(
        target_seconds=target_seconds,
        overlap_seconds=overlap_seconds,
    )

    transcript = load_transcript(transcript_path)
    chunks, metadata = chunkify_transcript(
        transcript,
        target_seconds=target_seconds,
        overlap_seconds=overlap_seconds,
    )

    if for_owui:
        payload = build_owui_payload(chunks, metadata, watch_prefix=watch_prefix)
        saved = save_owui_chunks(payload, output_path)
    else:
        saved = save_chunks(chunks, output_path, metadata)

    print(
        f"Created {len(chunks)} chunks "
        f"(target={target_seconds:g}s, overlap={overlap_seconds:g}s) -> {saved}"
    )
    for chunk in chunks:
        print(
            f"  chunk {chunk['chunk_id']}: "
            f"{chunk['start_time']:.1f}s-{chunk['end_time']:.1f}s, "
            f"{chunk['word_count']} words, "
            f"segments {chunk['segment_ids']}"
        )
    return saved


if __name__ == "__main__":
    import argparse

    from env_config import load_env_file
    from paths import TRANSCRIPTS_DIR, ensure_media_dirs

    load_env_file()

    parser = argparse.ArgumentParser(
        description="Chunk a transcript JSON file into OWUI-ready windows."
    )
    parser.add_argument(
        "transcript",
        nargs="?",
        type=Path,
        help="Transcript JSON (default: first *_transcript.json in transcriptions/transcripts/)",
    )
    parser.add_argument("--output", type=Path, help="Output JSON path")
    parser.add_argument(
        "--target-seconds",
        type=float,
        default=None,
        help=(
            f"Seconds per chunk (default: {DEFAULT_TARGET_SECONDS:g}, "
            "env: CHUNK_TARGET_SECONDS)"
        ),
    )
    parser.add_argument(
        "--overlap-seconds",
        type=float,
        default=None,
        help=(
            f"Overlap between chunks in seconds (default: {DEFAULT_OVERLAP_SECONDS:g}, "
            "env: CHUNK_OVERLAP_SECONDS)"
        ),
    )
    parser.add_argument(
        "--watch-prefix",
        action="store_true",
        help="Prefix each chunk text with a Markdown Watch link (still keeps link field)",
    )
    parser.add_argument(
        "--internal",
        action="store_true",
        help="Write internal *_chunks.json (with segment_ids) instead of *_chunks_for_owui.json",
    )
    args = parser.parse_args()

    ensure_media_dirs()
    transcript = args.transcript
    if transcript is None:
        candidates = sorted(TRANSCRIPTS_DIR.glob("*_transcript.json"))
        if not candidates:
            parser.error(f"No transcript files found in {TRANSCRIPTS_DIR}")
        transcript = candidates[0]

    main(
        transcript,
        args.output,
        target_seconds=args.target_seconds,
        overlap_seconds=args.overlap_seconds,
        watch_prefix=args.watch_prefix,
        for_owui=not args.internal,
    )
