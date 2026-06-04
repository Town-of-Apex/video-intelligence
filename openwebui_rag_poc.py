"""
Video Intelligence RAG (Postgres + pgvector)
title: Video Intelligence Postgres RAG Pipe
author: video-intelligence
version: 0.3.0
required_open_webui_version: 0.4.xx
license: MIT
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
            description="Postgres host.",
        )
        POSTGRES_PORT: int = Field(default=int(os.getenv("POSTGRES_PORT", "5432")))
        POSTGRES_DB: str = Field(default=os.getenv("POSTGRES_DB", "video_intelligence"))
        POSTGRES_USER: str = Field(default=os.getenv("POSTGRES_USER", "postgres"))
        POSTGRES_PASSWORD: str = Field(default=os.getenv("POSTGRES_PASSWORD", "password"))

        OLLAMA_BASE_URL: str = Field(
            default=os.getenv("OLLAMA_HOST", "http://host.docker.internal:11434"),
            description="Ollama base URL (no /v1 suffix).",
        )
        OLLAMA_MODEL: str = Field(
            default=os.getenv("OLLAMA_MODEL", "gemma3:4b"),
            description="Ollama model for generating responses.",
        )
        EMBEDDING_MODEL: str = Field(
            default=os.getenv("EMBEDDING_MODEL", "nomic-embed-text"),
            description="Embedding model (768 dims, must match ingest).",
        )
        RAG_TOP_K: int = Field(default=int(os.getenv("RAG_TOP_K", "5")))
        FILTER_VIDEO_ID: str = Field(
            default=os.getenv("FILTER_VIDEO_ID", ""),
            description="Optional video_id filter.",
        )

    def __init__(self):
        self.valves = self.Valves()
        self.name = "Video Intelligence RAG (Postgres PoC)"

    async def _status(
        self,
        emitter: Optional[Callable],
        description: str,
        *,
        done: bool = False,
    ) -> None:
        if emitter:
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
        vector = response.json()["embeddings"][0]
        if len(vector) != EMBEDDING_DIMENSIONS:
            raise ValueError(f"Expected {EMBEDDING_DIMENSIONS} dims, got {len(vector)}")
        return vector

    def _search_chunks(self, query: str) -> list[dict[str, Any]]:
        if psycopg2 is None:
            raise RuntimeError("psycopg2 not installed; pip install psycopg2-binary")

        embedding_literal = "[" + ",".join(str(float(x)) for x in self._embed_query(query)) + "]"
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
                    SELECT video_title, time_range, text, similarity
                    FROM search_video_chunks(%s::vector(768), %s::integer, %s::text)
                    """,
                    (embedding_literal, self.valves.RAG_TOP_K, video_filter),
                )
                return [dict(row) for row in cur.fetchall()]
        finally:
            conn.close()

    def _generate(self, prompt: str) -> str:
        url = f"{self.valves.OLLAMA_BASE_URL.rstrip('/')}/api/generate"
        response = requests.post(
            url,
            json={"model": self.valves.OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=600,
        )
        response.raise_for_status()
        text = response.json().get("response", "").strip()
        if not text:
            raise ValueError("Ollama returned an empty response")
        return text

    async def pipe(
        self,
        body: dict[str, Any],
        __user__: Optional[dict] = None,
        __event_emitter__: Optional[Callable] = None,
    ) -> str:
        try:
            messages = body.get("messages", [])
            if not messages:
                raise ValueError("No messages in request.")

            query = messages[-1].get("content", "").strip()
            if isinstance(query, list):
                query = " ".join(
                    p.get("text", "")
                    for p in query
                    if isinstance(p, dict) and p.get("type") == "text"
                ).strip()
            if not query:
                return "Please send a text message."

            await self._status(__event_emitter__, "Searching transcripts...")
            hits = self._search_chunks(query)

            context_lines = [
                f"[{h['time_range']}] {h['text']}" for h in hits
            ] or ["(No matching transcript chunks.)"]

            for hit in hits:
                await self._status(
                    __event_emitter__,
                    f"Found → {hit['video_title']} @ {hit['time_range']}",
                )

            prompt = f"""Answer using only the transcript excerpts below. Each one comes from a training video that has been transcribed and timestamped. Cite specific portions of the video transcripts provided (by the timestamp) and ALWAYS provide the link to the best portion of the video to allow the user to continue learning by watching that part of the video. Copy the link EXACTLY in your response and give that link to the user in an easy-to-click format or copy/paste if necessary. 

Transcript excerpts:
{chr(10).join(context_lines)}

Question: {query}

Answer:"""

            await self._status(__event_emitter__, "Generating response...")
            answer = self._generate(prompt)
            await self._status(__event_emitter__, "Done.", done=True)
            return answer

        except Exception as exc:
            await self._status(__event_emitter__, f"Error: {exc}", done=True)
            return f"Error: {exc}"
