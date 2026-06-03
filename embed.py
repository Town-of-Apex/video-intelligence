"""Add Ollama embeddings to chunk JSON files."""

from __future__ import annotations

import json
from pathlib import Path

from ollama import Client

client = Client(host="http://localhost:11434")


def generate_embedding(text: str) -> list[float]:
    response = client.embed(model="nomic-embed-text", input=text)
    return response["embeddings"][0]


def embed_chunks(chunks_path: str | Path) -> Path:
    path = Path(chunks_path)
    with path.open(encoding="utf-8") as handle:
        document = json.load(handle)

    for chunk in document["chunks"]:
        chunk["embedding"] = generate_embedding(chunk["text"])

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
