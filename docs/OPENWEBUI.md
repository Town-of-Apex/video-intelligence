# Open WebUI — Training Assistant (Knowledge upload)

Primary product path: transcribe training media → export slim chunk JSON with
SharePoint timestamp links → upload into Open WebUI Knowledge → chat with a
Training Assistant model. This repo does **not** run a custom embeddings DB or
a retrieval service for Open WebUI.

## Day-one flow

```
videos/unprocessed/
    → main.py (extract → Whisper → ~120s chunks + SharePoint links)
    → transcriptions/chunked/{stem}_chunks_for_owui.json
    → manual upload into Open WebUI Knowledge
    → Training Assistant model answers from Knowledge
```

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
# → transcriptions/chunked/foo_chunks_for_owui.json
```

### 2. Upload into Open WebUI Knowledge

1. Open Open WebUI → **Workspace → Knowledge** (or Collections).
2. Create or open a collection used by your Training Assistant model.
3. Upload the `*_chunks_for_owui.json` file(s).
4. Attach that Knowledge collection to the Training Assistant model.

Open WebUI owns embeddings and retrieval. Do not point OWUI at a custom
Postgres schema from this repo (that path was removed).

### 3. JSON shape (canonical)

Filename: `{stem}_chunks_for_owui.json`

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

No `embedding`, no `segment_ids`. Links come from `sharepoint_nav.py` only.

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
  `*_chunks_for_owui.json` so manual upload is unnecessary. Prefer OWUI’s own
  sync/folder features if available; do not add a large custom sync service here.
- **Web app fold-in:** upload in the Docker transcriber → auto SharePoint place
  + transcribe + write OWUI JSON into that Knowledge location. Today the web UI
  and `main.py` remain separate tracks.

## Manual web transcription (separate)

```bash
docker compose up --build -d
```

Opens the upload UI for TXT/JSON/SRT downloads. It does not yet emit
`*_chunks_for_owui.json`.
