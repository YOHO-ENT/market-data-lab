#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
UI_ROOT="${ROOT}/ui"

HOST="${MARKET_DATA_UI_HOST:-127.0.0.1}"
PORT="${MARKET_DATA_UI_PORT:-3020}"
export MARKET_DATA_API_URL="${MARKET_DATA_API_URL:-http://127.0.0.1:8010}"

cd "$UI_ROOT"

if [[ ! -d node_modules ]]; then
  echo "== installing UI dependencies locally =="
  if [[ -f package-lock.json ]]; then
    npm ci
  else
    npm install
  fi
fi

echo "== starting Market Data Lab UI at http://${HOST}:${PORT} =="
echo "== API proxy target: ${MARKET_DATA_API_URL} =="
exec npm run dev -- --host "$HOST" --port "$PORT" "$@"
