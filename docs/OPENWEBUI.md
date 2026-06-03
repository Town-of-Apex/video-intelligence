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
docker compose -f docker_compose.yml up -d
```

Schema is applied on first boot via `schema.sql` mounted into `docker-entrypoint-initdb.d`.

## 2. Ingest chunks

```bash
uv sync
uv run python embed.py
uv run python database.py ingest emergency_contact_audio_chunks.json
```

## 3. Test retrieval (citations include timestamps)

```bash
uv run python database.py search "how do I add an emergency contact" --json
```

Each hit includes `video_title`, `time_range` (e.g. `00:00:00-00:02:57`), `start_time`, `end_time`, and `text`.

## 4. OpenWebUI pipeline (`openwebui_pipeline.py`)

Copy `openwebui_pipeline.py` into OpenWebUI (**Workspace → Functions → Add** or upload to the [Pipelines](https://github.com/open-webui/pipelines) server).

The pipe runs on each chat request when you select **Video Intelligence (RAG)**:

1. Embeds the latest user message via Ollama (`nomic-embed-text`).
2. Calls `search_video_chunks()` in Postgres (same SQL as `database.py search`).
3. Prepends a system message with numbered excerpts and citation instructions.
4. Forwards the full conversation to your chat API (default: Ollama `/v1/chat/completions`).

### Valves to set in the UI

| Valve | Typical value (OpenWebUI in Docker) |
|-------|-------------------------------------|
| `POSTGRES_HOST` | `host.docker.internal` |
| `POSTGRES_DB` | `video_intelligence` |
| `OLLAMA_HOST` | `http://host.docker.internal:11434` |
| `CHAT_API_BASE_URL` | `http://host.docker.internal:11434/v1` |
| `DEFAULT_CHAT_MODEL` | e.g. `llama3.2` (your Ollama chat model) |
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

- Re-running `ingest` upserts by `(video_id, chunk_id)`.
- If you change `schema.sql` on an existing volume, run migrations manually or recreate the volume (`docker compose ... down -v`).
- For production, move credentials out of compose into secrets and restrict network access.
