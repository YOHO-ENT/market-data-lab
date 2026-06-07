#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TICKER="${1:-BSX}"
API_BASE="${MARKET_DATA_API_BASE:-http://127.0.0.1:8010}"

cd "$ROOT"

echo "== pytest =="
uv run pytest -q

echo "== status =="
uv run market-data status

echo "== snapshot: ${TICKER} =="
uv run market-data snapshot "$TICKER" > /tmp/market-data-lab-snapshot.json
uv run python - <<'PY'
import json
from pathlib import Path

snapshot = json.loads(Path("/tmp/market-data-lab-snapshot.json").read_text())
json.dumps(snapshot, allow_nan=False)
assert snapshot["data_quality"]["status"] != "unavailable", snapshot["data_quality"]
print(f"{snapshot['ticker']} snapshot ok: price={snapshot['price']} trend={snapshot['trend']}")
PY

echo "== chart: ${TICKER} =="
uv run market-data chart "$TICKER" --range 1y > /tmp/market-data-lab-chart.json
uv run python - <<'PY'
import json
from pathlib import Path

chart = json.loads(Path("/tmp/market-data-lab-chart.json").read_text())
json.dumps(chart, allow_nan=False)
assert chart["has_image"] is True, chart["data_quality"]
assert chart["points"], chart["data_quality"]
print(f"{chart['ticker']} chart ok: points={len(chart['points'])}")
PY

if curl -fsS "${API_BASE}/health" >/tmp/market-data-lab-health.json 2>/dev/null; then
  echo "== api smoke: ${API_BASE} =="
  curl -fsS "${API_BASE}/status" >/tmp/market-data-lab-api-status.json
  curl -fsS "${API_BASE}/snapshot/${TICKER}" >/tmp/market-data-lab-api-snapshot.json
  curl -fsS "${API_BASE}/chart/${TICKER}?range=1y" >/tmp/market-data-lab-api-chart.json
  uv run python - <<'PY'
import json
from pathlib import Path

for name in ("health", "api-status", "api-snapshot", "api-chart"):
    data = json.loads(Path(f"/tmp/market-data-lab-{name}.json").read_text())
    json.dumps(data, allow_nan=False)
print("api smoke ok")
PY
else
  echo "API server not running at ${API_BASE}; skipped HTTP smoke."
fi
