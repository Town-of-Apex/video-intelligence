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
from paths import EMBEDDINGS_DIR

EMBEDDING_DIMENSIONS = int(os.getenv("EMBEDDING_DIMENSIONS", "768"))
CHUNK_FILE_SUFFIX = "_chunks.json"


def connection_kwargs() -> dict[str, Any]:
    return {
        "host": os.getenv("POSTGRES_HOST", "host.docker.internal"),
        "port": int(os.getenv("POSTGRES_PORT", "5431")),
        "dbname": os.getenv("POSTGRES_DB", "training_intelligence"),
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


def ensure_schema(cur: psycopg.Cursor) -> None:
    """Apply additive schema changes for databases created before link/source_file."""
    cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
    cur.execute("ALTER TABLE videos ADD COLUMN IF NOT EXISTS source_file TEXT UNIQUE")
    cur.execute("ALTER TABLE chunks ADD COLUMN IF NOT EXISTS link TEXT")
    cur.execute(
        "DROP FUNCTION IF EXISTS search_video_chunks(vector, integer, text)"
    )
    cur.execute(
        """
        CREATE OR REPLACE FUNCTION search_video_chunks(
            query_embedding vector(768),
            match_count INTEGER DEFAULT 5,
            filter_video_id TEXT DEFAULT NULL
        )
        RETURNS TABLE (
            chunk_pk BIGINT,
            video_id TEXT,
            video_title TEXT,
            chunk_id INTEGER,
            start_time DOUBLE PRECISION,
            end_time DOUBLE PRECISION,
            time_range TEXT,
            text TEXT,
            link TEXT,
            similarity DOUBLE PRECISION
        )
        LANGUAGE sql
        STABLE
        AS $$
            SELECT
                c.id AS chunk_pk,
                c.video_id,
                v.title AS video_title,
                c.chunk_id,
                c.start_time,
                c.end_time,
                format_timestamp(c.start_time) || '-' || format_timestamp(c.end_time) AS time_range,
                c.text,
                c.link,
                1 - (c.embedding <=> query_embedding) AS similarity
            FROM chunks c
            JOIN videos v ON v.video_id = c.video_id
            WHERE filter_video_id IS NULL OR c.video_id = filter_video_id
            ORDER BY c.embedding <=> query_embedding
            LIMIT GREATEST(match_count, 1);
        $$
        """
    )


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


def discover_chunk_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        raise FileNotFoundError(f"Chunk directory not found: {directory}")
    return sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and path.name.endswith(CHUNK_FILE_SUFFIX)
    )


def wipe_database(cur: psycopg.Cursor) -> None:
    cur.execute("TRUNCATE videos RESTART IDENTITY CASCADE")


def upsert_video(
    cur: psycopg.Cursor,
    document: dict[str, Any],
    *,
    source_file: str,
) -> str:
    cur.execute(
        "SELECT video_id FROM videos WHERE source_file = %s",
        (source_file,),
    )
    existing = cur.fetchone()
    video_id = document["video_id"]

    if existing and existing[0] != video_id:
        cur.execute("DELETE FROM videos WHERE source_file = %s", (source_file,))

    cur.execute(
        """
        INSERT INTO videos (video_id, title, duration_seconds, transcribed_at, source_file)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (video_id) DO UPDATE SET
            title = EXCLUDED.title,
            duration_seconds = EXCLUDED.duration_seconds,
            transcribed_at = EXCLUDED.transcribed_at,
            source_file = EXCLUDED.source_file,
            updated_at = NOW()
        """,
        (
            video_id,
            document["title"],
            document.get("duration_seconds"),
            document.get("transcribed_at"),
            source_file,
        ),
    )
    return video_id


