"""Extract audio from a video file."""

from __future__ import annotations

from pathlib import Path

from moviepy import VideoFileClip

from paths import audio_path, ensure_media_dirs

# Extensions MoviePy/FFmpeg typically decode (container formats).
VIDEO_EXTENSIONS = frozenset({
    ".webm",
    ".mp4",
    ".m4v",
    ".mkv",
    ".avi",
    ".mov",
    ".wmv",
    ".flv",
    ".mpeg",
    ".mpg",
    ".ogv",
    ".3gp",
    ".ts",
})


def is_video(path: Path) -> bool:
    return path.suffix.lower() in VIDEO_EXTENSIONS


def find_videos(directory: Path) -> list[Path]:
    """Return video files in *directory*, sorted by name."""
    if not directory.is_dir():
        return []
    return sorted(
        (p for p in directory.iterdir() if p.is_file() and is_video(p)),
        key=lambda p: p.name.lower(),
    )


def extract(video_path: str | Path, output_path: str | Path | None = None) -> Path:
    """Extract audio from *video_path* and write to *output_path* (or audio/{stem}.mp3)."""
    video_path = Path(video_path)
    if not video_path.is_file():
        raise FileNotFoundError(video_path)
    if not is_video(video_path):
        supported = ", ".join(sorted(VIDEO_EXTENSIONS))
        raise ValueError(
            f"Unsupported file type {video_path.suffix!r} for {video_path.name}. "
            f"Supported extensions: {supported}"
        )

    output_path = Path(output_path) if output_path else audio_path(video_path.stem)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    video = VideoFileClip(str(video_path))
    try:
        if video.audio is None:
            raise ValueError(f"{video_path} has no audio track")
        video.audio.write_audiofile(str(output_path))
    finally:
        video.close()

    return output_path


if __name__ == "__main__":
    import argparse

    from paths import VIDEOS_UNPROCESSED

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "video",
        nargs="?",
        type=Path,
        help="Video file (default: first video in videos/unprocessed/)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output audio path (default: audio/{video_stem}.mp3)",
    )
    args = parser.parse_args()

    ensure_media_dirs()
    video = args.video
    if video is None:
        candidates = find_videos(VIDEOS_UNPROCESSED)
        if not candidates:
            parser.error(f"No video files found in {VIDEOS_UNPROCESSED}")
        video = candidates[0]

    out = extract(video, args.output)
    print(f"Extracted audio -> {out}")
