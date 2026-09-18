import { StrictMode, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

type JobStatus = "queued" | "processing" | "completed" | "failed";

type Job = {
  id: string;
  filename: string;
  status: JobStatus;
  stage: string;
  model: string;
  transcript?: string;
  error?: string;
  duration_seconds?: number;
  segment_count?: number;
  downloads?: Record<"json" | "txt" | "srt", string>;
};

const accept = [
  ".mp3", ".wav", ".aif", ".aiff", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma",
  ".webm", ".mp4", ".m4v", ".mkv", ".avi", ".mov", ".wmv", ".flv",
  ".mpeg", ".mpg", ".ogv", ".3gp", ".ts",
].join(",");

function App() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!job || !["queued", "processing"].includes(job.status)) return;
    const timer = window.setTimeout(async () => {
      try {
        const response = await fetch(`/api/jobs/${job.id}`);
        if (!response.ok) throw new Error("Could not check transcription status.");
        setJob(await response.json());
      } catch (requestError) {
        setError(requestError instanceof Error ? requestError.message : "Status check failed.");
      }
    }, 1500);
    return () => window.clearTimeout(timer);
  }, [job]);

  function chooseFile(selected?: File) {
    if (!selected) return;
    setFile(selected);
    setJob(null);
    setError("");
    setCopied(false);
  }

  async function submit() {
    if (!file) return;
    setUploading(true);
    setError("");
    const body = new FormData();
    body.append("file", file);
    try {
      const response = await fetch("/api/jobs", { method: "POST", body });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "Upload failed.");
      setJob(result);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Upload failed.");
    } finally {
      setUploading(false);
    }
  }

  async function copyTranscript() {
    if (!job?.transcript) return;
    await navigator.clipboard.writeText(job.transcript);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  }

  const busy = uploading || job?.status === "queued" || job?.status === "processing";

  return (
    <div className="page">
      <header className="topbar">
        <div className="brand-mark" aria-hidden="true">A</div>
        <div>
          <p className="eyebrow">Town of Apex</p>
          <h1>Media Transcription</h1>
        </div>
      </header>

      <main>
        <section className="intro">
          <p className="kicker">Video Intelligence</p>
          <h2>Turn a recording into a transcript.</h2>
          <p>Upload video or audio, then copy the result or download it as TXT, SRT, or JSON.</p>
        </section>

        <section className="card" aria-labelledby="upload-heading">
          <div className="card-heading">
            <div>
              <p className="step">Step 1</p>
              <h3 id="upload-heading">Choose a recording</h3>
            </div>
            <span className="model">Fast model: tiny.en</span>
          </div>

          <button
            className={`dropzone ${dragging ? "dragging" : ""}`}
            type="button"
            onClick={() => inputRef.current?.click()}
            onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={(event) => {
              event.preventDefault();
              setDragging(false);
              chooseFile(event.dataTransfer.files[0]);
            }}
          >
            <span className="upload-icon" aria-hidden="true">↑</span>
            <strong>{file ? file.name : "Drop a video or audio file here"}</strong>
            <span>{file ? `${(file.size / 1024 / 1024).toFixed(1)} MB` : "or click to browse"}</span>
          </button>
          <input
            ref={inputRef}
            className="visually-hidden"
            type="file"
            accept={accept}
            onChange={(event) => chooseFile(event.target.files?.[0])}
          />

          <div className="actions">
            <p>Uploaded media is deleted after transcription.</p>
            <button className="primary" disabled={!file || busy} onClick={submit}>
              {uploading ? "Uploading…" : busy ? "Transcribing…" : "Create transcript"}
            </button>
          </div>

          {error && <div className="notice error" role="alert">{error}</div>}
          {job && job.status !== "completed" && (
            <div className={`notice ${job.status === "failed" ? "error" : ""}`} aria-live="polite">
              <div className={job.status === "failed" ? "status-dot failed" : "spinner"} />
              <div>
                <strong>{job.status === "failed" ? "Transcription failed" : job.stage}</strong>
                <p>{job.status === "failed" ? job.error : "Keep this page open while the recording is processed."}</p>
              </div>
            </div>
          )}
        </section>

        {job?.status === "completed" && (
          <section className="card result" aria-labelledby="result-heading">
            <div className="card-heading">
              <div>
                <p className="step complete">Complete</p>
                <h3 id="result-heading">{job.filename}</h3>
              </div>
              <div className="meta">
                <span>{Math.round(job.duration_seconds || 0)} sec</span>
                <span>{job.segment_count} segments</span>
              </div>
            </div>

            <div className="transcript-toolbar">
              <strong>Transcript</strong>
              <button className="secondary" onClick={copyTranscript}>
                {copied ? "Copied" : "Copy text"}
              </button>
            </div>
            <pre className="transcript">{job.transcript}</pre>
            <div className="downloads">
              <span>Download</span>
              {(["txt", "srt", "json"] as const).map((format) => (
                <a key={format} href={job.downloads?.[format]}>
                  {format.toUpperCase()}
                </a>
              ))}
            </div>
          </section>
        )}
      </main>
      <footer>Internal Town of Apex tool</footer>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
