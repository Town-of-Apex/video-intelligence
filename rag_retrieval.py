"""Shared RAG retrieval helpers for CLI search and OpenWebUI pipelines."""

from __future__ import annotations

from typing import Any, Callable, Sequence


SEARCH_RESULT_FIELDS = (
    "chunk_pk",
    "video_id",
    "video_title",
    "chunk_id",
    "start_time",
    "end_time",
    "time_range",
    "text",
    "link",
    "similarity",
    "text_rank",
    "title_rank",
    "combined_score",
)


def row_to_hit(row: Sequence[Any], columns: Sequence[str]) -> dict[str, Any]:
    return dict(zip(columns, row, strict=True))


def merge_hits(
    hit_lists: Sequence[Sequence[dict[str, Any]]],
    *,
    top_k: int,
    score_key: str = "combined_score",
) -> list[dict[str, Any]]:
    """Deduplicate chunks across multiple searches and keep the best score."""
    best: dict[Any, dict[str, Any]] = {}

    for hits in hit_lists:
        for hit in hits:
            key = hit.get("chunk_pk")
            if key is None:
                key = (hit.get("video_id"), hit.get("chunk_id"))

            existing = best.get(key)
            score = float(hit.get(score_key) or hit.get("similarity") or 0.0)
            if existing is None or score > float(
                existing.get(score_key) or existing.get("similarity") or 0.0
            ):
                best[key] = hit

    ranked = sorted(
        best.values(),
        key=lambda row: float(row.get(score_key) or row.get("similarity") or 0.0),
        reverse=True,
    )
    return ranked[: max(top_k, 1)]


def build_query_expansion_prompt(query: str, titles: Sequence[str]) -> str:
    catalog = "\n".join(f"- {title}" for title in titles)
    return f"""You help search employee training video transcripts.

Available training videos:
{catalog}

Rewrite the user's question into a short search query (1-2 sentences) using words likely to appear in relevant transcripts. When a video title clearly matches the topic, include its key terms.

User question: {query}

Search query:"""


def expand_query_with_titles(
    query: str,
    titles: Sequence[str],
    *,
    generate: Callable[[str], str],
) -> str:
    cleaned = query.strip()
    if not cleaned or not titles:
        return cleaned

    expanded = generate(build_query_expansion_prompt(cleaned, titles)).strip()
    if not expanded or expanded.lower() == cleaned.lower():
        return cleaned
    return expanded


HYBRID_SEARCH_SQL = """
SELECT
    chunk_pk,
    video_id,
    video_title,
    chunk_id,
    start_time,
    end_time,
    time_range,
    text,
    link,
    similarity,
    text_rank,
    title_rank,
    combined_score
FROM search_video_chunks_hybrid(
    %s::vector(768),
    %s::text,
    %s::integer,
    %s::text,
    %s::double precision,
    %s::double precision,
    %s::double precision
)
"""

VECTOR_SEARCH_SQL = """
SELECT
    chunk_pk,
    video_id,
    video_title,
    chunk_id,
    start_time,
    end_time,
    time_range,
    text,
    link,
    similarity,
    0::double precision AS text_rank,
    0::double precision AS title_rank,
    similarity AS combined_score
FROM search_video_chunks(%s::vector(768), %s::integer, %s::text)
"""

LIST_VIDEO_TITLES_SQL = "SELECT video_id, title FROM videos ORDER BY title"
