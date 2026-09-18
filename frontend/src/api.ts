export type JobStatus =
  | "queued"
  | "processing"
  | "completed"
  | "failed";

export type JobDownloads = {
  json?: string;
  txt?: string;
  srt?: string;
};

export type Job = {
  id: string;
  filename: string;
  size_bytes: number;
  status: JobStatus;
  stage: string;
  model?: string;
  created_at?: string;
  started_at?: string;
  completed_at?: string;
  duration_seconds?: number;
  segment_count?: number;
  transcript?: string;
  error?: string;
  downloads?: JobDownloads;
};

export type ApiErrorBody = {
  detail?: string | { msg?: string }[];
};

const VIDEO_EXTENSIONS = [
  ".webm",
  ".mp4",
  ".m4v",
  ".mkv",
  ".avi",
  ".mov",
  ".wmv",
  ".flv",
  ".mpeg",
  ".mpg",
  ".ogv",
  ".3gp",
  ".ts",
] as const;

const AUDIO_EXTENSIONS = [
  ".mp3",
  ".wav",
  ".m4a",
  ".aac",
  ".flac",
  ".ogg",
  ".opus",
  ".wma",
] as const;

export const ACCEPTED_EXTENSIONS = [
  ...VIDEO_EXTENSIONS,
  ...AUDIO_EXTENSIONS,
] as const;

export const ACCEPT_ATTR = [
  "video/*",
  "audio/*",
  ...ACCEPTED_EXTENSIONS,
].join(",");

export function extensionOf(filename: string): string {
  const idx = filename.lastIndexOf(".");
  return idx >= 0 ? filename.slice(idx).toLowerCase() : "";
}

export function isAcceptedFile(file: File): boolean {
  const ext = extensionOf(file.name);
  return (ACCEPTED_EXTENSIONS as readonly string[]).includes(ext);
}

export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return "—";
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB"] as const;
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value >= 10 || unit === 0 ? 0 : 1)} ${units[unit]}`;
}

function formatDetail(body: unknown): string {
  if (!body || typeof body !== "object") return "Request failed.";
  const detail = (body as ApiErrorBody).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => (typeof item === "object" && item?.msg ? item.msg : String(item)))
      .filter(Boolean)
      .join(" ");
  }
  return "Request failed.";
}

export async function createJob(file: File): Promise<Job> {
  const form = new FormData();
  form.append("file", file);

  const response = await fetch("/api/jobs", {
    method: "POST",
    body: form,
  });

  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }

  if (!response.ok) {
    throw new Error(formatDetail(body) || `Upload failed (${response.status}).`);
  }

  return body as Job;
}

export async function getJob(jobId: string): Promise<Job> {
  const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}`);
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }

  if (!response.ok) {
    throw new Error(formatDetail(body) || `Could not load job (${response.status}).`);
  }

  return body as Job;
}
