#!/usr/bin/env bash
#
# stop_mac.sh — stop and remove the FinAlly container (macOS/Linux).
#
# Idempotent: safe to run when nothing is running. Does NOT delete the SQLite
# database — db/finally.db persists on the host (PLAN §11). To start fresh,
# run: rm db/finally.db
#
# Usage: scripts/stop_mac.sh

set -euo pipefail

CONTAINER="finally"

if ! command -v docker >/dev/null 2>&1; then
  echo "Error: docker is not installed or not on PATH." >&2
  exit 1
fi

if docker ps -a --format '{{.Names}}' | grep -qx "${CONTAINER}"; then
  echo "Stopping and removing container ${CONTAINER}..."
  docker rm -f "${CONTAINER}" >/dev/null
  echo "Stopped. Database preserved at db/finally.db (delete it to start fresh)."
else
  echo "No container named ${CONTAINER} is running. Nothing to do."
fi
