#!/usr/bin/env bash
set -Eeuo pipefail

export MRH_HOST="${MRH_HOST:-0.0.0.0}"
export MRH_PORT="${PORT:-${MRH_PORT:-10000}}"

# Keep API and pull worker in one instance so both use the same persistent SQLite file.
python -m mrhub.worker_service &
WORKER_PID=$!

python -m uvicorn mrhub.main:app --host "$MRH_HOST" --port "$MRH_PORT" &
API_PID=$!

shutdown() {
  trap - TERM INT EXIT
  kill -TERM "$API_PID" "$WORKER_PID" 2>/dev/null || true
  wait "$API_PID" 2>/dev/null || true
  wait "$WORKER_PID" 2>/dev/null || true
}

trap shutdown TERM INT EXIT

# If either process exits unexpectedly, stop the other instead of leaving a partial service.
set +e
wait -n "$API_PID" "$WORKER_PID"
STATUS=$?
set -e
exit "$STATUS"
