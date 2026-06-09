"""Application services tying fetchers, storage, snapshots, and charts together."""

from __future__ import annotations

import json
import math
import re
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd
import yaml

from market_data_lab.config import (
    DEFAULT_BENCHMARK,
    DEFAULT_PERIOD,
    MARKET_DATA_UNIVERSE_EDITABLE,
    REFRESH_RUN_DIR,
    SNAPSHOT_DIR,
    STALE_PRICE_MAX_AGE_DAYS,
    UNIVERSE_PATH,
    ensure_data_dirs,
)
from market_data_lab.models import (
    HistoryResponse,
    RefreshResponse,
    RefreshTickerResult,
    SnapshotRefreshResponse,
    normalize_ticker,
    normalize_tickers,
)
from market_data_lab.moomoo_integration import preview_research_universe
from market_data_lab.watchlist_sync import (
    DEFAULT_FIRN_WATCHLIST_PATH,
    DEFAULT_UNIVERSE_PATH,
    sync_universe_to_watchlist,
)

QUALITY_TYPES = (
    "missing_price",
    "missing_volume",
    "stale_data",
    "short_history",
    "invalid_values",
    "unavailable",
)
SHORT_HISTORY_MIN_ROWS = 200
NUMERIC_QUALITY_COLUMNS = (
    "open",
    "high",
    "low",
    "close",
    "adj_close",
    "volume",
    "dividends",
    "stock_splits",
)
GROUP_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
RUN_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,96}$")
DEFAULT_SCREEN_VIEWS = [
    {
        "name": "momentum",
        "filters": {
            "trend": ["bullish", "constructive"],
            "trend_score_min": 70,
            "relative_strength": ["outperforming", "in_line"],
            "week52_position_min": 0.6,
        },
    },
    {
        "name": "breakout_watch",
        "filters": {
            "breakout_status": ["breakout", "near_breakout"],
            "volume_ratio_min": 1.0,
            "ma_distance_max": 0.08,
        },
    },
    {
        "name": "quality_cache",
        "filters": {
            "data_quality": ["ok"],
            "liquidity_score_min": 20,
        },
    },
]


def refresh_history(
    tickers: list[str],
    *,
    period: str = DEFAULT_PERIOD,
    force: bool = False,
) -> RefreshResponse:
    """Fetch and cache historical OHLCV for explicit tickers."""

    started_at = datetime.now(UTC)
    ensure_data_dirs()
    normalized = normalize_tickers(tickers)
    store = _store()
    fetcher = _fetcher()
    results: list[RefreshTickerResult] = []

    for ticker in normalized:
        try:
            refresh_result = store.refresh(
                ticker,
                fetcher,
                period=period,
                force=force,
            )
            df, error = _unpack_refresh_result(refresh_result)
            if not df.empty and error:
                status = "stale"
            elif not df.empty:
                status = "ok"
            else:
                status = "unavailable"
            results.append(
                RefreshTickerResult(
                    ticker=ticker,
                    status=status,
                    rows=len(df),
                    as_of=_last_date(df),
                    error=error,
                )
            )
        except Exception as exc:
            cached = _safe_read(store, ticker)
            results.append(
                RefreshTickerResult(
                    ticker=ticker,
                    status="stale" if cached is not None and not cached.empty else "failed",
                    rows=0 if cached is None else len(cached),
                    as_of=None if cached is None else _last_date(cached),
                    error=str(exc),
                )
            )

    failed = sum(1 for result in results if result.status in {"failed", "unavailable"})
    stale = sum(1 for result in results if result.status == "stale")
    response = RefreshResponse(
        status="complete" if failed == 0 and stale == 0 else "partial",
        total=len(results),
        succeeded=len(results) - failed,
        failed=failed,
        results=results,
    )
    _write_refresh_run_log(
        started_at=started_at,
        finished_at=datetime.now(UTC),
        period=period,
        source=_refresh_source(fetcher),
        force=force,
        requested_tickers=normalized,
        response=response,
    )
    return response


def get_history(
    ticker: str,
    *,
    start: date | None = None,
    end: date | None = None,
) -> HistoryResponse:
    """Read cached historical rows for one ticker."""

    normalized = normalize_ticker(ticker)
    df = _store().read(normalized)
    df = _filter_dates(df, start=start, end=end)
    return HistoryResponse(
        ticker=normalized,
        count=len(df),
        start=_date_value(df.iloc[0]["date"]) if not df.empty else None,
        end=_date_value(df.iloc[-1]["date"]) if not df.empty else None,
        rows=_records(df),
    )


def get_snapshot(
    ticker: str,
    *,
    benchmark: str = DEFAULT_BENCHMARK,
) -> dict[str, Any]:
    """Build a technical snapshot from local cached history only."""

    normalized = normalize_ticker(ticker)
    benchmark = normalize_ticker(benchmark)
    try:
        df = _store().read(normalized)
    except Exception as exc:
        return _unavailable_snapshot(normalized, f"cached price history unavailable: {exc}")

    benchmark_df = None
    if benchmark != normalized:
        try:
            benchmark_df = _store().read(benchmark)
        except Exception:
            benchmark_df = None
    return _json_clean(_snapshot_builder()(normalized, df, benchmark_df=benchmark_df))


