"""
Video Intelligence RAG (Postgres + pgvector)
title: Video Intelligence Postgres RAG Pipe
author: video-intelligence
version: 0.5.0
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


def merge_hits(
    hit_lists: list[list[dict[str, Any]]],
    *,
    top_k: int,
) -> list[dict[str, Any]]:
    best: dict[Any, dict[str, Any]] = {}

    for hits in hit_lists:
        for hit in hits:
            key = hit.get("chunk_pk") or (hit.get("video_id"), hit.get("chunk_id"))
            score = float(hit.get("combined_score") or hit.get("similarity") or 0.0)
            existing = best.get(key)
            if existing is None or score > float(
                existing.get("combined_score") or existing.get("similarity") or 0.0
            ):
                best[key] = hit

    return sorted(
        best.values(),
        key=lambda row: float(row.get("combined_score") or row.get("similarity") or 0.0),
        reverse=True,
    )[: max(top_k, 1)]


class Pipe:
    class Valves(BaseModel):
        POSTGRES_HOST: str = Field(
            default=os.getenv("POSTGRES_HOST", "host.docker.internal"),
            description="Postgres host.",
        )
        POSTGRES_PORT: int = Field(default=int(os.getenv("POSTGRES_PORT", "5431")))
        POSTGRES_DB: str = Field(
            default=os.getenv("POSTGRES_DB", "training_intelligence")
        )
        POSTGRES_USER: str = Field(default=os.getenv("POSTGRES_USER", "postgres"))
        POSTGRES_PASSWORD: str = Field(
            default=os.getenv("POSTGRES_PASSWORD", "password")
        )

        CHAT_BACKEND: str = Field(
            default=os.getenv("CHAT_BACKEND", "openai"),
            description="ollama | openai | openrouter — chat generation provider.",
        )
        EMBEDDING_BACKEND: str = Field(
            default=os.getenv("EMBEDDING_BACKEND", "openai"),
            description="ollama | openai | openrouter — embedding provider.",
        )
        CHAT_API_KEY: str = Field(
            default=os.getenv("CHAT_API_KEY", ""),
            description="API key for chat when CHAT_BACKEND=openrouter.",
        )
        EMBEDDING_API_KEY: str = Field(
            default=os.getenv("EMBEDDING_API_KEY", ""),
            description="API key for embeddings when EMBEDDING_BACKEND=openrouter.",
        )
        APP_NAME: str = Field(
            default=os.getenv("APP_NAME", "Video Intelligence RAG"),
            description="App title sent to OpenRouter (X-Title header).",
        )
        APP_URL: str = Field(
            default=os.getenv("APP_URL", "http://localhost"),
            description="App URL sent to OpenRouter (HTTP-Referer header).",
        )
        LLAMA_BASE_URL: str = Field(
            default=os.getenv("LLAMA_HOST", "http://host.docker.internal:11434"),
            description="Chat model base URL (no /v1 suffix).",
        )
        LLAMA_MODEL: str = Field(
            default=os.getenv("LLAMA_MODEL", "gemma-4-E2B.gguf"),
            description="Chat model for answers and optional query expansion.",
        )
        EMBEDDING_BASE_URL: str = Field(
            default=os.getenv("EMBEDDING_HOST", "http://host.docker.internal:11435"),
            description="Embedding model base URL (no /v1 suffix).",
        )
        EMBEDDING_MODEL: str = Field(
            default=os.getenv("EMBEDDING_MODEL", "nomic-embed-text-v1.5.gguf"),
            description="Embedding model (768 dims, must match ingest).",
        )

        RAG_TOP_K: int = Field(
            default=int(os.getenv("RAG_TOP_K", "5")),
            description="Final number of transcript excerpts sent to the chat model.",
        )
        RAG_FETCH_K: int = Field(
            default=int(os.getenv("RAG_FETCH_K", "15")),
            description="Candidate pool retrieved before trimming to RAG_TOP_K.",
        )
        ENABLE_HYBRID_SEARCH: bool = Field(
            default=os.getenv("ENABLE_HYBRID_SEARCH", "true").lower()
            in {"1", "true", "yes", "on"},
            description="Combine vector, keyword, and title matching.",
        )
        ENABLE_QUERY_EXPANSION: bool = Field(
            default=os.getenv("ENABLE_QUERY_EXPANSION", "true").lower()
            in {"1", "true", "yes", "on"},
            description="Rewrite the user question using the video title catalog.",
        )
        VECTOR_WEIGHT: float = Field(default=float(os.getenv("VECTOR_WEIGHT", "0.65")))
        TEXT_WEIGHT: float = Field(default=float(os.getenv("TEXT_WEIGHT", "0.20")))
        TITLE_WEIGHT: float = Field(default=float(os.getenv("TITLE_WEIGHT", "0.15")))
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

    def _chat_backend(self) -> str:
        return self.valves.CHAT_BACKEND.strip().lower()

    def _embedding_backend(self) -> str:
        return self.valves.EMBEDDING_BACKEND.strip().lower()

    def _chat_headers(self) -> dict[str, str]:
        if self._chat_backend() == "openrouter":
            return {
                "Authorization": f"Bearer {self.valves.CHAT_API_KEY}",
                "HTTP-Referer": self.valves.APP_URL,
                "X-Title": self.valves.APP_NAME,
            }
        return {}

    def _embedding_headers(self) -> dict[str, str]:
        if self._embedding_backend() == "openrouter":
            return {
                "Authorization": f"Bearer {self.valves.EMBEDDING_API_KEY}",
                "HTTP-Referer": self.valves.APP_URL,
                "X-Title": self.valves.APP_NAME,
            }
        return {}

    def _embed_query(self, text: str) -> list[float]:
        backend = self._embedding_backend()
        if backend == "openrouter" and not self.valves.EMBEDDING_API_KEY:
            raise ValueError(
                "EMBEDDING_BACKEND is openrouter but EMBEDDING_API_KEY is not configured."
            )

        headers = self._embedding_headers()
        if backend == "ollama":
            url = f"{self.valves.EMBEDDING_BASE_URL.rstrip('/')}/api/embed"
            payload = {"model": self.valves.EMBEDDING_MODEL, "input": text}
            response = requests.post(url, json=payload, headers=headers, timeout=120)
            response.raise_for_status()
            vector = response.json()["embeddings"][0]
        else:
            url = f"{self.valves.EMBEDDING_BASE_URL.rstrip('/')}/v1/embeddings"
            payload = {"model": self.valves.EMBEDDING_MODEL, "input": text}
            response = requests.post(url, json=payload, headers=headers, timeout=120)
            response.raise_for_status()
            vector = response.json()["data"][0]["embedding"]

        if len(vector) != EMBEDDING_DIMENSIONS:
            raise ValueError(f"Expected {EMBEDDING_DIMENSIONS} dims, got {len(vector)}")

        return vector

    def _generate(self, prompt: str, *, temperature: float = 0.2) -> str:
        backend = self._chat_backend()
        if backend == "openrouter" and not self.valves.CHAT_API_KEY:
            raise ValueError(
                "CHAT_BACKEND is openrouter but CHAT_API_KEY is not configured."
            )

        headers = self._chat_headers()
        if backend == "ollama":
            url = f"{self.valves.LLAMA_BASE_URL.rstrip('/')}/api/generate"
            payload = {
                "model": self.valves.LLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": temperature},
            }
            response = requests.post(url, json=payload, headers=headers, timeout=600)
            response.raise_for_status()
            text = response.json().get("response", "").strip()
        else:
            url = f"{self.valves.LLAMA_BASE_URL.rstrip('/')}/v1/chat/completions"
            payload = {
                "model": self.valves.LLAMA_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "stream": False,
            }
            response = requests.post(url, json=payload, headers=headers, timeout=600)
            response.raise_for_status()
            text = response.json()["choices"][0]["message"]["content"].strip()

        if not text:
            raise ValueError("Inference server returned an empty response")

        return text

    def _connect(self):
        if psycopg2 is None:
            raise RuntimeError("psycopg2 not installed; pip install psycopg2-binary")

        return psycopg2.connect(
            host=self.valves.POSTGRES_HOST,
            port=self.valves.POSTGRES_PORT,
            user=self.valves.POSTGRES_USER,
            password=self.valves.POSTGRES_PASSWORD,
            dbname=self.valves.POSTGRES_DB,
        )

    def _list_video_titles(self, cur) -> list[str]:
        cur.execute("SELECT title FROM videos ORDER BY title")
        return [row["title"] for row in cur.fetchall() if row.get("title")]

    def _expand_query(self, query: str, titles: list[str]) -> str:
        if not self.valves.ENABLE_QUERY_EXPANSION or not titles:
            return query

        catalog = "\n".join(f"- {title}" for title in titles)
        prompt = f"""You help search employee training video transcripts.

