#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

cd "$ROOT"

echo "== sync universe from moomoo account web =="
uv run market-data moomoo-sync

echo "== refresh all universes: 5y =="
uv run market-data refresh --all --period 5y

echo "== latest refresh run =="
uv run market-data runs --limit 1

echo "== cache status: verbose =="
uv run market-data status --verbose

echo "== data quality =="
uv run market-data quality