def upsert_chunks(
    cur: psycopg.Cursor,
    document: dict[str, Any],
    *,
    source: Path,
) -> int:
    video_id = document["video_id"]
    rows: list[tuple[Any, ...]] = []
    chunk_ids: list[int] = []

    for index, chunk in enumerate(document["chunks"]):
        validate_chunk(chunk, path=source, index=index)
        chunk_ids.append(chunk["chunk_id"])
        rows.append(
            (
                video_id,
                chunk["chunk_id"],
                chunk["start_time"],
                chunk["end_time"],
                chunk.get("segment_ids", []),
                chunk["text"],
                chunk.get("word_count"),
                chunk.get("link"),
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
            link,
            embedding
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (video_id, chunk_id) DO UPDATE SET
            start_time = EXCLUDED.start_time,
            end_time = EXCLUDED.end_time,
            segment_ids = EXCLUDED.segment_ids,
            text = EXCLUDED.text,
            word_count = EXCLUDED.word_count,
            link = EXCLUDED.link,
            embedding = EXCLUDED.embedding,
            updated_at = NOW()
        """,
        rows,
    )

    cur.execute(
        """
        DELETE FROM chunks
        WHERE video_id = %s
          AND NOT (chunk_id = ANY(%s::integer[]))
        """,
        (video_id, chunk_ids),
    )
    return len(rows)


def ingest_file(path: Path, *, cur: psycopg.Cursor | None = None) -> tuple[str, int]:
    document = load_chunks_document(path)
    source_file = path.name

    if cur is None:
        with connect() as conn:
            with conn.cursor() as inner_cur:
                ensure_schema(inner_cur)
                video_id, count = ingest_file(path, cur=inner_cur)
            conn.commit()
        return video_id, count

    video_id = upsert_video(cur, document, source_file=source_file)
    document["video_id"] = video_id
    count = upsert_chunks(cur, document, source=path)
    return video_id, count


def ingest_paths(paths: list[Path]) -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            ensure_schema(cur)
            for path in paths:
                video_id, count = ingest_file(path, cur=cur)
                print(f"Ingested {count} chunk(s) for video_id={video_id!r} from {path}")
        conn.commit()


def sync_chunked_directory(
    directory: Path = EMBEDDINGS_DIR,
    *,
    wipe: bool = False,
) -> None:
    paths = discover_chunk_files(directory)
    if not paths:
        print(f"No *{CHUNK_FILE_SUFFIX} files found in {directory}")
        return

    with connect() as conn:
        with conn.cursor() as cur:
            ensure_schema(cur)
            if wipe:
                wipe_database(cur)
                print("Wiped videos and chunks tables.")

            for path in paths:
                video_id, count = ingest_file(path, cur=cur)
                print(
                    f"Synced {count} chunk(s) for video_id={video_id!r} "
                    f"from {path.name}"
                )
        conn.commit()

    print(f"Finished syncing {len(paths)} file(s) from {directory}")


def search_chunks(
    query: str,
    *,
    limit: int = 5,
    video_id: str | None = None,
) -> list[dict[str, Any]]:
    embedding = generate_embedding(query)

    with connect() as conn:
        with conn.cursor() as cur:
            ensure_schema(cur)
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
                    link,
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
        if row.get("link"):
            print(f"Link: {row['link']}")
        preview = row["text"]
        if len(preview) > 280:
            preview = preview[:277] + "..."
        print(preview)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    sync_parser = subparsers.add_parser(
        "sync",
        help="Load all chunked JSON from transcriptions/chunked into Postgres",
    )
    sync_parser.add_argument(
        "--dir",
        type=Path,
        default=EMBEDDINGS_DIR,
        help=f"Directory containing *{CHUNK_FILE_SUFFIX} files (default: {EMBEDDINGS_DIR})",
    )
    sync_parser.add_argument(
        "--wipe",
        action="store_true",
        help="Delete all existing videos/chunks before loading (recommended for full refresh)",
    )

    ingest_parser = subparsers.add_parser("ingest", help="Load embedded chunk JSON into Postgres")
    ingest_parser.add_argument(
        "paths",
        nargs="+",
        type=Path,
        help=f"Embedded chunk JSON files (e.g. transcriptions/chunked/my_video{CHUNK_FILE_SUFFIX})",
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
        if args.command == "sync":
            sync_chunked_directory(args.dir, wipe=args.wipe)
            return 0

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