Available training videos:
{catalog}

Rewrite the user's question into a short search query (1-2 sentences) using words likely to appear in relevant transcripts. When a video title clearly matches the topic, include its key terms.

User question: {query}

Search query:"""

        expanded = self._generate(prompt, temperature=0.0).strip()
        if not expanded or expanded.lower() == query.lower():
            return query
        return expanded

    def _search_once(
        self,
        cur,
        *,
        query: str,
        fetch_k: int,
        video_filter: str | None,
    ) -> list[dict[str, Any]]:
        embedding_literal = (
            "[" + ",".join(str(float(x)) for x in self._embed_query(query)) + "]"
        )

        if self.valves.ENABLE_HYBRID_SEARCH:
            cur.execute(
                HYBRID_SEARCH_SQL,
                (
                    embedding_literal,
                    query,
                    fetch_k,
                    video_filter,
                    self.valves.VECTOR_WEIGHT,
                    self.valves.TEXT_WEIGHT,
                    self.valves.TITLE_WEIGHT,
                ),
            )
        else:
            cur.execute(VECTOR_SEARCH_SQL, (embedding_literal, fetch_k, video_filter))

        return [dict(row) for row in cur.fetchall()]

    def _search_chunks(self, query: str) -> tuple[list[dict[str, Any]], list[str]]:
        video_filter = self.valves.FILTER_VIDEO_ID.strip() or None
        search_queries = [query.strip()]
        notes: list[str] = []

        conn = self._connect()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                titles = self._list_video_titles(cur)
                expanded = self._expand_query(query, titles)
                if expanded not in search_queries:
                    search_queries.append(expanded)
                    notes.append(f"Expanded query: {expanded}")

                hit_lists = [
                    self._search_once(
                        cur,
                        query=search_query,
                        fetch_k=self.valves.RAG_FETCH_K,
                        video_filter=video_filter,
                    )
                    for search_query in search_queries
                ]
        finally:
            conn.close()

        hits = merge_hits(hit_lists, top_k=self.valves.RAG_TOP_K)
        return hits, notes

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
                    part.get("text", "")
                    for part in query
                    if isinstance(part, dict) and part.get("type") == "text"
                ).strip()
            if not query:
                return "Please send a text message."

            await self._status(__event_emitter__, "Searching transcripts...")
            hits, notes = self._search_chunks(query)

            for note in notes:
                await self._status(__event_emitter__, note)

            context_lines = [
                (
                    f"Video: {hit['video_title']}\n"
                    f"[{hit['time_range']}] {hit['text']}\n"
                    f"LINK: {hit.get('link') or '(no link)'}"
                )
                for hit in hits
            ] or ["(No matching transcript chunks.)"]

            for hit in hits:
                score = hit.get("combined_score", hit.get("similarity"))
                await self._status(
                    __event_emitter__,
                    (
                        f"Found → {hit['video_title']} @ {hit['time_range']} "
                        f"(score={float(score):.3f})"
                    ),
                )

            prompt = f"""Answer the user's question using only the transcript excerpts below.

Write like a helpful, conversational chatbot—not a formal report or documentation page. Use natural paragraphs and flowing prose. Do not use numbered lists, bullet points, or step-by-step outlines unless the user explicitly asks for a list.

When you reference a video segment, mention the video title and timestamp naturally in the sentence (for example, "In the Payroll Refresher video around 2:15…"). For every video link, embed it as a Markdown hyperlink with short, readable link text—never paste a raw URL into the response. Use the URL from each excerpt's LINK field as the href, with anchor text that fits the sentence (e.g., [this section on direct deposit](url) or [the relevant part of Invoice Approvals](url)).

If several segments apply, weave them into your answer conversationally rather than listing them one by one.

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
