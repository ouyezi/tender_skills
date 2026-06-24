#!/usr/bin/env bash
# Poll interpret job progress until done/failed. For agents and shell scripts.
#
# Usage:
#   ./scripts/poll-interpret-job.sh <job_id>
#   ./scripts/poll-interpret-job.sh --session <session_id>
#
# Environment:
#   VIEWER_URL  default http://127.0.0.1:8765
#   POLL_INTERVAL_SEC  default 1

set -euo pipefail

VIEWER_URL="${VIEWER_URL:-http://127.0.0.1:8765}"
INTERVAL="${POLL_INTERVAL_SEC:-1}"

if [[ "${1:-}" == "--session" ]]; then
  SESSION_ID="${2:?session id required}"
  JOB_JSON=$(curl -fsS "${VIEWER_URL}/api/interpret/sessions/${SESSION_ID}/job")
  JOB_ID=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["job_id"])' <<<"$JOB_JSON")
else
  JOB_ID="${1:?job id required (or use --session <id>)}"
fi

echo "Watching interpret job: ${JOB_ID}" >&2

while true; do
  RESP=$(curl -fsS "${VIEWER_URL}/api/interpret/jobs/${JOB_ID}")
  echo "$RESP"
  STATUS=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])' <<<"$RESP")
  if [[ "$STATUS" == "done" || "$STATUS" == "failed" ]]; then
    exit "$( [[ "$STATUS" == "done" ]] && echo 0 || echo 1 )"
  fi
  sleep "$INTERVAL"
done
