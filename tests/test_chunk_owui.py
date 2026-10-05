"""Tests for temporal chunking and Open WebUI export shape."""

from __future__ import annotations

from chunk import (
    build_owui_payload,
    chunkify_segments,
    format_watch_prefix,
    legacy_chunks_to_owui_payload,
)


def _seg(segment_id: int, start: float, end: float, text: str) -> dict:
    return {
        "segment_id": segment_id,
        "start_time": start,
        "end_time": end,
        "text": text,
    }


def test_chunkify_longer_temporal_windows() -> None:
    # 30s segments → with 120s target, one chunk until duration hits threshold.
    segments = [
        _seg(i, (i - 1) * 30.0, i * 30.0, f"Segment {i} about training content here.")
        for i in range(1, 9)
    ]
    chunks = chunkify_segments(segments, target_seconds=120.0, overlap_seconds=15.0)

    assert len(chunks) >= 2
    assert chunks[0]["start_time"] == 0.0
    assert chunks[0]["end_time"] - chunks[0]["start_time"] >= 120.0
    # Modest overlap: next chunk starts before previous ends.
    assert chunks[1]["start_time"] < chunks[0]["end_time"]
    assert "embedding" not in chunks[0]
    assert "segment_ids" in chunks[0]


def test_owui_payload_shape_matches_canonical_examples(monkeypatch) -> None:
    monkeypatch.setenv("SHAREPOINT_HOST", "apexncorg.sharepoint.com")
    monkeypatch.setenv("SHAREPOINT_SITE_NAME", "TOAInnovations")
    monkeypatch.setenv("SHAREPOINT_DOCUMENT_LIBRARY", "Shared Documents")
    monkeypatch.setenv(
        "SHAREPOINT_VIDEO_FOLDER",
        "Project Resources/Training Intelligence/Videos",
    )

    chunks = [
        {
            "chunk_id": 1,
            "start_time": 0.0,
            "end_time": 120.04,
            "segment_ids": [1, 2],
            "text": "How to add an emergency contact from your home page.",
            "word_count": 10,
        },
        {
            "chunk_id": 2,
            "start_time": 86.04,
            "end_time": 177.6,
            "segment_ids": [3, 4],
            "text": "Then your contact shows up on the emergency contact card.",
            "word_count": 10,
        },
    ]
    metadata = {
        "video_id": "How to Add an Emergency Contact.webm",
        "title": "How To Add An Emergency Contact",
        "duration_seconds": 179.11,
        "transcribed_at": "2026-06-12T17:20:13+00:00",
    }

    payload = build_owui_payload(chunks, metadata, watch_prefix=False)

    assert set(payload.keys()) == {
        "video_id",
        "title",
        "total_duration_seconds",
        "transcribed_at",
        "chunk_count",
        "chunks",
    }
    assert payload["video_id"] == metadata["video_id"]
    assert payload["title"] == metadata["title"]
    assert payload["total_duration_seconds"] == 179.11
    assert payload["chunk_count"] == 2
    assert "duration_seconds" not in payload
    assert "embedding" not in payload

    for chunk in payload["chunks"]:
        assert set(chunk.keys()) == {
            "chunk_id",
            "start_time",
            "end_time",
            "text",
            "link",
        }
        assert "embedding" not in chunk
        assert "segment_ids" not in chunk
        assert "word_count" not in chunk
        assert chunk["link"].startswith(
            "https://apexncorg.sharepoint.com/sites/TOAInnovations/"
            "_layouts/15/stream.aspx?"
        )
        assert "nav=" in chunk["link"]
        assert "How%20to%20Add%20an%20Emergency%20Contact.webm" in chunk["link"]


def test_legacy_chunks_to_owui_preserves_links_and_strips_extras() -> None:
    legacy = {
        "video_id": "demo.webm",
        "title": "Demo Video",
        "duration_seconds": 90.0,
        "transcribed_at": "2026-06-12T17:20:13+00:00",
        "chunk_count": 1,
        "chunks": [
            {
                "chunk_id": 1,
                "start_time": 42.0,
                "end_time": 90.0,
                "segment_ids": [1, 2],
                "text": "Body text.",
                "word_count": 2,
                "link": "https://example.sharepoint.com/preserved-link",
                "embedding": [0.1, 0.2, 0.3],
            }
        ],
    }

    payload = legacy_chunks_to_owui_payload(legacy, preserve_links=True)

    assert set(payload.keys()) == {
        "video_id",
        "title",
        "total_duration_seconds",
        "transcribed_at",
        "chunk_count",
        "chunks",
    }
    assert payload["total_duration_seconds"] == 90.0
    assert "duration_seconds" not in payload
    assert payload["chunk_count"] == 1

    chunk = payload["chunks"][0]
    assert set(chunk.keys()) == {
        "chunk_id",
        "start_time",
        "end_time",
        "text",
        "link",
    }
    assert chunk["link"] == "https://example.sharepoint.com/preserved-link"
    assert chunk["text"] == "Body text."
    assert "embedding" not in chunk
    assert "segment_ids" not in chunk
    assert "word_count" not in chunk


def test_watch_prefix_opt_in(monkeypatch) -> None:
    monkeypatch.setenv("SHAREPOINT_HOST", "apexncorg.sharepoint.com")
    monkeypatch.setenv("SHAREPOINT_SITE_NAME", "TOAInnovations")
    monkeypatch.setenv("SHAREPOINT_DOCUMENT_LIBRARY", "Shared Documents")
    monkeypatch.setenv(
        "SHAREPOINT_VIDEO_FOLDER",
        "Project Resources/Training Intelligence/Videos",
    )

    chunks = [
        {
            "chunk_id": 1,
            "start_time": 42.0,
            "end_time": 90.0,
            "text": "Body text.",
            "segment_ids": [1],
            "word_count": 2,
        }
    ]
    metadata = {
        "video_id": "demo.webm",
        "title": "Demo Video",
        "duration_seconds": 90.0,
        "transcribed_at": "2026-06-12T17:20:13+00:00",
    }
    payload = build_owui_payload(chunks, metadata, watch_prefix=True)
    text = payload["chunks"][0]["text"]
    link = payload["chunks"][0]["link"]
    expected_prefix = format_watch_prefix("Demo Video", link, 42.0, 90.0)
    assert text.startswith(expected_prefix)
    assert text.endswith("Body text.")
    assert payload["chunks"][0]["link"] == link