def get_snapshots(
    tickers: list[str],
    *,
    limit: int = 100,
    benchmark: str = DEFAULT_BENCHMARK,
) -> dict[str, Any]:
    """Build technical snapshots for explicit tickers from local cache only."""

    if limit < 1:
        raise ValueError("limit must be at least 1")
    normalized = normalize_tickers(tickers)
    benchmark = normalize_ticker(benchmark)
    limited = normalized[:limit]
    snapshots = [get_snapshot(ticker, benchmark=benchmark) for ticker in limited]
    return _json_clean(
        {
            "status": "ok",
            "benchmark": benchmark,
            "limit": limit,
            "requested_count": len(normalized),
            "count": len(snapshots),
            "tickers": limited,
            "snapshots": snapshots,
        }
    )


def get_chart(
    ticker: str,
    *,
    range_name: str = "1y",
) -> dict[str, Any]:
    """Build chart-ready JSON from local cached history only."""

    normalized = normalize_ticker(ticker)
    try:
        df = _store().read(normalized)
    except Exception as exc:
        return _unavailable_chart(normalized, f"cached price history unavailable: {exc}")
    chart = _chart_builder()(normalized, df, range_name=range_name)
    if chart is None:
        return _unavailable_chart(normalized, "chart unavailable or insufficient history", rows=len(df))
    return _json_clean(chart)


def get_quality() -> dict[str, Any]:
    """Return the cache quality summary and details from local status checks."""

    summary = status_summary(verbose=True)
    quality = summary.get("data_quality") or {}
    return _json_clean(
        {
            "status": quality.get("status", summary.get("cache_status")),
            "cache_status": summary.get("cache_status"),
            "cached_ticker_count": summary.get("cached_ticker_count"),
            "latest_as_of": summary.get("latest_as_of"),
            "last_refresh": summary.get("last_refresh"),
            "stale_count": summary.get("stale_count"),
            "stale_tickers": summary.get("stale_tickers", []),
            "unavailable_count": summary.get("unavailable_count"),
            "data_quality": quality,
            "data_quality_report": summary.get("data_quality_report"),
            "entries": summary.get("entries", []),
        }
    )


