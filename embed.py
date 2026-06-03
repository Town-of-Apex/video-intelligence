from ollama import Client
import json

client = Client(
    host="http://localhost:11434"
)


def generate_embedding(text: str) -> list[float]:
    response = client.embed(
        model="nomic-embed-text",
        input=text
    )

    return response["embeddings"][0]


def embed_chunkscript(chunks_json: str):
    with open(chunks_json, "r") as f:
        chunks = json.load(f)

    for chunk in chunks["chunks"]:
        embedding = generate_embedding(chunk["text"])
        chunk["embedding"] = embedding

    with open(chunks_json, "w") as f:
        json.dump(chunks, f, indent=2)


if __name__ == "__main__":
    chunks_json = "emergency_contact_audio_chunks.json"
    print('embed time')
    embed_chunkscript(chunks_json)