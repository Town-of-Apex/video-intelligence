# Video Intelligence / Training Assistant

Town training videos are transcribed and loaded into an AI **Training Assistant**
so staff can ask how-to questions and get answers grounded in the real training
content — with links that open the SharePoint video at the right moment.

---

## Try the Training Assistant (start here)

You do **not** need to run any code from this repo to try the assistant.

### Requirements

1. Be on the Town’s firewalled **TOA** network (office / VPN as your IT setup requires).
2. Open a browser and go to:

   **[http://10.9.81.141:3000](http://10.9.81.141:3000)**

   That address is Open WebUI running on a Jetson Thor machine. It hosts the
   **Nemotron** model and a Knowledge base built from the training transcripts.

### Steps

1. Open the link above (on TOA).
2. Sign in if prompted (use whatever account was set up for you).
3. In the model / chat picker, choose **Training Assistant** (not a generic chat model).
4. Ask a training question in plain English.
5. When the answer cites a source, use the SharePoint link to jump into the video
   at that timestamp (you’ll need SharePoint access as usual).

### Example questions

- How do I add an emergency contact?
- How do I enter weekly time in Apex WFM?
- How do I create a requisition for a stock item?
- Where do I find my paystub or update direct deposit?

### Tips

| Tip | Why it helps |
| --- | --- |
| Ask about a specific Town process or system | The Knowledge base is training transcripts, not the whole internet |
| Mention the system name when you know it (Infor, Apex WFM, FSM, etc.) | Narrows retrieval to the right video |
| Follow the SharePoint link in the sources | Opens the training video near the relevant moment |
| If the page won’t load | Confirm you’re on **TOA**; the server is not reachable from the public internet |

### If something doesn’t work

| Symptom | What to check |
| --- | --- |
| Browser can’t reach `10.9.81.141:3000` | Connected to **TOA**? Try again on Town network / VPN |
| Chat works but answers seem generic / unhelpful | Model is set to **Training Assistant**, not another model |
| Link opens SharePoint but video doesn’t play | Your SharePoint permissions / video still in the training Videos folder |
| Need a new video added to the assistant | Ask the technical owner — new media goes through the transcript pipeline below |

More detail on Knowledge ingest (for maintainers): [`docs/OPENWEBUI.md`](docs/OPENWEBUI.md).

---

## What this repo is for

This repository builds the transcript files the assistant uses. Day-to-day use of
the assistant is in Open WebUI (above). The sections below are for people who
process new training videos or maintain the pipeline.

```
Training video (already on SharePoint)
    → this repo (transcribe + chunk)
    → transcriptions/owui_format/{stem}_chunks_for_owui.json
    → upload into Open WebUI Knowledge (Training Assistant)
    → staff ask questions at http://10.9.81.141:3000
```

Existing training transcripts are already migrated into
`transcriptions/owui_format/` and loaded into the live Knowledge base. New videos
still need to be processed and uploaded when they are added.

---

## Process a new training video (CLI)

```bash
uv sync
# Drop videos into videos/unprocessed/
uv run python main.py
```

Each run writes a slim JSON file (no embeddings) with ~120s transcript windows
and a SharePoint stream URL per chunk under
`transcriptions/owui_format/{stem}_chunks_for_owui.json`. Upload that file into
the Training Assistant’s Knowledge collection in Open WebUI.

Details: [`docs/OPENWEBUI.md`](docs/OPENWEBUI.md).

### Useful knobs

| Variable / flag | Default | Purpose |
| --- | --- | --- |
| `CHUNK_TARGET_SECONDS` / `--target-seconds` | `120` | Chunk window length |
| `CHUNK_OVERLAP_SECONDS` / `--overlap-seconds` | `15` | Overlap between windows |
| `--watch-prefix` | off | Prefix chunk text with a Markdown Watch link |
| `SHAREPOINT_*` | see `.env.example` | Stream deep-link location |

### Re-export from legacy chunk files

If you still have older `transcriptions/chunked/*_chunks.json` files (with
embeddings), convert them without re-transcribing:

```bash
uv run python chunk.py --migrate-legacy
# → transcriptions/owui_format/*_chunks_for_owui.json
```

---

## Manual transcriber (Docker web UI)

Separate track for one-off uploads → TXT / JSON / SRT downloads (does **not**
feed the Training Assistant Knowledge base by itself).

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

### Local macOS / desktop dev (optional)

```bash
uv sync
cd frontend && npm install && cd ..
uv run uvicorn web_app:app --reload --port 8000
# other terminal:
cd frontend && npm run dev
```

UI: `http://localhost:5173` (Vite proxies `/api` to the backend).

---

## Why SharePoint links + Open WebUI

Training answers should cite the moment in the video. When the file already
lives in SharePoint, each chunk carries a stream URL that opens at that time
(`sharepoint_nav.py`). Open WebUI stores and retrieves the JSON; this repo does
not run a custom embeddings database.

Example:

> “How do I add an emergency contact?”
>
> …answer grounded in the transcript…
>
> Sources: *How to Add an Emergency Contact* — with a link that opens the
> SharePoint player at that timestamp.

### Tradeoffs

| Approach | Upside | Cost / pain |
| --- | --- | --- |
| **Training Assistant in Open WebUI** (staff use) | Ask in plain English; Knowledge + citations | Must be on TOA; depends on Thor host |
| **`main.py` → OWUI Knowledge** (ingest) | Timestamp links, controlled chunking, OWUI owns RAG | Manual Knowledge upload for new videos |
| **Docker web UI → TXT** | Fast one-off transcripts | Does not update the Training Assistant by itself |
| **Copilot / MS auto transcript** | No extra stack | Less control over citations |

### Future

- Point Open WebUI Knowledge at a **synced folder** of `*_chunks_for_owui.json`
  so new videos don’t need a manual upload step.
- Fold the CLI into the Docker web app: upload → place on SharePoint →
  transcribe → write OWUI JSON into that Knowledge location. Today `main.py`
  and the web UI remain separate.

---

## Repo map

| Path | Role |
| --- | --- |
| `main.py`, `chunk.py`, `sharepoint_nav.py` | Folder ingest → `transcriptions/owui_format/` |
| `web_app.py`, `frontend/` | Manual upload UI + API (TXT/JSON/SRT) |
| `transcribe.py`, `transcript_exports.py`, `convert.py` | Whisper + exports |
| `docs/OPENWEBUI.md` | Knowledge ingest + Training Assistant notes |
| `example_chunks_for_owui.json` | Canonical export shape |

---

## Smoke checks

**Training Assistant (staff)**

1. On **TOA**, open [http://10.9.81.141:3000](http://10.9.81.141:3000)
2. Select **Training Assistant**
3. Ask: “How do I add an emergency contact?”
4. Confirm the answer cites training content and includes a usable SharePoint link

**OWUI export (maintainers)**

1. Put a short clip in `videos/unprocessed/`
2. `uv run python main.py --no-move`
3. Confirm `transcriptions/owui_format/*_chunks_for_owui.json` has `link` fields and no embeddings
4. Upload that file into the Training Assistant Knowledge collection

**Web UI (maintainers)**

1. `docker compose up --build -d`
2. Hit `/api/health`
3. Upload a short clip and download TXT
