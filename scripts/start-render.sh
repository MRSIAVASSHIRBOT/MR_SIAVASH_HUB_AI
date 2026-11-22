#!/usr/bin/env bash
set -Eeuo pipefail

export MRH_HOST="${MRH_HOST:-0.0.0.0}"
export MRH_PORT="${PORT:-${MRH_PORT:-10000}}"

# The API and Hub worker share one persistent SQLite volume. EL_AI consumes the
# signed Cloudflare Telegram queue in this same instance and uses the same Hub API.
python -m mrhub.worker_service &
WORKER_PID=$!

python -m uvicorn mrhub.main:app --host "$MRH_HOST" --port "$MRH_PORT" &
API_PID=$!

python -m el_ai &
EL_AI_PID=$!

shutdown() {
  trap - TERM INT EXIT
  kill -TERM "$API_PID" "$WORKER_PID" "$EL_AI_PID" 2>/dev/null || true
  wait "$API_PID" 2>/dev/null || true
  wait "$WORKER_PID" 2>/dev/null || true
  wait "$EL_AI_PID" 2>/dev/null || true
}

trap shutdown TERM INT EXIT

# Any process exit is a service failure; do not leave a partial runtime online.
set +e
wait -n "$API_PID" "$WORKER_PID" "$EL_AI_PID"
STATUS=$?
set -e
if [[ "$STATUS" -eq 0 ]]; then
  echo "A supervised runtime process exited unexpectedly" >&2
  STATUS=1
fi
exit "$STATUS"