def get_screen(
    *,
    tickers: list[str] | None = None,
    group: str | None = None,
    benchmark: str = DEFAULT_BENCHMARK,
    trend: str | list[str] | None = None,
    breakout_status: str | list[str] | None = None,
    data_quality: str | list[str] | None = None,
    rsi_min: float | None = None,
    rsi_max: float | None = None,
    trend_score_min: float | None = None,
    liquidity_score_min: float | None = None,
    relative_strength: str | list[str] | None = None,
    ma_distance_max: float | None = None,
    ma: str = "any",
    week52_position_min: float | None = None,
    week52_position_max: float | None = None,
    volume_ratio_min: float | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Screen locally cached technical snapshots without calling any fetcher."""

    if limit < 1:
        raise ValueError("limit must be at least 1")
    if ma_distance_max is not None and ma_distance_max < 0:
        raise ValueError("ma_distance_max must be non-negative")

    store = _store()
    requested = _screen_tickers(store, tickers=tickers, group=group)
    benchmark = normalize_ticker(benchmark)
    benchmark_df = _safe_read(store, benchmark)

    filters = {
        "trend": _filter_values(trend),
        "breakout_status": _filter_values(breakout_status),
        "data_quality": _filter_values(data_quality),
        "relative_strength": _filter_values(relative_strength),
        "rsi_min": rsi_min,
        "rsi_max": rsi_max,
        "trend_score_min": trend_score_min,
        "liquidity_score_min": liquidity_score_min,
        "ma_distance_max": ma_distance_max,
        "ma": _normalize_ma_selector(ma),
        "week52_position_min": week52_position_min,
        "week52_position_max": week52_position_max,
        "volume_ratio_min": volume_ratio_min,
    }

    rows: list[dict[str, Any]] = []
    for ticker in requested:
        snapshot = _cached_screen_snapshot(store, ticker, benchmark=benchmark, benchmark_df=benchmark_df)
        if _screen_matches(snapshot, filters):
            rows.append(_screen_row(snapshot))
        if len(rows) >= limit:
            break

    return _json_clean(
        {
            "status": "ok",
            "benchmark": benchmark,
            "count": len(rows),
            "requested_count": len(requested),
            "limit": limit,
            "filters": _json_clean(filters),
            "default_views": DEFAULT_SCREEN_VIEWS,
            "results": rows,
        }
    )


def refresh_snapshots(
    tickers: list[str],
    *,
    benchmark: str = DEFAULT_BENCHMARK,
) -> SnapshotRefreshResponse:
    """Generate and persist snapshot JSON sidecars for explicit tickers."""

    ensure_data_dirs()
    normalized = normalize_tickers(tickers)
    benchmark = normalize_ticker(benchmark)
    snapshots: dict[str, dict[str, Any]] = {}
    errors: dict[str, str] = {}

    for ticker in normalized:
        try:
            snapshot = get_snapshot(ticker, benchmark=benchmark)
            snapshots[ticker] = snapshot
            safe_snapshot = _json_clean(snapshot)
            _snapshot_path(ticker).write_text(
                json.dumps(safe_snapshot, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                encoding="utf-8",
            )
        except Exception as exc:
            errors[ticker] = str(exc)

    return SnapshotRefreshResponse(
        status="complete" if not errors else "partial",
        total=len(normalized),
        succeeded=len(normalized) - len(errors),
        failed=len(errors),
        snapshots=snapshots,
        errors=errors,
    )


def status_summary(*, verbose: bool = True) -> dict[str, Any]:
    """Return local cache status for CLI/API diagnostics."""

    ensure_data_dirs()
    store = _store()
    price_files = sorted(store.root.glob("*.parquet"))
    snapshot_files = sorted(SNAPSHOT_DIR.glob("*.json"))
    generated_at = datetime.now(UTC).isoformat()
    entries: list[dict[str, Any]] = []
    latest_as_of: date | None = None
    last_refresh: pd.Timestamp | None = None
    now = datetime.now(UTC).date()

    for path in price_files:
        entry = _status_entry_for_price_file(store, path, now=now)
        entries.append(entry)

        as_of = _parse_date(entry.get("as_of"))
        if as_of is not None:
            latest_as_of = as_of if latest_as_of is None else max(latest_as_of, as_of)

        refresh_ts = _parse_timestamp(entry.get("last_refresh"))
        if refresh_ts is not None:
            last_refresh = refresh_ts if last_refresh is None else max(last_refresh, refresh_ts)

    cached_tickers = [entry["ticker"] for entry in entries]
    stale_tickers = [
        entry["ticker"]
        for entry in entries
        if any(issue.get("type") == "stale_data" for issue in entry.get("data_quality", {}).get("issues", []))
    ]
    unavailable_count = sum(1 for entry in entries if entry.get("status") == "unavailable")
    quality = _quality_summary(entries, generated_at=generated_at)
    if not entries:
        overall_status = "unavailable"
    elif unavailable_count == len(entries):
        overall_status = "unavailable"
    elif quality["issue_count"]:
        overall_status = "partial"
    else:
        overall_status = "ok"

    summary = {
        "status": "ok",
        "cache_status": overall_status,
        "price_history_files": len(price_files),
        "cached_tickers": cached_tickers,
        "cached_ticker_count": len(cached_tickers),
        "latest_as_of": latest_as_of.isoformat() if latest_as_of is not None else None,
        "last_refresh": last_refresh.isoformat() if last_refresh is not None else None,
        "stale_count": len(stale_tickers),
        "stale_tickers": stale_tickers,
        "unavailable_count": unavailable_count,
        "snapshots": len(snapshot_files),
        "snapshot_count": len(snapshot_files),
        "snapshot_tickers": sorted(path.stem.upper() for path in snapshot_files),
        "price_history_dir": str(store.root),
        "snapshot_dir": str(SNAPSHOT_DIR),
        "data_quality": quality,
        "data_quality_report": quality["checks"],
        "groups": _universe_groups_for_status(),
    }
    if verbose:
        summary["entries"] = entries
    return _json_clean(summary)


def get_universes() -> dict[str, Any]:
    """Return configured universe groups with normalized ticker lists."""

    config = _load_universe_config(required=False)
    groups = _normalized_universe_groups(config.get("groups") or {})
    group_meta = _normalized_group_meta(config.get("group_meta") or {}, groups)
    unique = normalize_tickers([ticker for group_tickers in groups.values() for ticker in group_tickers])
    return _json_clean(
        {
            "status": "ok",
            "editable": MARKET_DATA_UNIVERSE_EDITABLE,
            "managed_by": "moomoo",
            "message": (
                "Managed by Moomoo. Run moomoo-sync to update."
                if not MARKET_DATA_UNIVERSE_EDITABLE
                else "Manual universe editing is enabled."
            ),
            "path": str(UNIVERSE_PATH),
            "group_count": len(groups),
            "ticker_count": len(unique),
            "groups": groups,
            "group_meta": group_meta,
        }
    )


def replace_universe_group(group: str, tickers: list[str]) -> dict[str, Any]:
    """Create or replace one universe group."""

    _ensure_universe_editable()
    group_name = _normalize_group_name(group)
    config = _load_universe_config(required=False)
    groups = dict(config.get("groups") or {})
    groups[group_name] = normalize_tickers([str(ticker) for ticker in tickers])
    config["groups"] = _normalized_universe_groups(groups)
    _write_universe_config(config)
    _sync_universe_configs()
    return _universe_group_payload(group_name, config["groups"][group_name])


def add_universe_tickers(group: str, tickers: list[str]) -> dict[str, Any]:
    """Add tickers to one universe group, preserving existing order."""

    _ensure_universe_editable()
    group_name = _normalize_group_name(group)
    config = _load_universe_config(required=False)
    groups = dict(config.get("groups") or {})
    existing = _universe_ticker_values(groups.get(group_name) or [])
    additions = [str(ticker) for ticker in tickers]
    groups[group_name] = normalize_tickers([*existing, *additions])
    config["groups"] = _normalized_universe_groups(groups)
    _write_universe_config(config)
    _sync_universe_configs()
    return _universe_group_payload(group_name, config["groups"][group_name])


def remove_universe_ticker(group: str, ticker: str) -> dict[str, Any]:
    """Remove one ticker from one universe group."""

    _ensure_universe_editable()
    group_name = _normalize_group_name(group)
    target = normalize_ticker(ticker)
    config = _load_universe_config(required=True)
    groups = _normalized_universe_groups(config.get("groups") or {})
    if group_name not in groups:
        raise KeyError(f"Universe group not found: {group_name}")
    if target not in groups[group_name]:
        raise KeyError(f"Ticker {target} not found in universe group {group_name}")
    groups[group_name] = [candidate for candidate in groups[group_name] if candidate != target]
    config["groups"] = groups
    _write_universe_config(config)
    _sync_universe_configs()
    return _universe_group_payload(group_name, groups[group_name])


def remove_universe_group(group: str) -> dict[str, Any]:
    """Remove one configured universe group."""

    _ensure_universe_editable()
    group_name = _normalize_group_name(group)
    config = _load_universe_config(required=True)
    groups = _normalized_universe_groups(config.get("groups") or {})
    if group_name not in groups:
        raise KeyError(f"Universe group not found: {group_name}")
    groups.pop(group_name)
    group_meta = dict(config.get("group_meta") or {})
    group_meta.pop(group_name, None)
    config["groups"] = groups
    config["group_meta"] = group_meta
    _write_universe_config(config)
    _sync_universe_configs()
    return _json_clean({"status": "ok", "group": group_name, "groups": get_universes()["groups"]})


def load_universe_tickers(group: str) -> list[str]:
    """Read ticker symbols for one configured universe group."""

    normalized_group = _normalize_group_name(group)
    groups = _load_universe_groups()
    if normalized_group not in groups:
        available = ", ".join(sorted(groups)) or "none"
        raise ValueError(f"Unknown universe group: {normalized_group}. Available: {available}")
    tickers = groups.get(normalized_group) or []
    return normalize_tickers(_universe_ticker_values(tickers))


def load_all_universe_tickers() -> list[str]:
    """Read all configured universe ticker symbols in file order."""

    groups = _load_universe_groups()
    tickers: list[str] = []
    for group_tickers in groups.values():
        tickers.extend(_universe_ticker_values(group_tickers or []))
    return normalize_tickers(tickers)


def resolve_refresh_tickers(
    tickers: list[str] | None = None,
    *,
    universe: str | None = None,
    all_universes: bool = False,
) -> list[str]:
    """Merge explicit tickers with an optional configured universe."""

    candidates: list[str] = []
    if all_universes:
        candidates.extend(load_all_universe_tickers())
    if universe:
        candidates.extend(load_universe_tickers(universe))
    candidates.extend(tickers or [])
    resolved = normalize_tickers(candidates)
    if not resolved:
        raise ValueError("Provide at least one ticker, --universe, or --all")
    return resolved


def list_refresh_runs(*, limit: int = 50) -> dict[str, Any]:
    """List persisted refresh run logs, newest first."""

    if limit < 1:
        raise ValueError("limit must be at least 1")
    if not REFRESH_RUN_DIR.exists():
        return {"status": "ok", "count": 0, "runs": []}

    runs: list[dict[str, Any]] = []
    for path in sorted(REFRESH_RUN_DIR.glob("*.json"), reverse=True):
        try:
            run = _read_refresh_run(path)
        except Exception:
            continue
        runs.append(_refresh_run_summary(run))
        if len(runs) >= limit:
            break
    return _json_clean({"status": "ok", "count": len(runs), "runs": runs})


def get_refresh_run(run_id: str) -> dict[str, Any]:
    """Return one persisted refresh run log by id."""

    path = _refresh_run_path(run_id)
    if not path.exists():
        raise FileNotFoundError(f"Refresh run not found: {run_id}")
    return _json_clean(_read_refresh_run(path))


def preview_moomoo_research_universe(**kwargs: Any) -> dict[str, Any]:
    """Fetch and convert moomoo research universe without writing config files."""

    return _json_clean(preview_research_universe(**_clean_moomoo_kwargs(kwargs)))


def sync_moomoo_research_universe(
    *,
    sync_firn: bool | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Replace Lab universe from moomoo export and optionally push it to Firn.

    In the standalone project, Firn writes are opt-in: set
    ``FIRN_WATCHLIST_PATH`` or pass ``sync_firn=True`` with a configured path.
    """

    should_sync_firn = DEFAULT_FIRN_WATCHLIST_PATH is not None if sync_firn is None else sync_firn
    if should_sync_firn and DEFAULT_FIRN_WATCHLIST_PATH is None:
        raise ValueError("FIRN_WATCHLIST_PATH is required when sync_firn is enabled")

    preview = preview_research_universe(**_clean_moomoo_kwargs(kwargs))
    groups = preview.get("groups") or {}
    group_meta = preview.get("group_meta") or {}
    if not groups:
        raise ValueError("moomoo research universe produced no mapped ticker groups")

    config = {
        "source": preview.get("source") or "moomoo-account-web",
        "synced_at": preview.get("synced_at"),
        "market": preview.get("market"),
        "positions_status": preview.get("positions_status"),
        "watchlists_status": preview.get("watchlists_status"),
        "groups": groups,
        "group_meta": group_meta,
        "moomoo_sync": {
            "item_count": preview.get("item_count", 0),
            "mapped_count": preview.get("mapped_count", 0),
            "unsupported_count": preview.get("unsupported_count", 0),
            "invalid_count": preview.get("invalid_count", 0),
            "skipped_items": preview.get("skipped_items", []),
        },
    }
    _write_universe_config(config)

    firn_synced = False
    if should_sync_firn:
        _sync_universe_configs()
        firn_synced = True

    return _json_clean(
        {
            **preview,
            "status": "ok",
            "synced": True,
            "universe_path": str(UNIVERSE_PATH),
            "firn_synced": firn_synced,
            "firn_watchlist_path": str(DEFAULT_FIRN_WATCHLIST_PATH) if firn_synced else None,
        }
    )


def _load_universe_groups() -> dict[str, Any]:
    return _load_universe_config(required=True).get("groups") or {}


def _clean_moomoo_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in kwargs.items() if value is not None}


