#!/usr/bin/env bash
set -Eeuo pipefail

export MRH_HOST="${MRH_HOST:-0.0.0.0}"
export MRH_PORT="${PORT:-${MRH_PORT:-10000}}"

# Keep API and pull worker in one instance so both use the same persistent SQLite file.
python -m mrhub.worker_service &
WORKER_PID=$!

cleanup() {
  kill -TERM "$WORKER_PID" 2>/dev/null || true
  wait "$WORKER_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

python -m uvicorn mrhub.main:app --host "$MRH_HOST" --port "$MRH_PORT"
