# Deployment Guide

## Prerequisites

- Python >= 3.12
- `uv` package manager
- OpenAI-compatible API key
- Sufficient disk for Chroma persistence and embedding model cache

## Environment Variables

Copy `backend/.env.example` to `backend/.env` and fill in at least:

```env
OPENAI_API_KEY=sk-...
OPENAI_API_BASE=https://api.openai.com/v1  # optional
OPENAI_MODEL=sensenova-6.7-flash-lite       # optional
CUITCCA_API_KEY=change-me                   # required for manage endpoints
```

See `.env.example` for the full list (CORS, paths, retrieval tuning, rerank settings).

## Build Frontend

```bash
make frontend-install
make frontend-build
```

This produces production assets in `backend/app/static/`.

## Run with systemd

Create `/etc/systemd/system/cuitcca.service`:

```ini
[Unit]
Description=CUITCCA Campus AI Assistant
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/cuitcca
Environment="PATH=/opt/cuitcca/.venv/bin"
ExecStart=/opt/cuitcca/.venv/bin/uvicorn backend.app.main:app --host 0.0.0.0 --port 8522
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now cuitcca
```

## Run with Docker (optional)

```dockerfile
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends gcc libgomp1 && rm -rf /var/lib/apt/lists/*
COPY . /app
RUN pip install uv && uv sync --frozen
EXPOSE 8522
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8522"]
```

## Nginx Reverse Proxy

```nginx
server {
    listen 80;
    server_name cuitcca.example.com;

    client_max_body_size 50M;

    location / {
        proxy_pass http://127.0.0.1:8522;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## Chroma Persistence

Chroma data lives at `CHROMA_DB_PATH` (default: `data/chroma_db`). Back up this directory to preserve indexes. The incremental ingestion pipeline avoids duplicate chunks, but a full re-ingest is possible if corruption occurs.

## Production Hardening

- Set `CORS_ORIGINS` to your real origins (comma-separated).
- Set `COOKIE_SECURE=true` if serving over HTTPS.
- Set a strong `CUITCCA_API_KEY` and keep it secret.
- Tune `RERANK_RECALL_K` / `RERANK_TOP_N` based on latency/quality trade-offs.
- Monitor logs in `log/` and increase verbosity via Python logging config if needed.
