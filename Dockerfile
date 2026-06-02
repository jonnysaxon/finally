# syntax=docker/dockerfile:1
#
# FinAlly production image — single container, port 8000 (PLAN §11).
#
# VERIFICATION (run on a Docker-capable host; see scripts/README.md for detail):
#   docker build -t finally:latest .
#   docker run -d --name finally -p 8000:8000 -v "$(pwd)/db:/app/db" --env-file .env finally:latest
#   curl -fsS http://localhost:8000/api/health        # -> {"status":"ok"}
#   docker compose -f test/docker-compose.test.yml up --build \
#     --abort-on-container-exit --exit-code-from playwright   # E2E suite
# Behind a MITM/corporate proxy, add --native-tls to the `uv sync` lines below.
#
# ---------------------------------------------------------------------------
# Stage 1 — build the Next.js frontend as a static export.
# ---------------------------------------------------------------------------
FROM node:20-slim AS frontend

WORKDIR /build

# Install dependencies first so this layer caches on lockfile changes only.
COPY frontend/package.json frontend/package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

# Build the static export. Next.js `output: 'export'` emits to `out/`.
COPY frontend/ ./
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2 — Python/FastAPI runtime served by uvicorn on :8000.
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

# uv: fast, reproducible installs from the committed lockfile.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app/backend

# Install dependencies from the lockfile first (cached unless deps change).
# No project source yet -> --no-install-project, so this layer is reused
# across source edits.
COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Now the backend source, then install the project itself.
COPY backend/ ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Drop the built frontend into the dir FastAPI serves static files from
# (BUILD_CONTRACT: backend serves the export from app/static/, SPA fallback).
COPY --from=frontend /build/out/ ./app/static/

# Runtime bind-mount target for the SQLite file (db/finally.db on the host).
# database.py writes here when /app/db exists.
RUN mkdir -p /app/db

# Put the uv-managed venv on PATH so `uvicorn` resolves without `uv run`.
ENV PATH="/app/backend/.venv/bin:${PATH}"

EXPOSE 8000

# Image-level health: hit GET /api/health (-> {"status":"ok"}). Makes `docker
# ps` / `docker run` report health without relying on a compose override.
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/api/health').status==200 else 1)"

# Single uvicorn process — SSE must not sit behind a buffering proxy (PLAN §13).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
