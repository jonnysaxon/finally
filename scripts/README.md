# FinAlly — Build, Run & Verification

Helper scripts and the canonical Docker commands for running FinAlly. The app
is a single container serving the FastAPI backend and the Next.js static export
on **port 8000** (PLAN §3/§11).

## Scripts

| Script | Platform | Does |
|--------|----------|------|
| `start_mac.sh`     | macOS/Linux | Build (if missing or `--build`), run container, wait for health, open browser (`--no-open` to skip) |
| `stop_mac.sh`      | macOS/Linux | Stop + remove the container. **Never deletes `db/finally.db`.** |
| `start_windows.ps1`| Windows     | Same as `start_mac.sh` (`-Build`, `-NoOpen`) |
| `stop_windows.ps1` | Windows     | Same as `stop_mac.sh` |

All scripts are idempotent — safe to run repeatedly. Run them from anywhere;
they resolve the repo root themselves.

```bash
# macOS/Linux
scripts/start_mac.sh            # build-if-needed, run, open browser
scripts/start_mac.sh --build    # force a fresh image build
scripts/stop_mac.sh             # stop (DB persists at db/finally.db)
```

```powershell
# Windows
.\scripts\start_windows.ps1 -Build
.\scripts\stop_windows.ps1
```

To start with a clean database: stop the container, then `rm db/finally.db`
(`Remove-Item db/finally.db` on Windows). The backend re-creates and re-seeds it
on the next request.

---

## VERIFICATION — run these on a Docker-capable host

> These commands require Docker (or Podman with a `docker` shim). They could
> not be executed in the build sandbox, which has no container runtime and a
> proxy that blocks binary downloads — verification is therefore deferred to a
> Docker-enabled machine. Each command below is the exact, copy-pasteable form.

### 1. Build the image

```bash
docker build -t finally:latest .
```

The build is multi-stage:
- **Stage 1** (`node:20-slim`): `npm ci` then `npm run build` in `frontend/`,
  producing the static export at `frontend/out/` (Next.js `output: "export"`).
- **Stage 2** (`python:3.12-slim`): `uv sync --frozen --no-dev` from
  `backend/uv.lock`, copies `frontend/out/` → `backend/app/static/` (where
  `app/static_files.py` serves it), and runs
  `uvicorn app.main:app --host 0.0.0.0 --port 8000`.

### 2. Run the container

```bash
docker run -d --name finally \
  -p 8000:8000 \
  -v "$(pwd)/db:/app/db" \
  --env-file .env \
  finally:latest
```

`db/finally.db` appears on the host (bind mount) and persists across restarts.
If you have no `.env`, the simulator + (with `LLM_MOCK=true`) mock chat still
work; only live AI chat needs `OPENROUTER_API_KEY`.

### 3. Health check

```bash
curl -fsS http://localhost:8000/api/health      # -> {"status":"ok"}
```

Then open http://localhost:8000 for the trading workstation UI.

### 4. End-to-end Playwright suite (PLAN §12)

Runs the app (LLM_MOCK + simulator, ephemeral DB) plus a Playwright runner:

```bash
docker compose -f test/docker-compose.test.yml up --build \
  --abort-on-container-exit --exit-code-from playwright
# tidy up:
docker compose -f test/docker-compose.test.yml down -v
```

The `playwright` service's exit code is the suite result (0 = all green). It
targets the app at `http://app:8000` via the `BASE_URL` env that
`test/playwright.config.ts` reads.

### 5. Convenience compose (single app container)

```bash
docker compose up --build    # foreground; Ctrl-C to stop
docker compose down          # DB persists in ./db
```

---

## Troubleshooting

- **`uv sync` fails behind a MITM/corporate proxy** (TLS `UnknownIssuer`,
  connection reset on PyPI). Add the system trust store by switching the
  install lines in the `Dockerfile` runtime stage to:
  ```dockerfile
  RUN --mount=type=cache,target=/root/.cache/uv \
      uv sync --frozen --no-dev --native-tls
  ```
  `--native-tls` makes uv use the OS certificate store instead of its bundled
  roots. On a normal host the plain `uv sync --frozen` (what the Dockerfile
  ships) is correct and faster.
- **`npm ci` fails** — ensure `frontend/package-lock.json` is committed and in
  sync with `package.json`. Same for `test/package-lock.json` for the E2E run.
- **Port 8000 already in use** — change the host side of the mapping, e.g.
  `-p 8080:8000`, then browse to `http://localhost:8080`.
- **SSE not streaming / events buffered** — the image runs a single uvicorn
  process and the backend sets `Cache-Control: no-cache` / `X-Accel-Buffering:
  no` (PLAN §13). Do not place a buffering reverse proxy in front of it.
