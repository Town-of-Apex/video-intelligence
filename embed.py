"""Add Ollama embeddings to chunk JSON files."""

from __future__ import annotations

import json
import os
from pathlib import Path

from ollama import Client

from env_config import load_env_file, normalize_service_url

DEFAULT_OLLAMA_HOST = "http://localhost:11434"
DEFAULT_EMBEDDING_MODEL = "nomic-embed-text"

load_env_file()


def embedding_host() -> str:
    return normalize_service_url(
        os.getenv("OLLAMA_HOST", DEFAULT_OLLAMA_HOST),
        default=DEFAULT_OLLAMA_HOST,
    )


def embedding_model() -> str:
    return os.getenv("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)


def client() -> Client:
    return Client(host=embedding_host())


def chunk_embedding_text(chunk: dict, title: str) -> str:
    """Text sent to the embedding model.

    Prefixing the video title helps retrieval match topic-level questions
    (e.g. benefits enrollment) to the correct training video.
    """
    text = chunk["text"].strip()
    title = title.strip()
    if not title:
        return text
    return f"Video title: {title}\n\n{text}"


def generate_embedding(text: str) -> list[float]:
    response = client().embed(model=embedding_model(), input=text)
    return response["embeddings"][0]


def embed_chunks(chunks_path: str | Path) -> Path:
    path = Path(chunks_path)
    with path.open(encoding="utf-8") as handle:
        document = json.load(handle)

    title = document.get("title", "")
    for chunk in document["chunks"]:
        chunk["embedding"] = generate_embedding(chunk_embedding_text(chunk, title))

    with path.open("w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=2, ensure_ascii=False)

    return path


# Backwards-compatible alias
embed_chunkscript = embed_chunks


if __name__ == "__main__":
    import argparse

    from paths import EMBEDDINGS_DIR, ensure_media_dirs

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "chunks",
        nargs="?",
        type=Path,
        help="Chunk JSON (default: first *_chunks.json in transcriptions/embeddings/)",
    )
    args = parser.parse_args()

    ensure_media_dirs()
    chunks_path = args.chunks
    if chunks_path is None:
        candidates = sorted(EMBEDDINGS_DIR.glob("*_chunks.json"))
        if not candidates:
            parser.error(f"No chunk files found in {EMBEDDINGS_DIR}")
        chunks_path = candidates[0]

    saved = embed_chunks(chunks_path)
    print(f"Embedded chunks -> {saved}")
