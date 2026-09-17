"""Load project .env values and normalize local service URLs."""

from __future__ import annotations

import os
from pathlib import Path


def load_env_file(path: Path = Path(".env")) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def normalize_service_url(url: str, *, default: str) -> str:
    """Turn host:port or bind addresses into a client-ready base URL."""
    resolved = (url or "").strip() or default
    if not resolved.startswith(("http://", "https://")):
        resolved = f"http://{resolved}"
    # 0.0.0.0 is valid for servers to bind to, not for clients to connect to.
    resolved = resolved.replace("://0.0.0.0", "://127.0.0.1")
    return resolved.rstrip("/")
