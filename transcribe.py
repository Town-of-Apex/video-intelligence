"""Transcribe audio with faster-whisper and save segments as JSON."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path

from faster_whisper import WhisperModel

METADATA_KEYS = ("video_id", "title", "duration_seconds", "transcribed_at")


def transcribe(audio_path: str | Path, model_size: str = "large-v3-turbo"):
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, info = model.transcribe(str(audio_path), beam_size=5)
    return list(segments), info


def segment_to_dict(segment, segment_id: int) -> dict:
    """Map a faster-whisper segment to the example_transcript.json segment shape."""
    return {
        "segment_id": segment_id,
        "start_time": round(segment.start, 3),
        "end_time": round(segment.end, 3),
        "text": segment.text.strip(),
    }


def format_segments(segments) -> list[dict]:
    return [segment_to_dict(segment, index) for index, segment in enumerate(segments, start=1)]


def build_transcript(
    segments,
    info,
    *,
    video_id: str,
    title: str,
) -> dict:
    return {
        "video_id": video_id,
        "title": title,
        "duration_seconds": round(info.duration, 3),
        "transcribed_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "segments": format_segments(segments),
    }


def save_transcript(payload: dict, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
    return path


def display_summary(segments, info) -> None:
    print(f"Detected language: {info.language}")
    print(f"Total duration: {info.duration:.2f} seconds")
    print(f"Total segments: {len(segments)}")
    if segments:
        print(f"Average segment length: {info.duration / len(segments):.2f} seconds")


def display_transcript(segments) -> None:
    print("-" * 80)
    for segment in segments:
        print(
            "[%.2fs -> %.2fs] %.2f %s"
            % (segment.start, segment.end, segment.avg_logprob, segment.text)
        )
    print("-" * 80)


def default_title(audio_path: Path) -> str:
    return audio_path.stem.replace("_", " ").replace("-", " ").title()


def main(
    model_size: str,
    audio_path: str | Path,
    *,
    video_id: str | None = None,
    title: str | None = None,
    output_path: str | Path | None = None,
):
    audio_path = Path(audio_path)
    segments, info = transcribe(audio_path, model_size)

    payload = build_transcript(
        segments,
        info,
        video_id=video_id or audio_path.stem,
        title=title or default_title(audio_path),
    )
    from paths import transcript_path as default_transcript_path

    output_path = output_path or default_transcript_path(audio_path.stem)

    display_summary(segments, info)
    display_transcript(segments)
    saved = save_transcript(payload, output_path)
    print(f"Saved transcript -> {saved}")
    return payload, saved


if __name__ == "__main__":
    import argparse

    from paths import audio_path as default_audio_path, ensure_media_dirs

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "audio",
        nargs="?",
        type=Path,
        help="Audio file (default: first .mp3 in audio/)",
    )
    parser.add_argument("--model-size", default="tiny.en", help="Whisper model size")
    parser.add_argument("--video-id", help="Override video_id in transcript JSON")
    parser.add_argument("--title", help="Override title in transcript JSON")
    parser.add_argument("--output", type=Path, help="Transcript JSON path")
    args = parser.parse_args()

    ensure_media_dirs()
    audio = args.audio
    if audio is None:
        from paths import AUDIO_DIR

        candidates = sorted(AUDIO_DIR.glob("*.mp3"))
        if not candidates:
            parser.error(f"No .mp3 files found in {AUDIO_DIR}")
        audio = candidates[0]

    start_time = time.perf_counter()
    payload, saved = main(
        args.model_size,
        audio,
        video_id=args.video_id,
        title=args.title,
        output_path=args.output,
    )
    elapsed = time.perf_counter() - start_time
    print(f"Time taken: {elapsed:.2f} seconds")
    print(f"Saved -> {saved}")
    duration = payload.get("duration_seconds") or 0
    if elapsed > 0 and duration:
        print(f"Speed: {duration / elapsed:.2f} file-seconds processed per second")
