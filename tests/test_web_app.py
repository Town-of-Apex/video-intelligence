from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

import web_app


client = TestClient(web_app.app)


def test_health() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "model": "tiny.en"}


def test_rejects_unsupported_upload() -> None:
    response = client.post(
        "/api/jobs",
        files={"file": ("notes.pdf", b"not a media file", "application/pdf")},
    )
    assert response.status_code == 415


def test_accepts_audio_upload_without_processing(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(web_app, "JOBS_DIR", tmp_path)
    monkeypatch.setattr(web_app.executor, "submit", lambda *args: None)
    web_app.jobs.clear()

    response = client.post(
        "/api/jobs",
        files={"file": ("meeting.mp3", b"fake audio", "audio/mpeg")},
    )

    assert response.status_code == 202
    job = response.json()
    assert job["filename"] == "meeting.mp3"
    assert job["status"] == "queued"
    assert client.get(f"/api/jobs/{job['id']}").status_code == 200


def test_processes_audio_and_deletes_upload(monkeypatch, tmp_path: Path) -> None:
    source_path = tmp_path / "upload.mp3"
    source_path.write_bytes(b"fake audio")
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    job_id = "test-job"
    web_app.jobs.clear()
    web_app.jobs[job_id] = {
        "id": job_id,
        "filename": "training.mp3",
        "status": "queued",
        "source_path": str(source_path),
        "output_dir": str(output_dir),
    }
    segments = [
        SimpleNamespace(start=0.0, end=1.5, text="Hello Town."),
    ]
    info = SimpleNamespace(duration=1.5)
    monkeypatch.setattr(
        web_app.transcribe,
        "transcribe",
        lambda path, model: (segments, info),
    )

    web_app._process_job(job_id)

    job = web_app.jobs[job_id]
    assert job["status"] == "completed"
    assert job["transcript"] == "Hello Town.\n"
    assert set(job["exports"]) == {"json", "txt", "srt"}
    assert not source_path.exists()
