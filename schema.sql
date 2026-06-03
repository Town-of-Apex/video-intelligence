-- Video intelligence: transcripts chunked and embedded for semantic search.
-- Embedding model: Ollama nomic-embed-text (768 dimensions).

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS videos (
    video_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    duration_seconds DOUBLE PRECISION,
    transcribed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS chunks (
    id BIGSERIAL PRIMARY KEY,
    video_id TEXT NOT NULL REFERENCES videos (video_id) ON DELETE CASCADE,
    chunk_id INTEGER NOT NULL,
    start_time DOUBLE PRECISION NOT NULL,
    end_time DOUBLE PRECISION NOT NULL,
    segment_ids INTEGER[] NOT NULL DEFAULT '{}',
    text TEXT NOT NULL,
    word_count INTEGER,
    embedding vector(768) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (video_id, chunk_id)
);

CREATE INDEX IF NOT EXISTS chunks_video_idx ON chunks (video_id);

CREATE INDEX IF NOT EXISTS chunks_embedding_idx
    ON chunks
    USING hnsw (embedding vector_cosine_ops);

-- Human-readable timestamp for citations (e.g. 12:34-14:08).
CREATE OR REPLACE FUNCTION format_timestamp(seconds DOUBLE PRECISION)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT
        CASE
            WHEN seconds IS NULL OR seconds < 0 THEN '00:00:00'
            ELSE
                LPAD(FLOOR(seconds / 3600)::TEXT, 2, '0') || ':' ||
                LPAD(FLOOR(MOD(seconds::NUMERIC, 3600) / 60)::TEXT, 2, '0') || ':' ||
                LPAD(FLOOR(MOD(seconds::NUMERIC, 60))::TEXT, 2, '0')
        END;
$$;

-- Semantic search over chunks; returns citation-friendly fields.
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
        1 - (c.embedding <=> query_embedding) AS similarity
    FROM chunks c
    JOIN videos v ON v.video_id = c.video_id
    WHERE filter_video_id IS NULL OR c.video_id = filter_video_id
    ORDER BY c.embedding <=> query_embedding
    LIMIT GREATEST(match_count, 1);
$$;
