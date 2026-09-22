# Video Intelligence

Self-hosted transcription for Town training media. The day-one use case is
simple: run it on the Town server with Docker, upload a recording, download a
transcript (TXT / JSON / SRT), and put that file somewhere a SharePoint agent
(or a person) can read it.

There’s also a fuller custom RAG path in this repo (chunk → embed → Postgres →
OpenWebUI) if we ever want answers with timestamp citations instead of leaning
on Copilot. That path is optional — see below.

## What you need day one (transcription)

On the Town server:

```bash
docker compose up --build -d transcriber
```

Open `http://<server>:8081` (port is `TRANSCRIBER_PORT`, default `8081`).

1. Drop a video or audio file on the page (or use the file picker).
2. Wait for transcription (first run downloads the Whisper model into the data volume).
3. Copy the text, or download **TXT**, **JSON**, or **SRT**.
4. Drop the file into whatever library/folder your SharePoint agent uses.

That’s the whole short-term workflow. No Microsoft Graph app, no database, no
OpenWebUI required.

### Useful knobs

| Variable | Default | Purpose |
| --- | --- | --- |
| `TRANSCRIBER_PORT` | `8081` | Host port for the web UI |
| `WHISPER_MODEL` | `tiny.en` | faster-whisper model (`tiny.en` is fast; bump to `medium.en` / `large-v3` for better accuracy if the box can take it) |
| `MAX_UPLOAD_BYTES` | `4294967296` | Max upload size (~4 GB) |

Transcript exports and the Whisper model cache live in the `transcriber_data`
Docker volume. Uploaded media is deleted after processing.

Jobs are processed **one at a time** so a modest server doesn’t melt. Job state
is in-memory: if you restart the container, the on-screen job list clears, but
exports already written under the volume are still on disk. Prefer downloading
when the job finishes.

### API (if you need it)

- `POST /api/jobs` — multipart upload, field name `file`
- `GET /api/jobs/{id}` — status / transcript when done
- `GET /api/jobs/{id}/transcript.txt` (also `.json`, `.srt`)
- `GET /api/health`

### Local macOS dev (optional)

```bash
uv sync
cd frontend && npm install && cd ..
uv run uvicorn web_app:app --reload --port 8000
# other terminal:
cd frontend && npm run dev
```

UI: `http://localhost:5173` (Vite proxies `/api` to the backend).

## Why there’s also a custom DB / OpenWebUI path

Microsoft’s automatic Teams → transcript/summary pipeline has been flaky for us.
The backup is: **we** transcribe, then either hand the TXT to a SharePoint agent
or (later) put structured chunks in our own store.

The custom path exists so an AI can answer questions over training videos **with
timestamp-specific citations** — and, when the video already lives in SharePoint,
links that jump to that moment (`sharepoint_nav.py`). Example vibe:

> “How do I add an emergency contact?”
>
> …answer grounded in the transcript…
>
> Sources: *How to Add an Emergency Contact* — 01:12–01:45  
> (link opens the SharePoint stream player at that time)

That’s the kind of thing you don’t reliably get from “Copilot, summarize this
Teams recording,” and it’s why the pipeline was built custom instead of only
shipping files to Microsoft.

### Tradeoffs (read this before diving in)

| Approach | Upside | Cost / pain |
| --- | --- | --- |
| **Download TXT → SharePoint agent** (current short-term) | Simple, works with what we already have | Agent quality depends on how you feed it files; no first-class timestamp UX |
| **Custom DB + OpenWebUI** (optional in this repo) | Hybrid search, citations, SharePoint deep-links, we control the prompt | You need Postgres, embeddings, and a chat model — either **API tokens** or **hardware to self-host** (Ollama / llama.cpp). More ops. |
| **Copilot / MS auto transcript** | No extra stack | We’ve seen reliability issues; less control over citations |

You do **not** need the custom path for Craig’s day-one job. It’s here so
someone can stand it up later if we decide Copilot + SharePoint agents aren’t
enough.

### How that pipeline fits together (high level)

```
videos/unprocessed/
    → extract audio
    → Whisper transcript JSON
    → chunk + (optional) SharePoint timestamp links
    → embed (Ollama / compatible API)
    → Postgres + pgvector
    → OpenWebUI function/pipe asks DB, answers with citations
```

Entry points if you want to poke at it:

- `main.py` — folder ingest through chunk/embed
- `database.py` — sync / ingest / search CLI
- `openwebui_rag_poc.py` — OpenWebUI pipe
- `docs/OPENWEBUI.md` — setup details (DB is on host port **5431** in compose)
- `plan.md` — older aspirational design notes (the web app API in there is not what shipped)

Start only Postgres when experimenting with RAG:

```bash
docker compose up -d postgres
```

Wiring completed **web** jobs into this RAG path is still a future step. Today
the web UI and the CLI RAG pipeline are separate tracks that share transcription
ideas, not one button.

## Repo map (short)

| Path | Role |
| --- | --- |
| `web_app.py`, `frontend/` | Phase 1 upload UI + API |
| `transcribe.py`, `transcript_exports.py`, `convert.py` | Whisper + TXT/JSON/SRT |
| `main.py`, `chunk.py`, `embed.py`, `database.py`, `schema.sql` | Optional RAG ingest |
| `sharepoint_nav.py` | Build “open video at timestamp” URLs (not Graph upload) |
| `openwebui_rag_poc.py`, `docs/OPENWEBUI.md` | Chat-over-transcripts experiment |

## Smoke check

1. `docker compose up --build -d transcriber`
2. Hit `/api/health`
3. Upload a short clip
4. Download TXT (and optionally JSON/SRT)
5. Confirm you can open/copy the transcript and drop it where the SharePoint agent expects files
