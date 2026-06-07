# Market Data Lab

Standalone local market data cache, technical snapshot, screen, and chart data service.

## Scope

- yfinance daily OHLCV ingestion
- Parquet history cache
- deterministic technical snapshots
- ECharts-ready chart data
- universe-driven daily screen workflow
- refresh run visibility
- FastAPI + compact CLI

Hard boundaries:

- no Firn adapter, Firn integration, or Firn write-back
- no KB reads or writes
- no LLM workflows
- no backtest or backtesting engine
- no trading, execution, broker, or portfolio operations
- no news, digest, or Telegram pipeline

## Daily Flow

From this directory:

```bash
./scripts/refresh_daily.sh
./scripts/dev.sh
```

The daily workflow is:

1. Review configured universes with `/universes` or the status `groups` payload.
2. Refresh the local daily OHLCV cache.
3. Review the latest refresh metadata with `/runs` or `market-data runs`.
4. Use `/screen` and the UI for the current local technical screen.

Open the UI at:

```text
http://127.0.0.1:3020
```

`refresh_daily.sh` runs the full daily data workflow:

```bash
uv run market-data refresh --all --period 5y
uv run market-data runs --limit 1
uv run market-data status --verbose
uv run market-data quality
```

`dev.sh` starts both local services and cleans them up when it exits:

- API: `http://127.0.0.1:8010`
- UI: `http://127.0.0.1:3020`

## Start Services Separately

API only:

```bash
./scripts/start_api.sh
```

UI only:

```bash
./scripts/start_ui.sh
```

The UI is a Vite app. During development, Vite proxies `/api/*` to the backend.
Override ports or the backend URL when needed:

```bash
MARKET_DATA_API_PORT=8011 ./scripts/start_api.sh
MARKET_DATA_UI_PORT=3021 MARKET_DATA_API_URL=http://127.0.0.1:8011 ./scripts/start_ui.sh
```

The scripts use project-local Python and Node tooling: `uv run` for Python
commands and `npm run dev` for Vite. `start_ui.sh` installs UI dependencies
locally with `npm ci` when `ui/node_modules` is missing.

## Verify

```bash
uv run pytest -q
bash scripts/smoke.sh BSX
uv run market-data runs --limit 5
curl -sS http://127.0.0.1:8010/health
curl -sS http://127.0.0.1:8010/status
curl -sS http://127.0.0.1:8010/universes
curl -sS 'http://127.0.0.1:8010/runs/refresh?limit=5'
curl -sS http://127.0.0.1:8010/screen
curl -sS http://127.0.0.1:8010/snapshot/BSX
curl -sS 'http://127.0.0.1:8010/chart/BSX?range=1y'
```

## CLI Examples

```bash
uv run market-data status
uv run market-data status --verbose
uv run market-data quality
uv run market-data runs --limit 5
uv run market-data refresh AAPL BSX --period 5y
uv run market-data refresh --all --period 5y
uv run market-data snapshot BSX
uv run market-data chart BSX --range 1y
```

## API Examples

```text
GET  /health
GET  /universes
GET  /runs/refresh?limit=5
GET  /screen
POST /refresh
GET  /history/{ticker}
GET  /snapshot/{ticker}
GET  /chart/{ticker}?range=6mo|1y|2y|5y
POST /snapshots/refresh
```
