# Open WebUI — Training Assistant

Staff use the live Training Assistant in Open WebUI. This doc is for
**maintainers** who process new videos or refresh Knowledge. For a
non-technical walkthrough, start with the top of [`README.md`](../README.md).

## Live instance (TOA network)

| Item | Value |
| --- | --- |
| URL | [http://10.9.81.141:3000](http://10.9.81.141:3000) |
| Host | Jetson Thor (Town network) |
| Network | Town firewalled **TOA** network only |
| Model to select | **Training Assistant** |
| Underlying LLM | Nemotron (hosted on the Thor) |
| Knowledge | Training transcript chunks (`*_chunks_for_owui.json`) already loaded for existing videos |

Open WebUI owns embeddings and retrieval. This repo does **not** run a custom
embeddings DB or a retrieval service for Open WebUI.

## Staff flow (no repo required)

1. Connect to **TOA**.
2. Open `http://10.9.81.141:3000`.
3. Choose **Training Assistant**.
4. Ask a how-to question; follow SharePoint source links into the video.

## Maintainer flow (new or updated videos)

```
videos/unprocessed/
    → main.py (extract → Whisper → ~120s chunks + SharePoint links)
    → transcriptions/owui_format/{stem}_chunks_for_owui.json
    → upload into Open WebUI Knowledge (Training Assistant collection)
    → answers available at http://10.9.81.141:3000
```

Existing media was migrated with `uv run python chunk.py --migrate-legacy`
(from legacy `transcriptions/chunked/*_chunks.json`, preserving SharePoint
timestamp links). Only **new** videos need the steps below.

### 1. Process a video (CLI)

Place files in `videos/unprocessed/`, then:

```bash
uv sync
uv run python main.py
# Optional tuning (defaults: 120s windows, 15s overlap):
uv run python main.py --target-seconds 120 --overlap-seconds 15
# Optional: prefix chunk text with a Markdown Watch link
uv run python main.py --watch-prefix
```

Or chunk an existing transcript:

```bash
uv run python chunk.py path/to/foo_transcript.json
# → transcriptions/owui_format/foo_chunks_for_owui.json

# One-shot: strip legacy transcriptions/chunked/*_chunks.json into owui_format/
uv run python chunk.py --migrate-legacy
```

### 2. Upload into Open WebUI Knowledge

1. On TOA, open [http://10.9.81.141:3000](http://10.9.81.141:3000).
2. Go to **Workspace → Knowledge** (or Collections).
3. Open the collection used by **Training Assistant**.
4. Upload the new `*_chunks_for_owui.json` file(s).
5. Confirm the Training Assistant model still has that Knowledge collection attached.

Do not point OWUI at a custom Postgres schema from this repo (that path was removed).

### 3. JSON shape (canonical)

Filename: `{stem}_chunks_for_owui.json`  
Location: `transcriptions/owui_format/`

```json
{
  "video_id": "How to Add an Emergency Contact.webm",
  "title": "How To Add An Emergency Contact",
  "total_duration_seconds": 179.11,
  "transcribed_at": "2026-06-12T17:20:13+00:00",
  "chunk_count": 2,
  "chunks": [
    {
      "chunk_id": 1,
      "start_time": 0.0,
      "end_time": 120.04,
      "text": "...",
      "link": "https://…/stream.aspx?id=…&nav=…"
    }
  ]
}
```

No `embedding`, no `segment_ids`. Links come from `sharepoint_nav.py` (or are
preserved from legacy chunk files during migration).

## Chunk tuning

| Variable / flag | Default | Purpose |
| --- | --- | --- |
| `CHUNK_TARGET_SECONDS` / `--target-seconds` | `120` | Target window length |
| `CHUNK_OVERLAP_SECONDS` / `--overlap-seconds` | `15` | Overlap between windows |
| `--watch-prefix` | off | Prefix text with `[Watch: title](link) (~Xs–Ys)` |

Chunks stay aligned to Whisper segment boundaries so timestamps stay accurate.

## SharePoint env

| Variable | Default |
| --- | --- |
| `SHAREPOINT_HOST` | `apexncorg.sharepoint.com` |
| `SHAREPOINT_SITE_NAME` | `TOAInnovations` |
| `SHAREPOINT_DOCUMENT_LIBRARY` | `Shared Documents` |
| `SHAREPOINT_VIDEO_FOLDER` | `Project Resources/Training Intelligence/Videos` |

Videos must already live at that folder path for timestamp links to open correctly.
`sharepoint_nav.py` builds URLs only; it does not upload files.

## Future (not built yet)

- **Synced folder:** point Open WebUI Knowledge at a watched directory of
  `transcriptions/owui_format/*_chunks_for_owui.json` so new videos don’t need a
  manual upload. Prefer OWUI’s own sync/folder features if available; do not add
  a large custom sync service here.
- **Web app fold-in:** upload in the Docker transcriber → auto SharePoint place
  + transcribe + write OWUI JSON into that Knowledge location. Today the web UI
  and `main.py` remain separate tracks.

## Manual web transcription (separate)

```bash
docker compose up --build -d
```

Opens the upload UI for TXT/JSON/SRT downloads. It does not yet emit
`*_chunks_for_owui.json` or update the Training Assistant Knowledge base.
