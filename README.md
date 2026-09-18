# Video Intelligence

A small, self-hosted transcription app for Town training media. Phase 1 accepts
video and audio uploads, transcribes them with faster-whisper, and provides
copyable transcripts plus JSON, TXT, and SRT downloads.

The existing chunking, embeddings, Postgres, and OpenWebUI RAG pipeline remain
in the repository but are not part of the web upload flow yet.

## Run locally on macOS

Requirements:

- Python 3.13 and [uv](https://docs.astral.sh/uv/)
- Node.js 22+

Install dependencies:

```bash
uv sync
cd frontend && npm install && cd ..
```

Start the API:

```bash
uv run uvicorn web_app:app --reload --port 8000
```

In another terminal, start the frontend:

```bash
cd frontend
npm run dev
```

Open `http://localhost:5173`. The Vite development server proxies `/api` to
the API. The first transcription downloads the configured Whisper model.

## Run with Docker

```bash
docker compose up --build transcriber
```

Open `http://localhost:8081`. The app is independent from OpenWebUI and can
run on the same Docker host without sharing a container.

Configuration:

| Variable | Default | Purpose |
| --- | --- | --- |
| `TRANSCRIBER_PORT` | `8081` | Host port for the web app |
| `WHISPER_MODEL` | `tiny.en` | faster-whisper model |
| `MAX_UPLOAD_BYTES` | `4294967296` | Maximum upload size |

Uploaded media is deleted after processing. Transcript exports and the Whisper
model cache both live in the `transcriber_data` Docker volume.

## API

- `POST /api/jobs` — multipart upload using the `file` field
- `GET /api/jobs/{id}` — status and transcript when complete
- `GET /api/jobs/{id}/transcript.json`
- `GET /api/jobs/{id}/transcript.txt`
- `GET /api/jobs/{id}/transcript.srt`
- `GET /api/health`

Jobs are intentionally processed one at a time so CPU transcription does not
overload a MacBook Air or the initial Town server. Job state is currently
in-memory; restarting the app clears the visible job list.

## Existing RAG pipeline

See `docs/OPENWEBUI.md` for the current CLI-based Postgres/pgvector and
OpenWebUI integration. Wiring successful web jobs into that pipeline is the
next phase.
