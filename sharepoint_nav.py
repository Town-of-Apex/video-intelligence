"""Build SharePoint stream URLs that open a video at a specific timestamp."""

from __future__ import annotations

import base64
import json
import os
import urllib.parse

# --- SharePoint location (override via env for dev / prod) ---

SHAREPOINT_HOST = os.environ.get("SHAREPOINT_HOST", "apexncorg.sharepoint.com")

# Site collection name as it appears in /sites/{name}/...
SHAREPOINT_SITE_NAME = os.environ.get("SHAREPOINT_SITE_NAME", "TOAInnovations")

# Document library and folders under the site (no leading or trailing slashes).
# Parsed from:
# .../Shared Documents/Project Resources/Training Intelligence/Videos
SHAREPOINT_DOCUMENT_LIBRARY = os.environ.get(
    "SHAREPOINT_DOCUMENT_LIBRARY", "Shared Documents"
)
SHAREPOINT_VIDEO_FOLDER_SEGMENTS: tuple[str, ...] = tuple(
    filter(
        None,
        os.environ.get(
            "SHAREPOINT_VIDEO_FOLDER",
            "Project Resources/Training Intelligence/Videos",
        ).split("/"),
    )
)

# stream.aspx lives under each site’s _layouts path.
STREAM_LAYOUT_PATH = "_layouts/15/stream.aspx"

# Folder browser URL (reference only — not used when building stream links).
SHAREPOINT_VIDEOS_FOLDER_VIEW_URL = (
    "https://apexncorg.sharepoint.com/sites/TOAInnovations/"
    "Shared%20Documents/Forms/AllItems.aspx?"
    "id=%2Fsites%2FTOAInnovations%2FShared%20Documents%2F"
    "Project%20Resources%2FTraining%20Intelligence%2FVideos"
    "&viewid=c2da8fbd%2Dde4f%2D4d1b%2D8819%2D4654787f5197"
)


def _server_relative_video_path(video_id: str) -> str:
    """
    Full server-relative path to a file in the videos folder.

    ``video_id`` should include the file extension (e.g. ``"How to Add an Emergency Contact.webm"``).
    """
    if not video_id or video_id.strip() != video_id:
        raise ValueError("video_id must be a non-empty filename (including extension).")

    parts = (
        "sites",
        SHAREPOINT_SITE_NAME,
        SHAREPOINT_DOCUMENT_LIBRARY,
        *SHAREPOINT_VIDEO_FOLDER_SEGMENTS,
        video_id,
    )
    return "/" + "/".join(parts)


def _encode_nav(start_time_seconds: float) -> str:
    """Base64 + URL-encode the playback nav payload SharePoint expects."""
    if start_time_seconds < 0:
        raise ValueError("start_time_seconds must be >= 0")

    nav_data = {
        "playbackOptions": {
            "startTimeInSeconds": float(start_time_seconds),
        }
    }
    nav_json = json.dumps(nav_data, separators=(",", ":"))
    nav_b64 = base64.b64encode(nav_json.encode("utf-8")).decode("ascii")
    return urllib.parse.quote(nav_b64, safe="")


def build_video_timestamp_url(video_id: str, start_time_seconds: float) -> str:
    """
    Return a SharePoint stream URL that opens ``video_id`` at ``start_time_seconds``.

    Parameters
    ----------
    video_id:
        Filename under the configured videos folder, including extension
        (e.g. ``"How to Add an Emergency Contact.webm"``).
    start_time_seconds:
        Playback start offset in seconds (same unit as chunk ``start_time``).
    """
    file_path = _server_relative_video_path(video_id)
    encoded_id = urllib.parse.quote(file_path, safe="")
    encoded_nav = _encode_nav(start_time_seconds)

    return (
        f"https://{SHAREPOINT_HOST}/sites/{SHAREPOINT_SITE_NAME}/"
        f"{STREAM_LAYOUT_PATH}?id={encoded_id}&nav={encoded_nav}"
    )

def add_nav_to_chunks(chunks_json: str) -> None:
    with open(chunks_json, encoding="utf-8") as f:
        payload = json.load(f)
    video_id = payload["video_id"]
    for chunk in payload["chunks"]:
        chunk["link"] = build_video_timestamp_url(video_id, chunk["start_time"])
    with open(chunks_json, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"Added links to {chunks_json}")

def main(chunks_json: str):
    add_nav_to_chunks(chunks_json)
    print(f"Added links to {chunks_json}")

if __name__ == "__main__":
    example_video = "How to Add an Emergency Contact.webm"
    example_start = 42.5
    print(build_video_timestamp_url(example_video, example_start))
