"""
OpenWebUI Pipe: inject video transcript RAG context before the chat LLM runs.

Install in OpenWebUI (Workspace → Functions → add pipeline) or on the Pipelines server.
Requires: requests, psycopg2-binary (pgvector is server-side in Postgres).

Defaults assume OpenWebUI runs in Docker and Postgres/Ollama run on the host:
  POSTGRES_HOST=host.docker.internal
  OLLAMA_HOST=http://host.docker.internal:11434
"""

from __future__ import annotations

import json
from typing import Any, Iterator

import requests
from pydantic import BaseModel, Field

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:  # pragma: no cover
    psycopg2 = None  # type: ignore[assignment]

EMBEDDING_DIMENSIONS = 768

SYSTEM_PROMPT = """You answer questions about ingested video transcripts.
Use only the retrieved transcript excerpts below. If they do not contain enough
information, say so clearly instead of guessing.

When you use a passage, cite it inline as [n] matching the source numbers below.
At the end, include a "Sources" section listing each [n] with video title and time range.

--- Retrieved transcript excerpts ---
{context}
--- End excerpts ---"""


class Pipe:
    """RAG pipe: embed query → pgvector search → augment messages → forward to chat API."""

    class Valves(BaseModel):
        POSTGRES_HOST: str = Field(
            default="host.docker.internal",
            description="Postgres host (use host.docker.internal from OpenWebUI container).",
        )
        POSTGRES_PORT: int = Field(default=5432, description="Postgres port.")
        POSTGRES_DB: str = Field(
            default="video_intelligence",
            description="Database name (matches docker_compose.yml).",
        )
        POSTGRES_USER: str = Field(default="postgres", description="Postgres user.")
        POSTGRES_PASSWORD: str = Field(default="password", description="Postgres password.")

        OLLAMA_HOST: str = Field(
            default="http://host.docker.internal:11434",
            description=(
                "Ollama base URL for embeddings (no /v1 suffix). "
                "If Ollama is running natively on your host (not in Docker), "
                "then 'host.docker.internal' lets containers reach services "
                "on your host machine. On Windows or Mac, this will access "
                "the Ollama app running locally (e.g., http://localhost:11434 "
                "from your host OS, but http://host.docker.internal:11434 from inside Docker). "
                "If you're running OpenWebUI outside Docker, you may need to use 'http://localhost:11434' instead."
            ),
        )
   
        EMBEDDING_MODEL: str = Field(
            default="nomic-embed-text",
            description="Must match the model used at ingest time (768 dims).",
        )

        CHAT_API_BASE_URL: str = Field(
            default="http://host.docker.internal:11434/v1",
            description="OpenAI-compatible chat API (Ollama /v1 or other provider).",
        )
        CHAT_API_KEY: str = Field(
            default="",
            description="Bearer token if required; leave empty for Ollama.",
        )
        DEFAULT_CHAT_MODEL: str = Field(
            default="",
            description=(
                "Model id sent to the chat API when the request model is this pipe's id. "
                "Leave empty to strip only the NAME_PREFIX from body['model']."
            ),
        )
        NAME_PREFIX: str = Field(
            default="",
            description="Optional prefix on model ids to strip before forwarding (e.g. 'ollama/').",
        )

        RAG_TOP_K: int = Field(default=5, description="Number of chunks to retrieve.")
        RAG_MIN_SIMILARITY: float = Field(
            default=0.0,
            description="Drop hits below this cosine similarity (0–1).",
        )
        FILTER_VIDEO_ID: str = Field(
            default="",
            description="If set, search only this video_id; otherwise search all videos.",
        )
        MAX_CHUNK_CHARS: int = Field(
            default=1200,
            description="Truncate each chunk's text in the injected context.",
        )
        ENABLE_RAG: bool = Field(
            default=True,
            description="Set false to forward requests without retrieval (debugging).",
        )

    def __init__(self):
        self.valves = self.Valves()
        self.id = "video_intelligence_rag"
        self.name = "Video Intelligence (RAG)"

    def pipes(self) -> list[dict[str, str]]:
        return [{"id": f"{self.id}", "name": self.name}]

    def get_models(self) -> list[dict[str, str]]:
        return self.pipes()

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.valves.CHAT_API_KEY:
            headers["Authorization"] = f"Bearer {self.valves.CHAT_API_KEY}"
        return headers

    @staticmethod
    def _message_text(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    parts.append(str(part.get("text", "")))
            return "\n".join(parts).strip()
        return str(content) if content is not None else ""

    def _last_user_message(self, messages: list[dict[str, Any]]) -> str:
        for message in reversed(messages):
            if message.get("role") == "user":
                text = self._message_text(message.get("content", ""))
                if text:
                    return text
        return ""

    def embed_query(self, text: str) -> list[float]:
        url = f"{self.valves.OLLAMA_HOST.rstrip('/')}/api/embed"
        response = requests.post(
            url,
            json={"model": self.valves.EMBEDDING_MODEL, "input": text},
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
        embeddings = data.get("embeddings") or []
        if not embeddings:
            raise ValueError("Ollama /api/embed returned no embeddings")
        vector = embeddings[0]
        if len(vector) != EMBEDDING_DIMENSIONS:
            raise ValueError(
                f"Expected {EMBEDDING_DIMENSIONS}-dim embedding, got {len(vector)}"
            )
        return vector

    def search_chunks(self, query: str) -> list[dict[str, Any]]:
        if psycopg2 is None:
            raise RuntimeError("psycopg2 is not installed; pip install psycopg2-binary")

        embedding = self.embed_query(query)
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
                rows = list(cur.fetchall())
        finally:
            conn.close()

        min_sim = self.valves.RAG_MIN_SIMILARITY
        return [dict(row) for row in rows if float(row["similarity"]) >= min_sim]

    def format_context(self, hits: list[dict[str, Any]]) -> str:
        if not hits:
            return "(No transcript chunks matched this query.)"

        lines: list[str] = []
        max_chars = self.valves.MAX_CHUNK_CHARS
        for index, hit in enumerate(hits, start=1):
            text = hit["text"]
            if len(text) > max_chars:
                text = text[: max_chars - 3] + "..."
            lines.append(
                f"[{index}] {hit['video_title']} ({hit['time_range']}) "
                f"video_id={hit['video_id']} similarity={float(hit['similarity']):.3f}\n"
                f"{text}"
            )
        return "\n\n".join(lines)

    def inject_rag(self, body: dict[str, Any]) -> dict[str, Any]:
        messages = list(body.get("messages") or [])
        if not messages:
            return body

        query = self._last_user_message(messages)
        if not query:
            return body

        try:
            hits = self.search_chunks(query)
            context = self.format_context(hits)
        except Exception as exc:
            context = f"(Retrieval failed: {exc})"

        system_content = SYSTEM_PROMPT.format(context=context)
        if messages and messages[0].get("role") == "system":
            messages[0] = {
                **messages[0],
                "content": f"{self._message_text(messages[0].get('content', ''))}\n\n{system_content}".strip(),
            }
        else:
            messages.insert(0, {"role": "system", "content": system_content})

        return {**body, "messages": messages}

    def _resolve_chat_model(self, body: dict[str, Any]) -> str:
        model = body.get("model", "") or ""
        prefix = self.valves.NAME_PREFIX
        if prefix and model.startswith(prefix):
            model = model[len(prefix) :]
        if self.valves.DEFAULT_CHAT_MODEL and (
            not model or model == self.id or model.endswith(self.id)
        ):
            return self.valves.DEFAULT_CHAT_MODEL
        return model or self.valves.DEFAULT_CHAT_MODEL or "llama3.2"

    def pipe(
        self,
        body: dict[str, Any],
        __user__: dict[str, Any] | None = None,
    ) -> dict[str, Any] | Iterator[bytes] | str:
        if self.valves.ENABLE_RAG:
            body = self.inject_rag(body)

        model_id = self._resolve_chat_model(body)
        payload = {**body, "model": model_id}
        stream = bool(body.get("stream", False))

        try:
            response = requests.post(
                url=f"{self.valves.CHAT_API_BASE_URL.rstrip('/')}/chat/completions",
                json=payload,
                headers=self._headers(),
                stream=stream,
                timeout=600,
            )
            response.raise_for_status()
            if stream:
                return response.iter_lines()
            return response.json()
        except Exception as exc:
            if stream:
                def _error_stream() -> Iterator[str]:
                    yield json.dumps(
                        {
                            "choices": [
                                {
                                    "delta": {"content": f"Pipeline error: {exc}"},
                                    "finish_reason": "stop",
                                }
                            ]
                        }
                    )

                return _error_stream()
            return f"Pipeline error: {exc}"
