#!/usr/bin/env bash
#
# start_mac.sh — build (if needed) and run the FinAlly container (macOS/Linux).
#
# Idempotent: safe to run repeatedly. Builds the image if it is missing or when
# --build is passed, then (re)starts a single container with the db/ bind mount,
# port 8000 mapping, and the project .env file.
#
# Usage:
#   scripts/start_mac.sh [--build] [--no-open]
#     --build     Force a fresh image build even if one already exists.
#     --no-open   Do not open the browser after the container is healthy.

set -euo pipefail

IMAGE="finally:latest"
CONTAINER="finally"
PORT="8000"
URL="http://localhost:${PORT}"

# Resolve the project root (this script lives in scripts/).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT_DIR}"

FORCE_BUILD=0
OPEN_BROWSER=1
for arg in "$@"; do
  case "${arg}" in
    --build)    FORCE_BUILD=1 ;;
    --no-open)  OPEN_BROWSER=0 ;;
    *) echo "Unknown option: ${arg}" >&2; exit 2 ;;
  esac
done

if ! command -v docker >/dev/null 2>&1; then
  echo "Error: docker is not installed or not on PATH." >&2
  exit 1
fi

# .env is required for the API keys; fall back to a clear message if absent.
if [ ! -f .env ]; then
  echo "Warning: no .env file found. Copy .env.example to .env and add your keys." >&2
  echo "         The simulator + LLM mock work without keys, but chat needs OPENROUTER_API_KEY." >&2
fi

# Ensure the host bind-mount dir exists so the SQLite file lands in the repo.
mkdir -p "${ROOT_DIR}/db"

# Build the image if forced, or if it does not already exist.
if [ "${FORCE_BUILD}" -eq 1 ] || ! docker image inspect "${IMAGE}" >/dev/null 2>&1; then
  echo "Building image ${IMAGE}..."
  docker build -t "${IMAGE}" "${ROOT_DIR}"
else
  echo "Image ${IMAGE} already present (use --build to rebuild)."
fi

# Remove any existing container with this name so the run is repeatable.
if docker ps -a --format '{{.Names}}' | grep -qx "${CONTAINER}"; then
  echo "Removing existing container ${CONTAINER}..."
  docker rm -f "${CONTAINER}" >/dev/null
fi

ENV_ARGS=()
if [ -f .env ]; then
  ENV_ARGS+=(--env-file .env)
fi

echo "Starting container ${CONTAINER}..."
docker run -d \
  --name "${CONTAINER}" \
  -p "${PORT}:8000" \
  -v "${ROOT_DIR}/db:/app/db" \
  "${ENV_ARGS[@]}" \
  "${IMAGE}" >/dev/null

# Wait for the health endpoint before declaring success / opening the browser.
echo -n "Waiting for ${URL}/api/health "
for _ in $(seq 1 30); do
  if curl -fsS "${URL}/api/health" >/dev/null 2>&1; then
    echo " ready."
    echo "FinAlly is running at ${URL}"
    if [ "${OPEN_BROWSER}" -eq 1 ] && command -v open >/dev/null 2>&1; then
      open "${URL}"
    fi
    exit 0
  fi
  echo -n "."
  sleep 1
done

echo ""
echo "Container started but health check did not pass in time." >&2
echo "Check logs with: docker logs ${CONTAINER}" >&2
exit 1
