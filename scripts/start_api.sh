#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

HOST="${MARKET_DATA_API_HOST:-127.0.0.1}"
PORT="${MARKET_DATA_API_PORT:-8010}"

cd "$ROOT"

echo "== starting Market Data Lab API at http://${HOST}:${PORT} =="
exec uv run uvicorn market_data_lab.api.app:app --host "$HOST" --port "$PORT" "$@"
