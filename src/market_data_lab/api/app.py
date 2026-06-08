"""FastAPI app for Market Data Lab."""

from __future__ import annotations

from datetime import date

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from market_data_lab.models import (
    HealthResponse,
    RefreshRequest,
    SnapshotRefreshRequest,
    normalize_ticker,
)
from market_data_lab.services import (
    add_universe_tickers,
    get_chart,
    get_history,
    get_quality,
    get_refresh_run,
    get_screen,
    get_snapshot,
    get_snapshots,
    get_universes,
    list_refresh_runs,
    preview_moomoo_research_universe,
    refresh_history,
    refresh_snapshots,
    remove_universe_ticker,
    remove_universe_group,
    replace_universe_group,
    status_summary,
    sync_moomoo_research_universe,
)

app = FastAPI(title="Market Data Lab", version="0.1.0")


class UniverseTickersRequest(BaseModel):
    tickers: list[str] = Field(default_factory=list)


class MoomooSyncRequest(BaseModel):
    sync_firn: bool = True
    base_url: str | None = None
    host: str | None = None
    port: int | None = None
    market: str | None = None
    group_type: str | None = None
    timeout: float = 10.0


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse()


@app.get("/status")
async def status() -> dict:
    return status_summary()


@app.get("/quality")
async def quality() -> dict:
    return get_quality()


@app.get("/screen")
async def screen(
    tickers: str | None = Query(None),
    group: str | None = Query(None),
    benchmark: str = Query("SPY", min_length=1),
    trend: str | None = Query(None),
    breakout_status: str | None = Query(None),
    data_quality: str | None = Query(None),
    rsi_min: float | None = Query(None),
    rsi_max: float | None = Query(None),
    trend_score_min: float | None = Query(None),
    liquidity_score_min: float | None = Query(None),
    relative_strength: str | None = Query(None),
    ma_distance_max: float | None = Query(None, ge=0),
    ma: str = Query("any"),
    week52_position_min: float | None = Query(None),
    week52_position_max: float | None = Query(None),
    volume_ratio_min: float | None = Query(None),
    limit: int = Query(100, ge=1),
):
    try:
        requested = _split_csv(tickers)
        return get_screen(
            tickers=requested,
            group=group,
            benchmark=benchmark,
            trend=trend,
            breakout_status=breakout_status,
            data_quality=data_quality,
            rsi_min=rsi_min,
            rsi_max=rsi_max,
            trend_score_min=trend_score_min,
            liquidity_score_min=liquidity_score_min,
            relative_strength=relative_strength,
            ma_distance_max=ma_distance_max,
            ma=ma,
            week52_position_min=week52_position_min,
            week52_position_max=week52_position_max,
            volume_ratio_min=volume_ratio_min,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/refresh")
async def refresh(body: RefreshRequest):
    return refresh_history(body.tickers, period=body.period, force=body.force)


@app.get("/universes")
async def universes() -> dict:
    try:
        return get_universes()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/integrations/moomoo/research-universe/preview")
async def moomoo_research_universe_preview(
    base_url: str | None = Query(None),
    host: str | None = Query(None),
    port: int | None = Query(None),
    market: str | None = Query(None),
    group_type: str | None = Query(None),
    timeout: float = Query(10.0, gt=0),
) -> dict:
    try:
        return preview_moomoo_research_universe(
            base_url=base_url,
            host=host,
            port=port,
            market=market,
            group_type=group_type,
            timeout=timeout,
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/integrations/moomoo/research-universe/sync")
async def moomoo_research_universe_sync(body: MoomooSyncRequest | None = None) -> dict:
    body = body or MoomooSyncRequest()
    try:
        return sync_moomoo_research_universe(
            sync_firn=body.sync_firn,
            base_url=body.base_url,
            host=body.host,
            port=body.port,
            market=body.market,
            group_type=body.group_type,
            timeout=body.timeout,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.put("/universes/{group}")
async def put_universe_group(group: str, body: UniverseTickersRequest):
    try:
        return replace_universe_group(group, body.tickers)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/universes/{group}/tickers")
async def post_universe_tickers(group: str, body: UniverseTickersRequest):
    try:
        return add_universe_tickers(group, body.tickers)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/universes/{group}")
async def delete_universe_group(group: str):
    try:
        return remove_universe_group(group)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/universes/{group}/tickers/{ticker}")
async def delete_universe_ticker(group: str, ticker: str):
    try:
        return remove_universe_ticker(group, ticker)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/runs/refresh")
async def refresh_runs(limit: int = Query(50, ge=1, le=500)):
    try:
        return list_refresh_runs(limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/runs/refresh/{run_id}")
async def refresh_run(run_id: str):
    try:
        return get_refresh_run(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/history/{ticker}")
async def history(
    ticker: str,
    start: date | None = None,
    end: date | None = None,
):
    try:
        return get_history(ticker, start=start, end=end)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/snapshots")
async def snapshots(
    tickers: str = Query(..., min_length=1),
    limit: int = Query(100, ge=1),
    benchmark: str = Query("SPY", min_length=1),
):
    try:
        requested = [ticker.strip() for ticker in tickers.split(",") if ticker.strip()]
        if not requested:
            raise ValueError("Provide at least one ticker")
        return get_snapshots(requested, limit=limit, benchmark=benchmark)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/snapshot/{ticker}")
async def snapshot(
    ticker: str,
    benchmark: str = Query("SPY", min_length=1),
):
    try:
        return get_snapshot(ticker, benchmark=benchmark)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        normalized = normalize_ticker(ticker)
        return {
            "ticker": normalized,
            "as_of": None,
            "currency": "unavailable",
            "price": None,
            "ma20": None,
            "ma50": None,
            "ma200": None,
            "distance_from_ma20": None,
            "distance_from_ma50": None,
            "distance_from_ma200": None,
            "rsi14": None,
            "atr14": None,
            "return_1m": None,
            "return_3m": None,
            "return_6m": None,
            "return_ytd": None,
            "volatility_20d": None,
            "volatility_60d": None,
            "beta_vs_spy": None,
            "max_drawdown_6m": None,
            "max_drawdown_1y": None,
            "week52_high": None,
            "week52_low": None,
            "week52_position": None,
            "distance_from_52w_high": None,
            "distance_from_52w_low": None,
            "latest_gap_pct": None,
            "liquidity_score": None,
            "trend_score": None,
            "trend": "unavailable",
            "breakout_status": "unavailable",
            "support_levels": [],
            "resistance_levels": [],
            "relative_strength_vs_spy": {"benchmark": "SPY", "status": "unavailable", "periods": {}},
            "volume_signal": {"status": "unavailable"},
            "data_quality": {
                "status": "unavailable",
                "warnings": [str(exc)],
            },
        }


@app.get("/chart/{ticker}")
async def chart(
    ticker: str,
    range: str = Query("1y", pattern="^(6mo|1y|2y|5y)$"),  # noqa: A002
):
    try:
        return get_chart(ticker, range_name=range)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        normalized = normalize_ticker(ticker)
        return {
            "ticker": normalized,
            "has_image": False,
            "points": [],
            "data_quality": {
                "status": "unavailable",
                "warnings": [str(exc)],
            },
        }


@app.post("/snapshots/refresh")
async def snapshots_refresh(body: SnapshotRefreshRequest):
    return refresh_snapshots(body.tickers, benchmark=body.benchmark)


def _split_csv(value: str | None) -> list[str] | None:
    if value is None:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]
