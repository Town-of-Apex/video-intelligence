"""
Video Intelligence RAG (Postgres + pgvector)
title: Video Intelligence Postgres RAG Pipe
author: video-intelligence
version: 0.1.0
required_open_webui_version: 0.4.xx
license: MIT

Proof-of-concept OpenWebUI pipe for this project:
- Queries pre-embedded transcript chunks in PostgreSQL (pgvector).
- Embeds the user query with Ollama (nomic-embed-text, 768 dims).
- Returns answers with video title + timestamp citations.

No document upload or ingest here — chunks are loaded via database.py ingest.
"""

from __future__ import annotations

import os
from typing import Any, Callable, Optional

import requests
from pydantic import BaseModel, Field

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:  # pragma: no cover
    psycopg2 = None  # type: ignore[assignment]

EMBEDDING_DIMENSIONS = 768


class Pipe:
    class Valves(BaseModel):
        POSTGRES_HOST: str = Field(
            default=os.getenv("POSTGRES_HOST", "host.docker.internal"),
            description="Postgres host (host.docker.internal from OpenWebUI in Docker).",
        )
        POSTGRES_PORT: int = Field(
            default=int(os.getenv("POSTGRES_PORT", "5432")),
            description="Postgres port.",
        )
        POSTGRES_DB: str = Field(
            default=os.getenv("POSTGRES_DB", "video_intelligence"),
            description="Database name.",
        )
        POSTGRES_USER: str = Field(
            default=os.getenv("POSTGRES_USER", "postgres"),
            description="Postgres user.",
        )
        POSTGRES_PASSWORD: str = Field(
            default=os.getenv("POSTGRES_PASSWORD", "password"),
            description="Postgres password.",
        )

        OLLAMA_BASE_URL: str = Field(
            default=os.getenv("OLLAMA_HOST", "http://host.docker.internal:11434"),
            description="Ollama base URL (no /v1 suffix).",
        )
        OLLAMA_MODEL: str = Field(
            default=os.getenv("OLLAMA_MODEL", "gemma3:4b"),
            description="Ollama chat model for generating responses.",
        )
        EMBEDDING_MODEL: str = Field(
            default=os.getenv("EMBEDDING_MODEL", "nomic-embed-text"),
            description="Must match the model used at ingest time (768 dims).",
        )

        RAG_TOP_K: int = Field(
            default=int(os.getenv("RAG_TOP_K", "5")),
            description="Number of transcript chunks to retrieve.",
        )
        FILTER_VIDEO_ID: str = Field(
            default=os.getenv("FILTER_VIDEO_ID", ""),
            description="Optional video_id to restrict search to one video.",
        )

    def __init__(self):
        self.valves = self.Valves()
        self.name = "Video Intelligence RAG (Postgres PoC)"

    async def _emit(
        self,
        emitter: Optional[Callable],
        description: str,
        *,
        done: bool = False,
        message: Optional[str] = None,
    ) -> None:
        if emitter is None:
            return
        if message is not None:
            await emitter({"type": "message", "data": {"content": message}})
        await emitter(
            {"type": "status", "data": {"description": description, "done": done}}
        )

    def _embed_query(self, text: str) -> list[float]:
        url = f"{self.valves.OLLAMA_BASE_URL.rstrip('/')}/api/embed"
        response = requests.post(
            url,
            json={"model": self.valves.EMBEDDING_MODEL, "input": text},
            timeout=120,
        )
        response.raise_for_status()
        embeddings = response.json().get("embeddings") or []
        if not embeddings:
            raise ValueError("Ollama /api/embed returned no embeddings")
        vector = embeddings[0]
        if len(vector) != EMBEDDING_DIMENSIONS:
            raise ValueError(
                f"Expected {EMBEDDING_DIMENSIONS}-dim embedding, got {len(vector)}"
            )
        return vector

    def _search_chunks(self, query: str) -> list[dict[str, Any]]:
        if psycopg2 is None:
            raise RuntimeError("psycopg2 is not installed; pip install psycopg2-binary")

        embedding = self._embed_query(query)
        embedding_literal = "[" + ",".join(str(float(x)) for x in embedding) + "]"
        video_filter = self.valves.FILTER_VIDEO_ID.strip() or None

        conn = psycopg2.connect(
            host=self.valves.POSTGRES_HOST,
            port=self.valves.POSTGRES_PORT,
            user=self.valves.POSTGRES_USER,
            password=self.valves.POSTGRES_PASSWORD,
            dbname=self.valves.POSTGRES_DB,
        )
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
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
                    FROM search_video_chunks(
                        %s::vector(768),
                        %s::integer,
                        %s::text
                    )
                    """,
                    (embedding_literal, self.valves.RAG_TOP_K, video_filter),
                )
                return [dict(row) for row in cur.fetchall()]
        finally:
            conn.close()

    def _build_context(self, hits: list[dict[str, Any]]) -> tuple[str, list[str]]:
        if not hits:
            return "(No transcript chunks matched this query.)", []

        grouped: dict[str, list[dict[str, Any]]] = {}
        for hit in hits:
            grouped.setdefault(hit["video_id"], []).append(hit)

        context_blocks: list[str] = []
        source_info: list[str] = []

        for video_id, chunks in grouped.items():
            title = chunks[0]["video_title"]
            lines = [
                f"[{chunk['time_range']}] (similarity={float(chunk['similarity']):.3f}) "
                f"{chunk['text']}"
                for chunk in chunks
            ]
            context_blocks.append(f"=== {title} ({video_id}) ===\n" + "\n".join(lines))
            for chunk in chunks:
                source_info.append(
                    f"{title} @ {chunk['time_range']} "
                    f"(chunk {chunk['chunk_id']}, similarity={float(chunk['similarity']):.3f})"
                )

        return "\n\n".join(context_blocks), source_info

    def _generate_response(self, prompt: str) -> str:
        url = f"{self.valves.OLLAMA_BASE_URL.rstrip('/')}/api/generate"
        response = requests.post(
            url,
            json={"model": self.valves.OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=600,
        )
        response.raise_for_status()
        text = response.json().get("response", "").strip()
        if not text:
            raise ValueError("Ollama /api/generate returned an empty response")
        return text

    async def pipe(
        self,
        body: dict[str, Any],
        __user__: Optional[dict] = None,
        __event_emitter__: Optional[Callable] = None,
    ) -> Optional[dict]:
        try:
            await self._emit(__event_emitter__, "Connecting to Postgres...")

            messages = body.get("messages", [])
            if not messages or not isinstance(messages, list):
                raise ValueError("Invalid or missing messages.")

            chat_history = [
                msg.get("content", "")
                for msg in messages[:-1]
                if msg.get("role") != "system"
            ]
            query = messages[-1].get("content", "").strip()
            if isinstance(query, list):
                query = " ".join(
                    part.get("text", "")
                    for part in query
                    if isinstance(part, dict) and part.get("type") == "text"
                ).strip()

            if not query:
                await self._emit(__event_emitter__, "Empty query.", done=True)
                return None

            await self._emit(__event_emitter__, "Searching transcript chunks...")
            hits = self._search_chunks(query)
            context, source_info = self._build_context(hits)

            for entry in source_info:
                await self._emit(__event_emitter__, f"Included in context → {entry}")

            full_conversation = "\n".join(f"User: {msg}" for msg in chat_history)
            context_prompt = f"""You are a helpful assistant with access to video transcript excerpts.
Answer the user query using only the provided context. If the context is insufficient, say so.
When you reference a passage, cite the timestamp range shown in brackets (e.g. 00:01:23-00:02:45).

Conversation history:
{full_conversation or "(none)"}

Transcript context:
{context}

User query:
{query}

Response:"""

            await self._emit(__event_emitter__, "Generating response...")
            response_text = self._generate_response(context_prompt)

            await self._emit(
                __event_emitter__,
                "Done.",
                done=True,
                message=response_text,
            )
            return {"status": "success", "query": query, "response": response_text}

        except Exception as exc:
            await self._emit(__event_emitter__, f"Error: {exc}", done=True)
            return {
                "status": "error",
                "error": {
                    "message": str(exc),
                    "detail": "Error during RAG pipeline execution.",
                },
            }