def _universe_groups_for_status() -> dict[str, list[str]]:
    try:
        groups = _load_universe_groups()
    except Exception:
        return {}
    normalized: dict[str, list[str]] = {}
    for group, tickers in groups.items():
        try:
            normalized[str(group)] = normalize_tickers(_universe_ticker_values(tickers or []))
        except ValueError:
            normalized[str(group)] = []
    return normalized


def _load_universe_config(*, required: bool) -> dict[str, Any]:
    if not UNIVERSE_PATH.exists():
        if required:
            raise FileNotFoundError(f"Universe config not found: {UNIVERSE_PATH}")
        return {"groups": {}}
    data = yaml.safe_load(UNIVERSE_PATH.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("Universe config must be a mapping")
    groups = data.get("groups") or {}
    if not isinstance(groups, dict):
        raise ValueError("Universe config must contain a mapping at groups")
    data["groups"] = groups
    return data


def _write_universe_config(config: dict[str, Any]) -> None:
    groups = _normalized_universe_groups(config.get("groups") or {})
    payload = dict(config)
    payload["groups"] = groups
    payload["group_meta"] = _normalized_group_meta(payload.get("group_meta") or {}, groups)
    UNIVERSE_PATH.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(payload, sort_keys=False, default_flow_style=False)
    UNIVERSE_PATH.write_text(text, encoding="utf-8")


def _normalized_universe_groups(groups: dict[str, Any]) -> dict[str, list[str]]:
    normalized: dict[str, list[str]] = {}
    for group, tickers in groups.items():
        group_name = _normalize_group_name(str(group))
        normalized[group_name] = normalize_tickers(_universe_ticker_values(tickers or []))
    return normalized


def _normalized_group_meta(
    group_meta: dict[str, Any],
    groups: dict[str, list[str]],
) -> dict[str, dict[str, Any]]:
    normalized: dict[str, dict[str, Any]] = {}
    for group in groups:
        raw = group_meta.get(group) if isinstance(group_meta, dict) else None
        meta = raw if isinstance(raw, dict) else {}
        tags = meta.get("tags") or [group]
        if isinstance(tags, str):
            tags = [tags]
        try:
            tag_values = [str(tag).strip().lower().replace(" ", "-") for tag in tags]
        except TypeError:
            tag_values = [group]
        tag_values = [tag for tag in dict.fromkeys(tag_values) if tag]
        extra_meta = {
            str(key): value
            for key, value in meta.items()
            if key not in {"label", "tags"}
        }
        normalized[group] = {
            **extra_meta,
            "label": str(meta.get("label") or group.replace("_", " ").title()),
            "tags": tag_values or [group],
        }
    return normalized


def _sync_universe_configs() -> None:
    """Sync Lab universe to Firn when a Firn watchlist path is configured."""

    universe_path = Path(UNIVERSE_PATH)
    firn_path = DEFAULT_FIRN_WATCHLIST_PATH
    if firn_path is None:
        return
    if not universe_path.exists() and not firn_path.exists():
        return
    sync_universe_to_watchlist(universe_path=universe_path, watchlist_path=firn_path)


def _ensure_universe_editable() -> None:
    if not MARKET_DATA_UNIVERSE_EDITABLE:
        raise PermissionError("Universe editing is disabled; use moomoo-sync to update groups")


def _universe_ticker_values(tickers: Any) -> list[str]:
    if isinstance(tickers, str):
        raise ValueError("Universe group tickers must be a list")
    try:
        values = list(tickers)
    except TypeError as exc:
        raise ValueError("Universe group tickers must be a list") from exc
    return [str(ticker) for ticker in values]


def _normalize_group_name(group: str) -> str:
    normalized = str(group).strip()
    if not normalized:
        raise ValueError("universe group is required")
    if not GROUP_RE.match(normalized):
        raise ValueError(f"Invalid universe group: {group!r}")
    return normalized


def _universe_group_payload(group: str, tickers: list[str]) -> dict[str, Any]:
    return _json_clean(
        {
            "status": "ok",
            "group": group,
            "count": len(tickers),
            "tickers": tickers,
            "groups": get_universes()["groups"],
        }
    )


def _screen_tickers(store: Any, *, tickers: list[str] | None, group: str | None) -> list[str]:
    candidates: list[str] = []
    if group:
        candidates.extend(load_universe_tickers(group))
    if tickers:
        candidates.extend(tickers)
    if not candidates:
        candidates.extend(path.stem for path in sorted(store.root.glob("*.parquet")))
    return normalize_tickers(candidates)


def _cached_screen_snapshot(
    store: Any,
    ticker: str,
    *,
    benchmark: str,
    benchmark_df: pd.DataFrame | None,
) -> dict[str, Any]:
    try:
        df = store.read(ticker)
    except Exception as exc:
        return _unavailable_snapshot(ticker, f"cached price history unavailable: {exc}")
    return _json_clean(
        _snapshot_builder()(ticker, df, benchmark_df=None if ticker == benchmark else benchmark_df)
    )


def _screen_row(snapshot: dict[str, Any]) -> dict[str, Any]:
    data_quality = snapshot.get("data_quality") or {}
    relative_strength = snapshot.get("relative_strength_vs_spy") or {}
    volume_signal = snapshot.get("volume_signal") or {}
    row = {
        "ticker": snapshot.get("ticker"),
        "as_of": snapshot.get("as_of"),
        "price": snapshot.get("price"),
        "currency": snapshot.get("currency"),
        "trend": snapshot.get("trend"),
        "breakout_status": snapshot.get("breakout_status"),
        "data_quality": data_quality,
        "data_quality_status": data_quality.get("status"),
        "rsi14": snapshot.get("rsi14"),
        "trend_score": snapshot.get("trend_score"),
        "liquidity_score": snapshot.get("liquidity_score"),
        "relative_strength_vs_spy": relative_strength,
        "relative_strength_status": relative_strength.get("status"),
        "distance_from_ma20": snapshot.get("distance_from_ma20"),
        "distance_from_ma50": snapshot.get("distance_from_ma50"),
        "distance_from_ma200": snapshot.get("distance_from_ma200"),
        "week52_position": snapshot.get("week52_position"),
        "volume_signal": volume_signal,
        "volume_ratio": volume_signal.get("ratio"),
        "return_1m": snapshot.get("return_1m"),
        "return_3m": snapshot.get("return_3m"),
        "return_6m": snapshot.get("return_6m"),
    }
    return _json_clean(row)


def _screen_matches(snapshot: dict[str, Any], filters: dict[str, Any]) -> bool:
    if not _status_matches(snapshot.get("trend"), filters["trend"]):
        return False
    if not _status_matches(snapshot.get("breakout_status"), filters["breakout_status"]):
        return False
    data_quality = snapshot.get("data_quality") or {}
    if not _status_matches(data_quality.get("status"), filters["data_quality"]):
        return False
    relative_strength = snapshot.get("relative_strength_vs_spy") or {}
    if not _status_matches(relative_strength.get("status"), filters["relative_strength"]):
        return False
    if not _number_in_range(snapshot.get("rsi14"), minimum=filters["rsi_min"], maximum=filters["rsi_max"]):
        return False
    if not _number_at_least(snapshot.get("trend_score"), filters["trend_score_min"]):
        return False
    if not _number_at_least(snapshot.get("liquidity_score"), filters["liquidity_score_min"]):
        return False
    if not _number_in_range(
        snapshot.get("week52_position"),
        minimum=filters["week52_position_min"],
        maximum=filters["week52_position_max"],
    ):
        return False
    volume_signal = snapshot.get("volume_signal") or {}
    if not _number_at_least(volume_signal.get("ratio"), filters["volume_ratio_min"]):
        return False
    if not _ma_distance_matches(snapshot, filters["ma_distance_max"], filters["ma"]):
        return False
    return True


def _filter_values(values: str | list[str] | None) -> set[str]:
    if values is None:
        return set()
    raw_values = [values] if isinstance(values, str) else values
    result: set[str] = set()
    for raw in raw_values:
        result.update(part.strip().lower() for part in str(raw).split(",") if part.strip())
    return result


def _status_matches(value: Any, allowed: set[str]) -> bool:
    if not allowed:
        return True
    return str(value).strip().lower() in allowed


def _number_at_least(value: Any, minimum: float | None) -> bool:
    if minimum is None:
        return True
    number = _finite_number(value)
    return number is not None and number >= minimum


def _number_in_range(value: Any, *, minimum: float | None, maximum: float | None) -> bool:
    if minimum is None and maximum is None:
        return True
    number = _finite_number(value)
    if number is None:
        return False
    if minimum is not None and number < minimum:
        return False
    if maximum is not None and number > maximum:
        return False
    return True


def _ma_distance_matches(snapshot: dict[str, Any], threshold: float | None, selector: str) -> bool:
    if threshold is None:
        return True
    fields = {
        "20": ["distance_from_ma20"],
        "50": ["distance_from_ma50"],
        "200": ["distance_from_ma200"],
        "any": ["distance_from_ma20", "distance_from_ma50", "distance_from_ma200"],
    }[selector]
    values = [_finite_number(snapshot.get(field)) for field in fields]
    return any(value is not None and abs(value) <= threshold for value in values)


def _normalize_ma_selector(value: str) -> str:
    normalized = str(value or "any").strip().lower().replace("ma", "")
    if normalized in {"", "all"}:
        normalized = "any"
    if normalized not in {"20", "50", "200", "any"}:
        raise ValueError("ma must be one of any, 20, 50, or 200")
    return normalized


def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _write_refresh_run_log(
    *,
    started_at: datetime,
    finished_at: datetime,
    period: str,
    source: str,
    force: bool,
    requested_tickers: list[str],
    response: RefreshResponse,
) -> dict[str, Any]:
    results = [result.model_dump() for result in response.results]
    run_id = _new_run_id(started_at)
    success = sum(1 for result in results if result.get("status") == "ok")
    fail = sum(1 for result in results if result.get("status") in {"failed", "unavailable"})
    stale = sum(1 for result in results if result.get("status") == "stale")
    payload = _json_clean(
        {
            "run_id": run_id,
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "period": period,
            "source": source,
            "force": force,
            "requested_tickers": requested_tickers,
            "status": response.status,
            "total": response.total,
            "success": success,
            "fail": fail,
            "stale": stale,
            "per_ticker": results,
            "results": results,
        }
    )
    REFRESH_RUN_DIR.mkdir(parents=True, exist_ok=True)
    _refresh_run_path(run_id).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return payload


def _new_run_id(started_at: datetime) -> str:
    return f"{started_at.strftime('%Y%m%dT%H%M%S%fZ')}-{uuid4().hex[:8]}"


def _refresh_run_path(run_id: str) -> Path:
    normalized = str(run_id).strip()
    if not RUN_ID_RE.match(normalized):
        raise ValueError(f"Invalid refresh run id: {run_id!r}")
    return REFRESH_RUN_DIR / f"{normalized}.json"


def _read_refresh_run(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Refresh run log must be a JSON object: {path}")
    return data


def _refresh_run_summary(run: dict[str, Any]) -> dict[str, Any]:
    return _json_clean(
        {
            "run_id": run.get("run_id"),
            "started_at": run.get("started_at"),
            "finished_at": run.get("finished_at"),
            "period": run.get("period"),
            "source": run.get("source"),
            "status": run.get("status"),
            "total": run.get("total"),
            "success": run.get("success"),
            "fail": run.get("fail"),
            "stale": run.get("stale"),
            "requested_tickers": run.get("requested_tickers", []),
        }
    )


def _refresh_source(fetcher: Any) -> str:
    module = str(getattr(fetcher, "__module__", ""))
    if "yfinance" in module:
        return "yfinance"
    name = str(getattr(fetcher, "__name__", "")).strip()
    return name or "unknown"


def _status_entry_for_price_file(store: Any, path: Path, *, now: date) -> dict[str, Any]:
    ticker = path.stem.upper()
    try:
        raw = pd.read_parquet(path)
        df = store._normalize_cached(raw, ticker)
    except Exception as exc:
        issue = _quality_issue(
            "unavailable",
            f"cached price history could not be read: {exc}",
            severity="error",
        )
        return {
            "ticker": ticker,
            "rows": 0,
            "raw_rows": 0,
            "as_of": None,
            "last_refresh": None,
            "status": "unavailable",
            "stale_days": None,
            "warnings": [issue["message"]],
            "data_quality": {
                "status": "unavailable",
                "issues": [issue],
            },
        }

    as_of = _last_date(df)
    as_of_date = _parse_date(as_of)
    stale_days = (now - as_of_date).days if as_of_date is not None else None
    issues = _quality_issues_for_cache(ticker, raw, df, as_of_date=as_of_date, stale_days=stale_days)
    if any(issue["type"] == "unavailable" for issue in issues):
        status = "unavailable"
        quality_status = "unavailable"
    elif any(issue["type"] == "stale_data" for issue in issues):
        status = "stale"
        quality_status = "partial"
    elif issues:
        status = "partial"
        quality_status = "partial"
    else:
        status = "ok"
        quality_status = "ok"

    return {
        "ticker": ticker,
        "rows": len(df),
        "raw_rows": len(raw),
        "as_of": as_of,
        "last_refresh": _last_refresh(raw),
        "status": status,
        "stale_days": stale_days,
        "warnings": [issue["message"] for issue in issues],
        "data_quality": {
            "status": quality_status,
            "issues": issues,
        },
    }


def _quality_issues_for_cache(
    ticker: str,
    raw: pd.DataFrame,
    df: pd.DataFrame,
    *,
    as_of_date: date | None,
    stale_days: int | None,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    raw_rows = len(raw)
    rows = len(df)

    if rows == 0 or as_of_date is None:
        issues.append(
            _quality_issue(
                "unavailable",
                "no usable cached price rows are available",
                severity="error",
                rows=rows,
            )
        )

    missing_price = _missing_count(raw, "close")
    if missing_price:
        issues.append(
            _quality_issue(
                "missing_price",
                f"{missing_price} cached rows have no close price",
                severity="error",
                count=missing_price,
                rows=raw_rows,
            )
        )

    missing_volume = _missing_count(raw, "volume")
    if missing_volume:
        issues.append(
            _quality_issue(
                "missing_volume",
                f"{missing_volume} cached rows have no volume",
                count=missing_volume,
                rows=raw_rows,
            )
        )

    if stale_days is not None and stale_days > STALE_PRICE_MAX_AGE_DAYS:
        issues.append(
            _quality_issue(
                "stale_data",
                f"latest cached date is {stale_days} days old",
                count=stale_days,
                stale_days=stale_days,
                as_of=as_of_date.isoformat(),
            )
        )

    if 0 < rows < SHORT_HISTORY_MIN_ROWS:
        issues.append(
            _quality_issue(
                "short_history",
                f"only {rows} usable rows; at least {SHORT_HISTORY_MIN_ROWS} are preferred",
                count=rows,
                rows=rows,
            )
        )

    invalid = _invalid_numeric_values(raw)
    if invalid:
        count = sum(invalid.values())
        columns = sorted(invalid)
        issues.append(
            _quality_issue(
                "invalid_values",
                f"{count} invalid or non-finite numeric values found",
                severity="error",
                count=count,
                columns=columns,
                column_counts=invalid,
            )
        )

    return issues


def _quality_summary(entries: list[dict[str, Any]], *, generated_at: str) -> dict[str, Any]:
    report: dict[str, list[dict[str, Any]]] = {kind: [] for kind in QUALITY_TYPES}
    for entry in entries:
        for issue in entry.get("data_quality", {}).get("issues", []):
            kind = str(issue.get("type", "invalid_values"))
            if kind not in report:
                report[kind] = []
            detail = {key: value for key, value in issue.items() if key != "type"}
            detail["ticker"] = entry["ticker"]
            report[kind].append(_json_clean(detail))

    checks = {
        kind: {
            "count": len(details),
            "tickers": sorted({str(detail["ticker"]) for detail in details}),
            "details": details,
        }
        for kind, details in report.items()
    }
    issue_count = sum(check["count"] for check in checks.values())
    if not entries:
        status = "unavailable"
    elif issue_count:
        status = "partial"
    else:
        status = "ok"
    return {
        "status": status,
        "generated_at": generated_at,
        "issue_count": issue_count,
        "checks": checks,
    }


def _quality_issue(kind: str, message: str, **details: Any) -> dict[str, Any]:
    issue = {
        "type": kind,
        "severity": details.pop("severity", "warning"),
        "message": message,
    }
    for key, value in details.items():
        if value is not None:
            issue[key] = value
    return issue


def _missing_count(df: pd.DataFrame, column: str) -> int:
    if column not in df.columns:
        return len(df)
    return int(df[column].isna().sum())


def _invalid_numeric_values(df: pd.DataFrame) -> dict[str, int]:
    invalid: dict[str, int] = {}
    for column in NUMERIC_QUALITY_COLUMNS:
        if column not in df.columns:
            continue
        count = _invalid_numeric_count(df[column])
        if count:
            invalid[column] = count
    return invalid


def _invalid_numeric_count(series: pd.Series) -> int:
    numeric = pd.to_numeric(series, errors="coerce")
    count = 0
    for raw_value, numeric_value in zip(series, numeric, strict=False):
        try:
            raw_missing = pd.isna(raw_value)
        except (TypeError, ValueError):
            raw_missing = False
        if raw_missing:
            continue
        try:
            value = float(numeric_value)
        except (TypeError, ValueError):
            count += 1
            continue
        if not math.isfinite(value):
            count += 1
    return count


def _last_refresh(df: pd.DataFrame) -> str | None:
    if df.empty or "fetched_at" not in df.columns:
        return None
    values = pd.to_datetime(df["fetched_at"], utc=True, errors="coerce")
    values = values.dropna()
    if values.empty:
        return None
    return values.max().isoformat()


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    try:
        parsed = pd.to_datetime(value, errors="coerce")
    except Exception:
        return None
    if pd.isna(parsed):
        return None
    return parsed.date()


def _parse_timestamp(value: Any) -> pd.Timestamp | None:
    if value is None:
        return None
    try:
        parsed = pd.to_datetime(value, utc=True, errors="coerce")
    except Exception:
        return None
    if pd.isna(parsed):
        return None
    return parsed


def _filter_dates(
    df: pd.DataFrame,
    *,
    start: date | None,
    end: date | None,
) -> pd.DataFrame:
    if df.empty:
        return df
    result = df.copy()
    result["date"] = pd.to_datetime(result["date"]).dt.date
    if start:
        result = result[result["date"] >= start]
    if end:
        result = result[result["date"] <= end]
    return result.reset_index(drop=True)


def _records(df: pd.DataFrame) -> list[dict[str, Any]]:
    if df.empty:
        return []
    cleaned = df.copy()
    cleaned["date"] = pd.to_datetime(cleaned["date"]).dt.date.astype(str)
    return [_json_clean(record) for record in cleaned.to_dict(orient="records")]


def _last_date(df: pd.DataFrame) -> str | None:
    if df.empty or "date" not in df.columns:
        return None
    return str(pd.to_datetime(df["date"]).max().date())


def _date_value(value: Any) -> date | None:
    if value is None or pd.isna(value):
        return None
    return pd.to_datetime(value).date()


def _safe_read(store: Any, ticker: str) -> pd.DataFrame | None:
    try:
        return store.read(ticker)
    except Exception:
        return None


def _unpack_refresh_result(result: Any) -> tuple[pd.DataFrame, str | None]:
    if isinstance(result, tuple):
        df = result[0]
        error = result[1] if len(result) > 1 else None
        return df, error
    df = getattr(result, "data", None)
    if df is None:
        df = getattr(result, "df", None)
    error = getattr(result, "error", None)
    if isinstance(df, pd.DataFrame):
        return df, error
    if isinstance(result, pd.DataFrame):
        return result, None
    return pd.DataFrame(), error or "unknown refresh result"


def _json_clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_clean(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_clean(item) for item in value]
    if isinstance(value, tuple):
        return [_json_clean(item) for item in value]
    if isinstance(value, set):
        return sorted(_json_clean(item) for item in value)
    if isinstance(value, (pd.Timestamp, date)):
        return value.isoformat()
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        try:
            return _json_clean(value.item())
        except Exception:
            return str(value)
    return value


def _unavailable_snapshot(ticker: str, warning: str) -> dict[str, Any]:
    return {
        "ticker": ticker,
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
        "support_levels": [],
        "resistance_levels": [],
        "trend": "unavailable",
        "breakout_status": "unavailable",
        "relative_strength_vs_spy": {"benchmark": "SPY", "status": "unavailable", "periods": {}},
        "volume_signal": {"status": "unavailable"},
        "data_quality": {
            "status": "unavailable",
            "warnings": [warning],
            "source": "parquet",
            "rows": 0,
            "as_of": None,
            "generated_at": datetime.now(UTC).isoformat(),
        },
    }


def _unavailable_chart(ticker: str, warning: str, *, rows: int = 0) -> dict[str, Any]:
    return {
        "ticker": ticker,
        "as_of": None,
        "currency": "unavailable",
        "has_image": False,
        "points": [],
        "ma20": [],
        "ma50": [],
        "ma200": [],
        "support_levels": [],
        "resistance_levels": [],
        "data_quality": {
            "status": "unavailable",
            "warnings": [warning],
            "source": "parquet",
            "rows": rows,
            "as_of": None,
            "generated_at": datetime.now(UTC).isoformat(),
        },
    }


def _snapshot_path(ticker: str) -> Path:
    safe = normalize_ticker(ticker).replace("/", "_")
    return SNAPSHOT_DIR / f"{safe}.json"


def _store() -> Any:
    from market_data_lab.storage.parquet_store import ParquetPriceStore

    return ParquetPriceStore()


def _fetcher() -> Any:
    from market_data_lab.fetchers.yfinance_provider import fetch_price_history

    return fetch_price_history


def _snapshot_builder() -> Any:
    from market_data_lab.snapshots.technical_snapshot import build_snapshot

    return build_snapshot


def _chart_builder() -> Any:
    from market_data_lab.charts.chart_data import build_chart

    return build_chart
