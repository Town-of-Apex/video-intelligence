# Video Intelligence

Self-hosted transcription for Town training media, plus an Open WebUI–ready
chunk export with SharePoint timestamp links.

## Day-one product path

```
videos/unprocessed/
    → main.py
    → transcriptions/chunked/{stem}_chunks_for_owui.json
    → manual upload into Open WebUI Knowledge
    → Training Assistant model
```

```bash
uv sync
# Drop videos into videos/unprocessed/
uv run python main.py
```

Each run writes a slim JSON file (no embeddings) with ~120s transcript windows
and a SharePoint stream URL per chunk. Upload that file into Open WebUI
Knowledge. Details: [`docs/OPENWEBUI.md`](docs/OPENWEBUI.md).

### Useful knobs

| Variable / flag | Default | Purpose |
| --- | --- | --- |
| `CHUNK_TARGET_SECONDS` / `--target-seconds` | `120` | Chunk window length |
| `CHUNK_OVERLAP_SECONDS` / `--overlap-seconds` | `15` | Overlap between windows |
| `--watch-prefix` | off | Prefix chunk text with a Markdown Watch link |
| `SHAREPOINT_*` | see `.env.example` | Stream deep-link location |

## Manual transcriber (Docker web UI)

Separate track for one-off uploads → TXT / JSON / SRT downloads (no OWUI
chunk export yet).

```bash
docker compose up --build -d
```

Open `http://<server>:8081` (port is `TRANSCRIBER_PORT`, default `8081`).

1. Drop a video or audio file on the page.
2. Wait for transcription.
3. Copy the text, or download **TXT**, **JSON**, or **SRT**.

| Variable | Default | Purpose |
| --- | --- | --- |
| `TRANSCRIBER_PORT` | `8081` | Host port for the web UI |
| `WHISPER_MODEL` | `tiny.en` | faster-whisper model |
| `MAX_UPLOAD_BYTES` | `4294967296` | Max upload size (~4 GB) |

Jobs are processed **one at a time**. Uploaded media is deleted after
processing. Exports and the Whisper cache live in the `transcriber_data` volume.

### API

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

## Why SharePoint links + Open WebUI

Training answers should cite the moment in the video. When the file already
lives in SharePoint, each chunk carries a stream URL that opens at that time
(`sharepoint_nav.py`). Open WebUI stores and retrieves the JSON; this repo does
not run a custom embeddings database or a retrieval service OWUI has to call.

Example vibe:

> “How do I add an emergency contact?”
>
> …answer grounded in the transcript…
>
> Sources: *How to Add an Emergency Contact* — with a link that opens the
> SharePoint player at that timestamp.

### Tradeoffs

| Approach | Upside | Cost / pain |
| --- | --- | --- |
| **`main.py` → OWUI Knowledge** (primary) | Timestamp links, we control chunking, OWUI owns RAG | Manual Knowledge upload for PoC |
| **Docker web UI → TXT** | Fast one-off transcripts | No first-class timestamp UX |
| **Copilot / MS auto transcript** | No extra stack | Less control over citations |

### Future

- Point Open WebUI Knowledge at a **synced folder** of `*_chunks_for_owui.json`
  (prefer OWUI’s own folder sync if available; no big custom sync system here).
- Fold the CLI into the Docker web app: upload → place on SharePoint →
  transcribe → write OWUI JSON into that Knowledge location. Today `main.py`
  and the web UI remain separate.

## Repo map

| Path | Role |
| --- | --- |
| `main.py`, `chunk.py`, `sharepoint_nav.py` | Primary: folder ingest → OWUI JSON |
| `web_app.py`, `frontend/` | Manual upload UI + API |
| `transcribe.py`, `transcript_exports.py`, `convert.py` | Whisper + TXT/JSON/SRT |
| `docs/OPENWEBUI.md` | Knowledge ingest steps |
| `example_chunks_for_owui.json` | Canonical export shape |

## Smoke check

**OWUI export**

1. Put a short clip in `videos/unprocessed/`
2. `uv run python main.py --no-move`
3. Confirm `transcriptions/chunked/*_chunks_for_owui.json` has `link` fields and no embeddings
4. Upload that file into Open WebUI Knowledge

**Web UI**

1. `docker compose up --build -d`
2. Hit `/api/health`
3. Upload a short clip and download TXT
