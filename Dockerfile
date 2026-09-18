FROM node:22-alpine AS frontend-builder

WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build


FROM ghcr.io/astral-sh/uv:0.8.22 AS uv


FROM python:3.13-slim AS python-builder

COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project


FROM python:3.13-slim AS runtime

ENV APP_DATA_DIR=/app/data \
    HF_HOME=/app/data/huggingface \
    PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    WHISPER_MODEL=tiny.en

RUN apt-get update \
    && apt-get install --no-install-recommends -y ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=python-builder /app/.venv /app/.venv
COPY . .
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist

RUN useradd --create-home --uid 10001 app \
    && mkdir -p /app/data/huggingface /app/data/jobs \
    && chown -R app:app /app

USER app
EXPOSE 8000

CMD ["uvicorn", "web_app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
