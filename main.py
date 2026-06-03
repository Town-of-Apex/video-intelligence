"""Bulk pipeline: unprocessed videos -> transcripts -> embedded chunks -> processed."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from paths import (
    VIDEOS_PROCESSED,
    VIDEOS_UNPROCESSED,
    audio_path,
    embeddings_path,
    ensure_media_dirs,
    transcript_path,
)

import chunk
import convert
import embed
import transcribe


def list_unprocessed_videos() -> list[Path]:
    return convert.find_videos(VIDEOS_UNPROCESSED)


def process_video(
    video_path: Path,
    *,
    model_size: str = "tiny.en",
    move_when_done: bool = True,
) -> dict[str, Path]:
    """Run extract -> transcribe -> chunk -> embed for one video file."""
    stem = video_path.stem
    artifacts = {
        "video": video_path,
        "audio": audio_path(stem),
        "transcript": transcript_path(stem),
        "embeddings": embeddings_path(stem),
    }

    print(f"\n=== Processing {video_path.name} (video_id={stem!r}) ===")

    print("Extracting audio...")
    convert.extract(video_path, artifacts["audio"])

    print("Transcribing...")
    transcribe.main(
        model_size,
        artifacts["audio"],
        video_id=stem,
        output_path=artifacts["transcript"],
    )

    print("Chunking...")
    chunk.main(artifacts["transcript"], artifacts["embeddings"])

    print("Manual embedding of chunks...")
    embed.embed_chunks(artifacts["embeddings"])

    if move_when_done:
        destination = VIDEOS_PROCESSED / video_path.name
        print(f"Moving video -> {destination}")
        shutil.move(str(video_path), destination)
        artifacts["video"] = destination

    print(f"Done: {stem}")
    return artifacts


def process_all(*, model_size: str = "tiny.en") -> int:
    ensure_media_dirs()
    videos = list_unprocessed_videos()
    if not videos:
        print(f"No video files in {VIDEOS_UNPROCESSED}")
        return 0

    print(f"Found {len(videos)} video(s) to process")
    failures: list[tuple[Path, BaseException]] = []

    for video in videos:
        try:
            process_video(video, model_size=model_size)
        except Exception as exc:
            print(f"Failed {video.name}: {exc}", file=sys.stderr)
            failures.append((video, exc))

    if failures:
        print(f"\n{len(failures)} video(s) failed.", file=sys.stderr)
        return 1

    print(f"\nSuccessfully processed {len(videos)} video(s).")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "video",
        nargs="?",
        type=Path,
        help="Single video under videos/unprocessed/ (default: process all)",
    )
    parser.add_argument(
        "--model-size",
        default="tiny.en",
        help="Whisper model passed to transcribe.py (default: tiny.en)",
    )
    parser.add_argument(
        "--no-move",
        action="store_true",
        help="Leave the source video in videos/unprocessed/ after processing",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    ensure_media_dirs()

    if args.video is not None:
        video = args.video
        if not video.is_file():
            video = VIDEOS_UNPROCESSED / video.name
        if not video.is_file():
            print(f"Video not found: {args.video}", file=sys.stderr)
            return 1
        try:
            process_video(video, model_size=args.model_size, move_when_done=not args.no_move)
        except Exception as exc:
            print(f"Failed: {exc}", file=sys.stderr)
            return 1
        return 0

    return process_all(model_size=args.model_size)


if __name__ == "__main__":
    raise SystemExit(main())
