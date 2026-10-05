"""Bulk pipeline: unprocessed videos -> transcripts -> OWUI chunk JSON -> processed."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from paths import (
    VIDEOS_PROCESSED,
    VIDEOS_UNPROCESSED,
    audio_path,
    ensure_media_dirs,
    owui_chunks_path,
    transcript_path,
)

import chunk
import convert
import transcribe
from env_config import load_env_file

load_env_file()


def list_unprocessed_videos() -> list[Path]:
    return convert.find_videos(VIDEOS_UNPROCESSED)


def process_video(
    video_path: Path,
    *,
    model_size: str = "tiny.en",
    move_when_done: bool = True,
    target_seconds: float | None = None,
    overlap_seconds: float | None = None,
    watch_prefix: bool = False,
) -> dict[str, Path]:
    """Run extract -> transcribe -> chunk -> OWUI export for one video file."""
    stem = video_path.stem
    artifacts = {
        "video": video_path,
        "audio": audio_path(stem),
        "transcript": transcript_path(stem),
        "owui_chunks": owui_chunks_path(stem),
    }

    print(f"\n=== Processing {video_path.name} (video_id={stem!r}) ===")

    print("Extracting audio...")
    convert.extract(video_path, artifacts["audio"])

    print("Transcribing...")
    transcribe.main(
        model_size,
        artifacts["audio"],
        video_id=video_path.name,
        output_path=artifacts["transcript"],
    )

    print("Chunking + OWUI export (SharePoint timestamp links)...")
    chunk.main(
        artifacts["transcript"],
        artifacts["owui_chunks"],
        target_seconds=target_seconds,
        overlap_seconds=overlap_seconds,
        watch_prefix=watch_prefix,
        for_owui=True,
    )

    if move_when_done:
        destination = VIDEOS_PROCESSED / video_path.name
        print(f"Moving video -> {destination}")
        shutil.move(str(video_path), destination)
        artifacts["video"] = destination

    print(f"Done: {stem}")
    print(f"  Upload to Open WebUI Knowledge: {artifacts['owui_chunks']}")
    return artifacts


def process_all(
    *,
    model_size: str = "tiny.en",
    target_seconds: float | None = None,
    overlap_seconds: float | None = None,
    watch_prefix: bool = False,
) -> int:
    ensure_media_dirs()
    videos = list_unprocessed_videos()
    if not videos:
        print(f"No video files in {VIDEOS_UNPROCESSED}")
        return 0

    print(f"Found {len(videos)} video(s) to process")
    failures: list[tuple[Path, BaseException]] = []

    for video in videos:
        try:
            process_video(
                video,
                model_size=model_size,
                target_seconds=target_seconds,
                overlap_seconds=overlap_seconds,
                watch_prefix=watch_prefix,
            )
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
    parser.add_argument(
        "--target-seconds",
        type=float,
        default=None,
        help=(
            f"Seconds per transcript chunk "
            f"(default: {chunk.DEFAULT_TARGET_SECONDS:g}, env: CHUNK_TARGET_SECONDS)"
        ),
    )
    parser.add_argument(
        "--overlap-seconds",
        type=float,
        default=None,
        help=(
            f"Second overlap between chunks "
            f"(default: {chunk.DEFAULT_OVERLAP_SECONDS:g}, env: CHUNK_OVERLAP_SECONDS)"
        ),
    )
    parser.add_argument(
        "--watch-prefix",
        action="store_true",
        help="Prefix each chunk text with a Markdown Watch link (still keeps link field)",
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
            process_video(
                video,
                model_size=args.model_size,
                move_when_done=not args.no_move,
                target_seconds=args.target_seconds,
                overlap_seconds=args.overlap_seconds,
                watch_prefix=args.watch_prefix,
            )
        except Exception as exc:
            print(f"Failed: {exc}", file=sys.stderr)
            return 1
        return 0

    return process_all(
        model_size=args.model_size,
        target_seconds=args.target_seconds,
        overlap_seconds=args.overlap_seconds,
        watch_prefix=args.watch_prefix,
    )


if __name__ == "__main__":
    raise SystemExit(main())
