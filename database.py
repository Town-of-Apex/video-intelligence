"""Ingest embedded chunk JSON into PostgreSQL + pgvector and run semantic search."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import psycopg
from pgvector.psycopg import register_vector

from embed import generate_embedding

EMBEDDING_DIMENSIONS = int(os.getenv("EMBEDDING_DIMENSIONS", "768"))


def connection_kwargs() -> dict[str, Any]:
    return {
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": int(os.getenv("POSTGRES_PORT", "5432")),
        "dbname": os.getenv("POSTGRES_DB", "video_intelligence"),
        "user": os.getenv("POSTGRES_USER", "postgres"),
        "password": os.getenv("POSTGRES_PASSWORD", "password"),
    }


def connect() -> psycopg.Connection:
    conn = psycopg.connect(**connection_kwargs())
    register_vector(conn)
    return conn


def load_env_file(path: Path = Path(".env")) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_chunks_document(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        document = json.load(handle)

    required = ("video_id", "title", "chunks")
    missing = [key for key in required if key not in document]
    if missing:
        raise ValueError(f"{path}: missing required keys: {', '.join(missing)}")

    if not document["chunks"]:
        raise ValueError(f"{path}: chunks array is empty")

    return document


def validate_chunk(chunk: dict[str, Any], *, path: Path, index: int) -> None:
    embedding = chunk.get("embedding")
    if embedding is None:
        raise ValueError(f"{path}: chunk[{index}] has no embedding; run embed.py first")
    if len(embedding) != EMBEDDING_DIMENSIONS:
        raise ValueError(
            f"{path}: chunk[{index}] embedding has {len(embedding)} dimensions, "
            f"expected {EMBEDDING_DIMENSIONS}"
        )


def upsert_video(cur: psycopg.Cursor, document: dict[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO videos (video_id, title, duration_seconds, transcribed_at)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (video_id) DO UPDATE SET
            title = EXCLUDED.title,
            duration_seconds = EXCLUDED.duration_seconds,
            transcribed_at = EXCLUDED.transcribed_at,
            updated_at = NOW()
        """,
        (
            document["video_id"],
            document["title"],
            document.get("duration_seconds"),
            document.get("transcribed_at"),
        ),
    )


def upsert_chunks(cur: psycopg.Cursor, document: dict[str, Any], *, source: Path) -> int:
    video_id = document["video_id"]
    rows: list[tuple[Any, ...]] = []

    for index, chunk in enumerate(document["chunks"]):
        validate_chunk(chunk, path=source, index=index)
        rows.append(
            (
                video_id,
                chunk["chunk_id"],
                chunk["start_time"],
                chunk["end_time"],
                chunk.get("segment_ids", []),
                chunk["text"],
                chunk.get("word_count"),
                chunk["embedding"],
            )
        )

    cur.executemany(
        """
        INSERT INTO chunks (
            video_id,
            chunk_id,
            start_time,
            end_time,
            segment_ids,
            text,
            word_count,
            embedding
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (video_id, chunk_id) DO UPDATE SET
            start_time = EXCLUDED.start_time,
            end_time = EXCLUDED.end_time,
            segment_ids = EXCLUDED.segment_ids,
            text = EXCLUDED.text,
            word_count = EXCLUDED.word_count,
            embedding = EXCLUDED.embedding,
            updated_at = NOW()
        """,
        rows,
    )
    return len(rows)


def ingest_file(path: Path) -> tuple[str, int]:
    document = load_chunks_document(path)
    for index, chunk in enumerate(document["chunks"]):
        validate_chunk(chunk, path=path, index=index)

    with connect() as conn:
        with conn.cursor() as cur:
            upsert_video(cur, document)
            count = upsert_chunks(cur, document, source=path)
        conn.commit()

    return document["video_id"], count


def ingest_paths(paths: list[Path]) -> None:
    for path in paths:
        video_id, count = ingest_file(path)
        print(f"Ingested {count} chunk(s) for video_id={video_id!r} from {path}")


def search_chunks(
    query: str,
    *,
    limit: int = 5,
    video_id: str | None = None,
) -> list[dict[str, Any]]:
    embedding = generate_embedding(query)

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    chunk_pk,
                    video_id,
                    video_title,
                    chunk_id,
                    start_time,
                    end_time,
                    time_range,
                    text,
                    similarity
                FROM search_video_chunks(%s::vector, %s::integer, %s::text)
                """,
                (embedding, limit, video_id),
            )
            columns = [desc.name for desc in cur.description]
            rows = cur.fetchall()

    return [dict(zip(columns, row, strict=True)) for row in rows]


def print_search_results(results: list[dict[str, Any]]) -> None:
    if not results:
        print("No matching chunks.")
        return

    for rank, row in enumerate(results, start=1):
        print(
            f"\n[{rank}] {row['video_title']} ({row['video_id']}) "
            f"chunk {row['chunk_id']} @ {row['time_range']} "
            f"(similarity={row['similarity']:.4f})"
        )
        preview = row["text"]
        if len(preview) > 280:
            preview = preview[:277] + "..."
        print(preview)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser("ingest", help="Load embedded chunk JSON into Postgres")
    ingest_parser.add_argument(
        "paths",
        nargs="+",
        type=Path,
        help="Embedded chunk JSON files (e.g. transcriptions/embeddings/my_video_chunks.json)",
    )

    search_parser = subparsers.add_parser("search", help="Semantic search with timestamp citations")
    search_parser.add_argument("query", help="Natural language question")
    search_parser.add_argument("--limit", type=int, default=5)
    search_parser.add_argument("--video-id", help="Restrict search to one video_id")
    search_parser.add_argument(
        "--json",
        action="store_true",
        help="Print raw JSON (useful for OpenWebUI pipelines/tools)",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    load_env_file()
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "ingest":
            ingest_paths(args.paths)
            return 0

        if args.command == "search":
            results = search_chunks(args.query, limit=args.limit, video_id=args.video_id)
            if args.json:
                print(json.dumps(results, indent=2))
            else:
                print_search_results(results)
            return 0
    except (psycopg.Error, ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
