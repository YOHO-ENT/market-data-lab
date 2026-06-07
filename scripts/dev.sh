#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

API_HOST="${MARKET_DATA_API_HOST:-127.0.0.1}"
API_PORT="${MARKET_DATA_API_PORT:-8010}"
UI_HOST="${MARKET_DATA_UI_HOST:-127.0.0.1}"
UI_PORT="${MARKET_DATA_UI_PORT:-3020}"
export MARKET_DATA_API_URL="${MARKET_DATA_API_URL:-http://${API_HOST}:${API_PORT}}"

pids=()

terminate_tree() {
  local pid="$1"
  local child

  if command -v pgrep >/dev/null 2>&1; then
    for child in $(pgrep -P "$pid" 2>/dev/null || true); do
      terminate_tree "$child"
    done
  fi

  kill "$pid" 2>/dev/null || true
}

cleanup() {
  local status=$?
  local pid
  trap - EXIT INT TERM

  if ((${#pids[@]} > 0)); then
    echo
    echo "== stopping Market Data Lab dev processes =="
    for pid in "${pids[@]}"; do
      terminate_tree "$pid"
    done
    wait "${pids[@]}" 2>/dev/null || true
  fi

  exit "$status"
}

is_running_job() {
  local wanted="$1"
  local pid

  for pid in $(jobs -pr); do
    if [[ "$pid" == "$wanted" ]]; then
      return 0
    fi
  done

  return 1
}

trap cleanup EXIT INT TERM

echo "== starting API: http://${API_HOST}:${API_PORT} =="
MARKET_DATA_API_HOST="$API_HOST" MARKET_DATA_API_PORT="$API_PORT" "${SCRIPT_DIR}/start_api.sh" &
pids+=("$!")

echo "== starting UI: http://${UI_HOST}:${UI_PORT} =="
MARKET_DATA_UI_HOST="$UI_HOST" MARKET_DATA_UI_PORT="$UI_PORT" MARKET_DATA_API_URL="$MARKET_DATA_API_URL" "${SCRIPT_DIR}/start_ui.sh" &
pids+=("$!")

echo "== Market Data Lab dev =="
echo "API: http://${API_HOST}:${API_PORT}"
echo "UI:  http://${UI_HOST}:${UI_PORT}"
echo "Press Ctrl-C to stop both."

while :; do
  for pid in "${pids[@]}"; do
    if ! is_running_job "$pid"; then
      set +e
      wait "$pid"
      status=$?
      set -e
      exit "$status"
    fi
  done

  sleep 1
done
