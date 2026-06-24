#!/usr/bin/env bash
# Stop any running doc-chunk viewer, then start a fresh instance.
#
# Usage:
#   ./scripts/restart-viewer.sh              # foreground (logs in this terminal)
#   ./scripts/restart-viewer.sh -b         # background
#   ./scripts/restart-viewer.sh --log-prompts
#
# Configuration:
#   Always loads ${REPO_ROOT}/.env before start (values in .env override the
#   current shell for LLM_/OCR_/SEGMENT_/INTERPRET_* keys).
#
# Environment (optional overrides after .env):
#   VIEWER_HOST   default 127.0.0.1
#   VIEWER_PORT   default 8765
#   INTERPRET_LOG_PROMPTS  set to 1 with --log-prompts

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PY="${ROOT}/.venv/bin/python"
ENV_FILE="${ROOT}/.env"
VIEWER_HOST="${VIEWER_HOST:-127.0.0.1}"
VIEWER_PORT="${VIEWER_PORT:-8765}"
BACKGROUND=0
LOG_PROMPTS=0

_PROJECT_ENV_OVERRIDE_PREFIXES=(LLM_ OCR_ SEGMENT_ INTERPRET_)

usage() {
  sed -n '2,16p' "$0"
  exit "${1:-0}"
}

should_override_from_env() {
  local key="$1"
  if [[ "$key" == "LLM_API_KEY" ]]; then
    return 1
  fi
  local prefix
  for prefix in "${_PROJECT_ENV_OVERRIDE_PREFIXES[@]}"; do
    if [[ "$key" == "${prefix}"* ]]; then
      return 0
    fi
  done
  return 1
}

# Parse KEY=VALUE lines from the repo .env (same rules as viewer.config.load_project_env).
load_project_env() {
  if [[ ! -f "$ENV_FILE" ]]; then
    echo "No .env at ${ENV_FILE}" >&2
    return 0
  fi

  local line key value stripped
  while IFS= read -r line || [[ -n "$line" ]]; do
    stripped="${line#"${line%%[![:space:]]*}"}"
    [[ -z "$stripped" || "$stripped" == \#* ]] && continue
    if [[ "$stripped" == export\ * ]]; then
      stripped="${stripped#export }"
      stripped="${stripped#"${stripped%%[![:space:]]*}"}"
    fi
    [[ "$stripped" != *"="* ]] && continue

    key="${stripped%%=*}"
    value="${stripped#*=}"
    key="${key%"${key##*[![:space:]]}"}"
    value="${value#"${value%%[![:space:]]*}"}"

    if [[ ${#value} -ge 2 ]]; then
      local first="${value:0:1}"
      local last="${value: -1}"
      if [[ "$first" == "$last" && ( "$first" == "'" || "$first" == '"' ) ]]; then
        value="${value:1:${#value}-2}"
      fi
    fi

    if should_override_from_env "$key"; then
      export "$key=$value"
    elif [[ -z "${!key+x}" ]]; then
      export "$key=$value"
    fi
  done <"$ENV_FILE"

  echo "Loaded ${ENV_FILE}" >&2
  if [[ -n "${LLM_MODEL:-}" ]]; then
    echo "LLM_MODEL=${LLM_MODEL}" >&2
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -b|--background)
      BACKGROUND=1
      shift
      ;;
    --log-prompts)
      LOG_PROMPTS=1
      shift
      ;;
    -h|--help)
      usage 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage 1
      ;;
  esac
done

if [[ ! -x "$VENV_PY" ]]; then
  echo "Missing virtualenv: ${VENV_PY}" >&2
  echo "Create it first, e.g. python -m venv .venv && .venv/bin/pip install -e ." >&2
  exit 1
fi

stop_viewer() {
  local pid
  local killed=0

  if command -v lsof >/dev/null 2>&1; then
    while IFS= read -r pid; do
      [[ -z "$pid" ]] && continue
      echo "Stopping viewer (pid ${pid}, port ${VIEWER_PORT})..." >&2
      kill "$pid" 2>/dev/null || true
      killed=1
    done < <(lsof -tiTCP:"${VIEWER_PORT}" -sTCP:LISTEN 2>/dev/null || true)
  fi

  if [[ "$killed" -eq 1 ]]; then
    for _ in 1 2 3 4 5; do
      if ! lsof -tiTCP:"${VIEWER_PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
        break
      fi
      sleep 0.2
    done
    if lsof -tiTCP:"${VIEWER_PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
      while IFS= read -r pid; do
        [[ -z "$pid" ]] && continue
        echo "Force stopping pid ${pid}..." >&2
        kill -9 "$pid" 2>/dev/null || true
      done < <(lsof -tiTCP:"${VIEWER_PORT}" -sTCP:LISTEN 2>/dev/null || true)
    fi
  else
    echo "No listener on ${VIEWER_HOST}:${VIEWER_PORT}" >&2
  fi
}

start_viewer() {
  cd "$ROOT"
  load_project_env

  if [[ "$LOG_PROMPTS" -eq 1 ]]; then
    export INTERPRET_LOG_PROMPTS=1
  fi

  local url="http://${VIEWER_HOST}:${VIEWER_PORT}/interpret"
  echo "Starting viewer at ${url}" >&2

  if [[ "$BACKGROUND" -eq 1 ]]; then
    local log_file="${ROOT}/.viewer.log"
    nohup "$VENV_PY" -m viewer >"$log_file" 2>&1 &
    local pid=$!
    echo "Viewer running in background (pid ${pid})" >&2
    echo "Logs: ${log_file}" >&2
    echo "Open: ${url}" >&2
  else
    echo "Press Ctrl+C to stop." >&2
    exec "$VENV_PY" -m viewer
  fi
}

stop_viewer
start_viewer
