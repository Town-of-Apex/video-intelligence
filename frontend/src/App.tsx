import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type ChangeEvent,
  type DragEvent,
  type KeyboardEvent,
} from "react";
import {
  ACCEPT_ATTR,
  createJob,
  formatBytes,
  getJob,
  isAcceptedFile,
  type Job,
  type JobStatus,
} from "./api";

type UiPhase = "idle" | "uploading" | JobStatus;

const POLL_MS = 1500;
const TERMINAL: ReadonlySet<JobStatus> = new Set(["completed", "failed"]);

function statusLabel(phase: UiPhase): string {
  switch (phase) {
    case "idle":
      return "Ready";
    case "uploading":
      return "Uploading";
    case "queued":
      return "Queued";
    case "processing":
      return "Processing";
    case "completed":
      return "Completed";
    case "failed":
      return "Failed";
    default:
      return "Ready";
  }
}

function App() {
  const inputId = useId();
  const statusId = useId();
  const dropzoneId = useId();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pollRef = useRef<number | null>(null);

  const [dragActive, setDragActive] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [phase, setPhase] = useState<UiPhase>("idle");
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copyState, setCopyState] = useState<"idle" | "copied" | "error">("idle");

  const stopPolling = useCallback(() => {
    if (pollRef.current !== null) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  useEffect(() => () => stopPolling(), [stopPolling]);

  const startPolling = useCallback(
    (jobId: string) => {
      stopPolling();

      const tick = async () => {
        try {
          const next = await getJob(jobId);
          setJob(next);
          setPhase(next.status);
          if (TERMINAL.has(next.status)) {
            stopPolling();
            if (next.status === "failed") {
              setError(next.error || "Transcription failed.");
            }
          }
        } catch (err) {
          stopPolling();
          setPhase("failed");
          setError(err instanceof Error ? err.message : "Polling failed.");
        }
      };

      void tick();
      pollRef.current = window.setInterval(() => {
        void tick();
      }, POLL_MS);
    },
    [stopPolling],
  );

  const reset = useCallback(() => {
    stopPolling();
    setSelectedFile(null);
    setPhase("idle");
    setJob(null);
    setError(null);
    setCopyState("idle");
    setDragActive(false);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }, [stopPolling]);

  const chooseFile = useCallback((file: File | null) => {
    setError(null);
    setCopyState("idle");
    if (!file) {
      setSelectedFile(null);
      return;
    }
    if (!isAcceptedFile(file)) {
      setSelectedFile(null);
      setError(
        "Unsupported file type. Choose a common video or audio format (for example .mp4, .mov, .mp3, .wav).",
      );
      return;
    }
    setSelectedFile(file);
    setJob(null);
    setPhase("idle");
  }, []);

  const onInputChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0] ?? null;
    chooseFile(file);
  };

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragActive(false);
    const file = event.dataTransfer.files?.[0] ?? null;
    chooseFile(file);
  };

  const onDragOver = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragActive(true);
  };

  const onDragLeave = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    if (event.currentTarget.contains(event.relatedTarget as Node | null)) {
      return;
    }
    setDragActive(false);
  };

  const onDropzoneKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      fileInputRef.current?.click();
    }
  };

  const upload = async () => {
    if (!selectedFile || phase === "uploading" || phase === "queued" || phase === "processing") {
      return;
    }

    stopPolling();
    setError(null);
    setCopyState("idle");
    setJob(null);
    setPhase("uploading");

    try {
      const created = await createJob(selectedFile);
      setJob(created);
      setPhase(created.status);
      if (TERMINAL.has(created.status)) {
        if (created.status === "failed") {
          setError(created.error || "Transcription failed.");
        }
        return;
      }
      startPolling(created.id);
    } catch (err) {
      setPhase("failed");
      setError(err instanceof Error ? err.message : "Upload failed.");
    }
  };

  const copyTranscript = async () => {
    const text = job?.transcript;
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setCopyState("copied");
      window.setTimeout(() => setCopyState("idle"), 2000);
    } catch {
      setCopyState("error");
    }
  };

  const busy =
    phase === "uploading" || phase === "queued" || phase === "processing";
  const stageText =
    phase === "uploading"
      ? "Sending file to the server"
      : job?.stage || (phase === "idle" ? "Select a media file to begin" : "—");

  return (
    <div className="page">
      <a className="skip-link" href="#main">
        Skip to main content
      </a>

      <header className="topbar">
        <div className="topbar-inner">
          <p className="brand">Town of Apex</p>
          <p className="product">Video Intelligence</p>
        </div>
      </header>

      <main id="main" className="main">
        <section className="hero" aria-labelledby="page-title">
          <h1 id="page-title">Transcript upload</h1>
          <p className="lede">
            Drop a training video or audio file to generate a plain-text transcript
            and downloadable JSON, TXT, and SRT exports.
          </p>
        </section>

        <section className="panel" aria-labelledby="upload-heading">
          <div className="panel-head">
            <h2 id="upload-heading">Upload media</h2>
            <p className="panel-sub">
              Accepted formats include MP4, MOV, MKV, WebM, MP3, WAV, and other
              common video or audio types.
            </p>
          </div>

          <div
            id={dropzoneId}
            className={`dropzone${dragActive ? " is-active" : ""}${busy ? " is-disabled" : ""}`}
            role="button"
            tabIndex={busy ? -1 : 0}
            aria-disabled={busy}
            aria-controls={inputId}
            aria-describedby={`${statusId} drop-hint`}
            onClick={() => {
              if (!busy) fileInputRef.current?.click();
            }}
            onKeyDown={onDropzoneKeyDown}
            onDragEnter={onDragOver}
            onDragOver={onDragOver}
            onDragLeave={onDragLeave}
            onDrop={onDrop}
          >
            <p className="drop-title">
              {selectedFile ? selectedFile.name : "Drop a file here, or browse"}
            </p>
            <p id="drop-hint" className="drop-hint">
              {selectedFile
                ? `${formatBytes(selectedFile.size)} · ready to upload`
                : "Video or audio · keyboard: Enter or Space to browse"}
            </p>
            <input
              ref={fileInputRef}
              id={inputId}
              className="sr-only"
              type="file"
              accept={ACCEPT_ATTR}
              disabled={busy}
              onChange={onInputChange}
            />
          </div>

          <div className="actions">
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => void upload()}
              disabled={!selectedFile || busy}
            >
              {busy ? "Working…" : "Start transcription"}
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={reset}
              disabled={phase === "uploading"}
            >
              Reset
            </button>
          </div>
        </section>

        <section
          className="panel status-panel"
          aria-labelledby="status-heading"
          aria-live="polite"
          aria-atomic="true"
        >
          <div className="panel-head">
            <h2 id="status-heading">Job status</h2>
          </div>

          <div className="status-row">
            <span
              className={`status-pill status-${phase}`}
              id={statusId}
            >
              {statusLabel(phase)}
            </span>
            <p className="stage">{stageText}</p>
          </div>

          {job && (
            <dl className="meta">
              <div>
                <dt>File</dt>
                <dd>{job.filename}</dd>
              </div>
              <div>
                <dt>Job ID</dt>
                <dd>
                  <code>{job.id}</code>
                </dd>
              </div>
              {typeof job.size_bytes === "number" && (
                <div>
                  <dt>Size</dt>
                  <dd>{formatBytes(job.size_bytes)}</dd>
                </div>
              )}
              {job.model && (
                <div>
                  <dt>Model</dt>
                  <dd>{job.model}</dd>
                </div>
              )}
              {typeof job.duration_seconds === "number" && (
                <div>
                  <dt>Duration</dt>
                  <dd>{Math.round(job.duration_seconds)}s</dd>
                </div>
              )}
              {typeof job.segment_count === "number" && (
                <div>
                  <dt>Segments</dt>
                  <dd>{job.segment_count}</dd>
                </div>
              )}
            </dl>
          )}

          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
        </section>

        {phase === "completed" && job?.transcript != null && (
          <section className="panel result-panel" aria-labelledby="result-heading">
            <div className="panel-head result-head">
              <div>
                <h2 id="result-heading">Transcript</h2>
                <p className="panel-sub">Plain text from the completed job.</p>
              </div>
              <div className="result-actions">
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => void copyTranscript()}
                >
                  {copyState === "copied" ? "Copied" : "Copy"}
                </button>
                {copyState === "error" && (
                  <span className="copy-error" role="status">
                    Could not copy. Select the text manually.
                  </span>
                )}
              </div>
            </div>

            <pre className="transcript" tabIndex={0}>
              {job.transcript || "(Empty transcript)"}
            </pre>

            {job.downloads && (
              <div className="downloads" aria-label="Download transcript formats">
                <h3 className="downloads-title">Downloads</h3>
                <ul className="download-list">
                  {job.downloads.json && (
                    <li>
                      <a className="download-link" href={job.downloads.json} download>
                        JSON
                      </a>
                    </li>
                  )}
                  {job.downloads.txt && (
                    <li>
                      <a className="download-link" href={job.downloads.txt} download>
                        TXT
                      </a>
                    </li>
                  )}
                  {job.downloads.srt && (
                    <li>
                      <a className="download-link" href={job.downloads.srt} download>
                        SRT
                      </a>
                    </li>
                  )}
                </ul>
              </div>
            )}
          </section>
        )}
      </main>

      <footer className="footer">
        <p>Internal staff tool · No sign-in required for this phase</p>
      </footer>
    </div>
  );
}

export default App;
