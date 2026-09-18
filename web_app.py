"""FastAPI application for uploading media and downloading transcripts."""

from __future__ import annotations

import os
import shutil
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import convert
import transcribe
from transcript_exports import transcript_text, write_transcript_exports

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("APP_DATA_DIR", PROJECT_ROOT / "data"))
JOBS_DIR = DATA_DIR / "jobs"
FRONTEND_DIR = PROJECT_ROOT / "frontend" / "dist"
MODEL_SIZE = os.environ.get("WHISPER_MODEL", "tiny.en")
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(4 * 1024**3)))

AUDIO_EXTENSIONS = frozenset(
    {
        ".mp3",
        ".wav",
        ".aif",
        ".aiff",
        ".m4a",
        ".aac",
        ".flac",
        ".ogg",
        ".opus",
        ".wma",
    }
)
SUPPORTED_EXTENSIONS = convert.VIDEO_EXTENSIONS | AUDIO_EXTENSIONS
DOWNLOAD_MEDIA_TYPES = {
    "json": "application/json",
    "txt": "text/plain; charset=utf-8",
    "srt": "application/x-subrip; charset=utf-8",
}

app = FastAPI(title="Video Intelligence Transcriber", version="0.1.0")
executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="transcription")
jobs: dict[str, dict] = {}
jobs_lock = threading.Lock()


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _public_job(job: dict) -> dict:
    result = {
        key: value
        for key, value in job.items()
        if key not in {"source_path", "output_dir", "exports"}
    }
    if job["status"] == "completed":
        result["downloads"] = {
            file_format: f"/api/jobs/{job['id']}/transcript.{file_format}"
            for file_format in DOWNLOAD_MEDIA_TYPES
        }
    return result


def _set_job(job_id: str, **updates) -> None:
    with jobs_lock:
        jobs[job_id].update(updates)


def _process_job(job_id: str) -> None:
    with jobs_lock:
        job = jobs[job_id].copy()

    source_path = Path(job["source_path"])
    output_dir = Path(job["output_dir"])
    audio_path: Path | None = None
    _set_job(job_id, status="processing", stage="Loading media", started_at=_now())

    try:
        if convert.is_video(source_path):
            _set_job(job_id, stage="Extracting audio")
            audio_path = output_dir / "extracted_audio.mp3"
            convert.extract(source_path, audio_path)
            transcription_input = audio_path
        else:
            transcription_input = source_path

        _set_job(job_id, stage=f"Transcribing with {MODEL_SIZE}")
        segments, info = transcribe.transcribe(transcription_input, MODEL_SIZE)
        payload = transcribe.build_transcript(
            segments,
            info,
            video_id=job["filename"],
            title=Path(job["filename"]).stem.replace("_", " ").replace("-", " ").title(),
        )

        _set_job(job_id, stage="Writing transcript files")
        exports = write_transcript_exports(payload, output_dir)
        _set_job(
            job_id,
            status="completed",
            stage="Complete",
            completed_at=_now(),
            duration_seconds=payload["duration_seconds"],
            segment_count=len(payload["segments"]),
            transcript=transcript_text(payload),
            exports={key: str(value) for key, value in exports.items()},
        )
    except Exception as exc:
        _set_job(
            job_id,
            status="failed",
            stage="Failed",
            completed_at=_now(),
            error=str(exc),
        )
    finally:
        source_path.unlink(missing_ok=True)
        if audio_path is not None:
            audio_path.unlink(missing_ok=True)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "model": MODEL_SIZE}


@app.post("/api/jobs", status_code=status.HTTP_202_ACCEPTED)
async def create_job(file: UploadFile = File(...)) -> dict:
    original_name = Path(file.filename or "").name
    extension = Path(original_name).suffix.lower()
    if not original_name or extension not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type. Supported extensions: {supported}",
        )

    job_id = str(uuid.uuid4())
    output_dir = JOBS_DIR / job_id
    output_dir.mkdir(parents=True, exist_ok=False)
    source_path = output_dir / f"upload{extension}"
    size = 0

    try:
        with source_path.open("wb") as destination:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="Upload exceeds the configured size limit.",
                    )
                destination.write(chunk)
    except Exception:
        shutil.rmtree(output_dir, ignore_errors=True)
        raise
    finally:
        await file.close()

    job = {
        "id": job_id,
        "filename": original_name,
        "size_bytes": size,
        "status": "queued",
        "stage": "Waiting to transcribe",
        "model": MODEL_SIZE,
        "created_at": _now(),
        "source_path": str(source_path),
        "output_dir": str(output_dir),
    }
    with jobs_lock:
        jobs[job_id] = job
    executor.submit(_process_job, job_id)
    return _public_job(job)


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    with jobs_lock:
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found.")
        return _public_job(job)


@app.get("/api/jobs/{job_id}/transcript.{file_format}")
def download_transcript(job_id: str, file_format: str) -> FileResponse:
    if file_format not in DOWNLOAD_MEDIA_TYPES:
        raise HTTPException(status_code=404, detail="Transcript format not found.")
    with jobs_lock:
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found.")
        if job["status"] != "completed":
            raise HTTPException(status_code=409, detail="Transcript is not ready.")
        file_path = Path(job["exports"][file_format])

    return FileResponse(
        file_path,
        media_type=DOWNLOAD_MEDIA_TYPES[file_format],
        filename=file_path.name,
    )


if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
