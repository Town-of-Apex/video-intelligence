# OpenWebUI + pgvector integration

This project stores transcript chunks in PostgreSQL with pgvector. OpenWebUI does not connect to arbitrary pgvector tables out of the box for RAG; you wire retrieval with a **custom Function** or **Pipeline** that calls this repo’s search CLI (or the same SQL from your own service).

## Topology

| Component | Where it runs | Endpoint |
|-----------|---------------|----------|
| PostgreSQL + pgvector | Docker (`docker_compose.yml`) | `localhost:5432` (host) / `host.docker.internal:5432` (from OpenWebUI container) |
| Ollama | Native app | `http://localhost:11434` |
| OpenWebUI | Docker | Uses Ollama at `http://host.docker.internal:11434` |

Use the same embedding model in ingest and search: **nomic-embed-text** (768 dims).

## 1. Start the database

```bash
docker compose -f docker-compose.yml up -d
```

Schema is applied on first boot via `schema.sql` mounted into `docker-entrypoint-initdb.d`.

## 2. Process videos and ingest chunks

```bash
uv sync
# Place .webm files in videos/unprocessed/, then run the full pipeline:
uv run python main.py
# Optional chunk tuning (defaults: 200 words, 50 overlap):
uv run python main.py --target-words 200 --overlap-words 50
uv run python database.py sync --wipe
# Or ingest specific files:
uv run python database.py ingest transcriptions/chunked/*_chunks.json
```

Chunk size and overlap can also be set via `.env`:

- `CHUNK_TARGET_WORDS=200`
- `CHUNK_OVERLAP_WORDS=50`

After changing chunk size or the embedding format, re-run chunking, embedding, and `database.py sync --wipe`.

## 3. Test retrieval (citations include timestamps)

```bash
uv run python database.py search "how do I enroll in benefits as a new hire" --json
uv run python database.py search "benefits enrollment" --expand-query --json
```

Each hit includes `video_title`, `time_range` (e.g. `00:00:00-00:02:57`), `start_time`, `end_time`, and `text`.

## 4. OpenWebUI pipeline (`openwebui_rag_poc.py`)

Copy `openwebui_rag_poc.py` into OpenWebUI (**Workspace → Functions → Add** or upload to the [Pipelines](https://github.com/open-webui/pipelines) server).

The pipe runs on each chat request when you select **Video Intelligence (RAG)**:

1. Optionally rewrites the user question using the video title catalog (`ENABLE_QUERY_EXPANSION`).
2. Embeds the query via your embedding server (`nomic-embed-text` or llama.cpp `/v1/embeddings`).
3. Retrieves candidates with hybrid search (`search_video_chunks_hybrid`: vector + transcript keywords + title fuzzy match).
4. Sends the top excerpts (with video title, timestamp, and link) to the chat model for the final answer.

### Valves to set in the UI

| Valve | Typical value (OpenWebUI in Docker) |
|-------|-------------------------------------|
| `POSTGRES_HOST` | `host.docker.internal` |
| `POSTGRES_PORT` | `5431` |
| `POSTGRES_DB` | `training_intelligence` |
| `CHAT_BACKEND` | `openai` (llama.cpp/vLLM), `ollama`, or `openrouter` |
| `EMBEDDING_BACKEND` | `openai`, `ollama`, or `openrouter` — independent from chat |
| `CHAT_API_KEY` | Required when `CHAT_BACKEND=openrouter` |
| `EMBEDDING_API_KEY` | Required when `EMBEDDING_BACKEND=openrouter` |
| `APP_NAME` / `APP_URL` | Sent to OpenRouter as `X-Title` / `HTTP-Referer` |
| `LLAMA_BASE_URL` | Chat model base URL (no `/v1` suffix) |
| `EMBEDDING_BASE_URL` | Embedding model base URL (no `/v1` suffix) |
| `RAG_TOP_K` | `5` (final excerpts) |
| `RAG_FETCH_K` | `15` (candidate pool) |
| `ENABLE_HYBRID_SEARCH` | `true` |
| `ENABLE_QUERY_EXPANSION` | `true` |
| `FILTER_VIDEO_ID` | optional, e.g. `emergency_contact_audio` |

### Dependencies inside the OpenWebUI / Pipelines container

```bash
pip install requests psycopg2-binary
```

### Alternative: subprocess search

If you mount this repo into the container, you can still shell out to `database.py search --json` from a custom function; the pipeline file is self-contained and does not require the repo on disk.

## 5. SQL from other services

```sql
SELECT * FROM search_video_chunks(
  $1::vector(768),
  5,
  NULL  -- or 'emergency_contact_audio' to scope one video
);
```

Generate `$1` with the same Ollama embedding model used at ingest time.

## Notes

- `database.py sync` loads every `transcriptions/chunked/*_chunks.json` file. Use `--wipe` for a full refresh. Re-runs upsert by source JSON filename and `(video_id, chunk_id)`; SharePoint `link` values are stored when present.
- Re-running `ingest` upserts by `(video_id, chunk_id)`.
- If you change `schema.sql` on an existing volume, run migrations manually or recreate the volume (`docker compose ... down -v`).
- For production, move credentials out of compose into secrets and restrict network access.
