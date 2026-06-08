"""Compact CLI for Market Data Lab."""

from __future__ import annotations

import argparse
import inspect
import json
from typing import Any

from market_data_lab import services as backend_services
from market_data_lab.config import DEFAULT_CHART_RANGE, DEFAULT_PERIOD
from market_data_lab.services import (
    get_chart,
    get_history,
    get_snapshot,
    preview_moomoo_research_universe,
    refresh_history,
    resolve_refresh_tickers,
    status_summary,
    sync_moomoo_research_universe,
)

RUN_SERVICE_FUNCTIONS = (
    "get_refresh_runs",
    "list_refresh_runs",
    "get_recent_refresh_runs",
    "recent_refresh_runs",
)


def main() -> None:
    parser = argparse.ArgumentParser(prog="market-data")
    subparsers = parser.add_subparsers(dest="command", required=True)

    refresh = subparsers.add_parser("refresh", help="Fetch and cache price history")
    refresh.add_argument("tickers", nargs="*")
    refresh.add_argument("--universe", help="Refresh a group from config/universe.yaml")
    refresh.add_argument("--all", action="store_true", dest="all_universes", help="Refresh every configured universe group")
    refresh.add_argument("--period", default=DEFAULT_PERIOD)
    refresh.add_argument("--force", action="store_true")

    snapshot = subparsers.add_parser("snapshot", help="Print a technical snapshot")
    snapshot.add_argument("ticker")
    snapshot.add_argument("--benchmark", default="SPY")

    chart = subparsers.add_parser("chart", help="Print chart-ready JSON")
    chart.add_argument("ticker")
    chart.add_argument("--range", default=DEFAULT_CHART_RANGE, choices=["6mo", "1y", "2y", "5y"])

    history = subparsers.add_parser("history", help="Print cached history rows")
    history.add_argument("ticker")
    history.add_argument("--limit", type=int, default=5)

    status = subparsers.add_parser("status", help="Print cache status")
    status.add_argument("--verbose", action="store_true", help="Include per-ticker cache diagnostics")

    subparsers.add_parser("quality", help="Print a compact cache quality report")

    runs = subparsers.add_parser("runs", help="Print recent refresh runs")
    runs.add_argument("--limit", type=_positive_int, default=5, help="Maximum runs to show")

    moomoo_preview = subparsers.add_parser("moomoo-preview", help="Preview moomoo research universe sync")
    _add_moomoo_args(moomoo_preview)

    moomoo_sync = subparsers.add_parser("moomoo-sync", help="Replace Lab universe from moomoo export")
    _add_moomoo_args(moomoo_sync)
    moomoo_sync.add_argument("--no-firn", action="store_true", help="Do not push the synced universe to Firn")

    args = parser.parse_args()

    if args.command == "refresh":
        tickers = resolve_refresh_tickers(args.tickers, universe=args.universe, all_universes=args.all_universes)
        result = refresh_history(tickers, period=args.period, force=args.force)
        print(f"Refresh {result.status}: {result.succeeded}/{result.total} succeeded")
        run_id = _first_value(_coerce_mapping(result), "run_id", "id")
        if run_id:
            print(f"run_id={run_id}")
        for item in result.results:
            suffix = f" | {item.error}" if item.error else ""
            print(f"  {item.ticker}: {item.status} | rows={item.rows} | as_of={item.as_of}{suffix}")
        return

    if args.command == "snapshot":
        print(json.dumps(get_snapshot(args.ticker, benchmark=args.benchmark), indent=2, ensure_ascii=False, allow_nan=False))
        return

    if args.command == "chart":
        print(json.dumps(get_chart(args.ticker, range_name=args.range), indent=2, ensure_ascii=False, allow_nan=False))
        return

    if args.command == "history":
        response = get_history(args.ticker)
        rows = response.rows[-args.limit:] if args.limit > 0 else response.rows
        payload = {**response.model_dump(mode="json", exclude={"rows"}), "rows": rows}
        print(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False))
        return

    if args.command == "status":
        print(json.dumps(status_summary(verbose=args.verbose), indent=2, ensure_ascii=False, allow_nan=False))
        return

    if args.command == "quality":
        print(format_quality_report(status_summary(verbose=True)))
        return

    if args.command == "runs":
        print(format_runs_report(recent_refresh_runs(limit=args.limit)))
        return

    if args.command == "moomoo-preview":
        result = preview_moomoo_research_universe(**_moomoo_kwargs(args))
        print(format_moomoo_sync_report(result, preview=True))
        return

    if args.command == "moomoo-sync":
        result = sync_moomoo_research_universe(sync_firn=not args.no_firn, **_moomoo_kwargs(args))
        print(format_moomoo_sync_report(result, preview=False))
        return


def _add_moomoo_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--base-url", help="Moomoo Account Web base URL")
    parser.add_argument("--host", help="OpenD host passed through to moomoo export")
    parser.add_argument("--port", type=int, help="OpenD port passed through to moomoo export")
    parser.add_argument("--market", help="Moomoo market filter")
    parser.add_argument("--group-type", help="Moomoo watchlist group type")
    parser.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout in seconds")


def _moomoo_kwargs(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "base_url": args.base_url,
        "host": args.host,
        "port": args.port,
        "market": args.market,
        "group_type": args.group_type,
        "timeout": args.timeout,
    }


def recent_refresh_runs(*, limit: int = 5) -> list[dict[str, Any]]:
    """Read recent refresh runs from services, falling back to cache status."""

    for name in RUN_SERVICE_FUNCTIONS:
        service = getattr(backend_services, name, None)
        if not callable(service):
            continue
        result = _call_runs_service(service, limit=limit)
        runs = _coerce_runs(result, limit=limit)
        if runs:
            return runs
    return _runs_from_status(status_summary(verbose=True), limit=limit)


def format_runs_report(runs: list[dict[str, Any]]) -> str:
    """Format recent refresh runs for compact human CLI output."""

    if not runs:
        return "No refresh runs found."

    lines = ["Recent refresh runs:"]
    for run in runs:
        parts = [
            f"run_id={_first_value(run, 'run_id', 'id') or 'n/a'}",
            f"status={_first_value(run, 'status', 'state') or 'unknown'}",
        ]

        completed_at = _first_value(run, "completed_at", "finished_at", "ended_at", "last_refresh")
        started_at = _first_value(run, "started_at", "created_at", "generated_at")
        if completed_at:
            parts.append(f"completed_at={completed_at}")
        elif started_at:
            parts.append(f"started_at={started_at}")

        counts = _format_run_counts(run)
        if counts:
            parts.append(counts)

        latest_as_of = _first_value(run, "latest_as_of", "as_of")
        if latest_as_of:
            parts.append(f"latest_as_of={latest_as_of}")

        source = _first_value(run, "source")
        if source:
            parts.append(f"source={source}")

        tickers = _format_tickers(run)
        if tickers:
            parts.append(f"tickers={tickers}")

        lines.append("- " + " | ".join(str(part) for part in parts))
    return "\n".join(lines)


def format_quality_report(summary: dict) -> str:
    """Format the status summary's data quality report for humans."""

    quality = summary.get("data_quality") or {}
    checks = summary.get("data_quality_report") or quality.get("checks") or {}
    status = quality.get("status") or summary.get("cache_status") or "unknown"
    issue_count = quality.get("issue_count", _issue_count(checks))
    cached_count = summary.get("cached_ticker_count", len(summary.get("cached_tickers") or []))
    latest_as_of = summary.get("latest_as_of") or "n/a"
    last_refresh = summary.get("last_refresh") or "n/a"
    stale_count = summary.get("stale_count", 0)
    unavailable_count = summary.get("unavailable_count", 0)

    lines = [
        f"Market data quality: {status} ({issue_count} issues)",
        f"Cached tickers: {cached_count} | latest as-of: {latest_as_of} | last refresh: {last_refresh}",
        f"Stale tickers: {stale_count} | unavailable tickers: {unavailable_count}",
    ]

    if not checks:
        lines.append("No quality checks available.")
        return "\n".join(lines)

    issue_checks = [(kind, check) for kind, check in checks.items() if int(check.get("count") or 0) > 0]
    if not issue_checks:
        lines.append("All quality checks passed.")
        return "\n".join(lines)

    lines.append("Issues:")
    for kind, check in issue_checks:
        count = int(check.get("count") or 0)
        tickers = ", ".join(str(ticker) for ticker in check.get("tickers") or []) or "n/a"
        lines.append(f"- {_human_label(kind)}: {count} ({tickers})")
        details = check.get("details") or []
        for detail in details[:3]:
            ticker = detail.get("ticker", "n/a")
            message = detail.get("message") or _detail_fallback(detail)
            lines.append(f"  {ticker}: {message}")
        extra = max(count - min(len(details), 3), 0)
        if extra > 0:
            lines.append(f"  ... {extra} more")

    return "\n".join(lines)


def format_moomoo_sync_report(result: dict[str, Any], *, preview: bool) -> str:
    """Format moomoo preview/sync output for compact CLI use."""

    action = "Moomoo preview" if preview else "Moomoo sync"
    lines = [
        f"{action}: {result.get('status', 'unknown')}",
        (
            f"mapped={result.get('mapped_count', 0)} | "
            f"unsupported={result.get('unsupported_count', 0)} | "
            f"invalid={result.get('invalid_count', 0)} | "
            f"groups={result.get('group_count', 0)} | "
            f"tickers={result.get('ticker_count', 0)}"
        ),
    ]
    if not preview:
        lines.append(
            f"universe={result.get('universe_path', 'n/a')} | "
            f"firn_synced={result.get('firn_synced', False)}"
        )
    groups = result.get("groups") or {}
    for group, tickers in groups.items():
        shown = ", ".join(str(ticker) for ticker in list(tickers)[:8])
        extra = len(tickers) - min(len(tickers), 8)
        suffix = f", +{extra}" if extra > 0 else ""
        lines.append(f"- {group}: {len(tickers)} [{shown}{suffix}]")
    skipped = result.get("skipped_items") or []
    if skipped:
        lines.append(f"skipped_items={len(skipped)}")
    return "\n".join(lines)


def _issue_count(checks: dict) -> int:
    return sum(int(check.get("count") or 0) for check in checks.values())


def _human_label(value: str) -> str:
    return str(value).replace("_", " ").title()


def _detail_fallback(detail: dict) -> str:
    fields = [
        f"{key}={value}"
        for key, value in detail.items()
        if key not in {"ticker", "severity"} and value is not None
    ]
    return ", ".join(fields) if fields else "quality issue detected"


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def _call_runs_service(service: Any, *, limit: int) -> Any:
    try:
        signature = inspect.signature(service)
    except (TypeError, ValueError):
        return service(limit=limit)

    parameters = tuple(signature.parameters.values())
    if any(parameter.name == "limit" or parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters):
        return service(limit=limit)
    if any(
        parameter.kind
        in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.VAR_POSITIONAL)
        for parameter in parameters
    ):
        return service(limit)
    return service()


def _coerce_runs(value: Any, *, limit: int) -> list[dict[str, Any]]:
    value = _coerce_jsonish(value)
    if isinstance(value, dict):
        for key in ("runs", "refresh_runs", "recent_runs", "items", "results"):
            items = value.get(key)
            if isinstance(items, list):
                return [_coerce_mapping(item) for item in items[:limit]]
        if _looks_like_run(value):
            return [_coerce_mapping(value)]
        return []
    if isinstance(value, list):
        return [_coerce_mapping(item) for item in value[:limit]]
    return []


def _runs_from_status(summary: dict[str, Any], *, limit: int) -> list[dict[str, Any]]:
    last_refresh = summary.get("last_refresh")
    if not last_refresh:
        return []

    entries = summary.get("entries") or []
    latest_entries = [
        entry
        for entry in entries
        if isinstance(entry, dict) and entry.get("last_refresh") == last_refresh
    ]
    ticker_count = len(latest_entries) if latest_entries else summary.get("cached_ticker_count")
    tickers = [entry.get("ticker") for entry in latest_entries if entry.get("ticker")]
    run = {
        "status": summary.get("cache_status") or summary.get("status"),
        "last_refresh": last_refresh,
        "latest_as_of": summary.get("latest_as_of"),
        "total": ticker_count,
        "source": "cache-status",
        "tickers": tickers,
    }
    return [run][:limit]


def _coerce_mapping(value: Any) -> dict[str, Any]:
    value = _coerce_jsonish(value)
    if isinstance(value, dict):
        return value
    if hasattr(value, "__dict__"):
        return {key: _coerce_jsonish(item) for key, item in vars(value).items() if not key.startswith("_")}
    return {}


def _coerce_jsonish(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, tuple):
        return list(value)
    return value


def _looks_like_run(value: dict[str, Any]) -> bool:
    return any(
        key in value
        for key in (
            "run_id",
            "id",
            "status",
            "state",
            "started_at",
            "completed_at",
            "last_refresh",
        )
    )


def _first_value(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, ""):
            return value
    return None


def _format_run_counts(run: dict[str, Any]) -> str | None:
    total = _first_value(run, "total", "ticker_count", "requested_count", "count")
    succeeded = _first_value(run, "succeeded", "success_count")
    failed = _first_value(run, "failed", "failed_count")

    if total is None and succeeded is None and failed is None:
        return None
    if succeeded is not None and total is not None:
        text = f"succeeded={succeeded}/{total}"
    elif total is not None:
        text = f"total={total}"
    else:
        text = f"succeeded={succeeded}"
    if failed is not None:
        text = f"{text} failed={failed}"
    return text


def _format_tickers(run: dict[str, Any]) -> str | None:
    tickers = _first_value(run, "tickers", "universe_tickers")
    if not isinstance(tickers, list) or not tickers:
        return None
    shown = [str(ticker) for ticker in tickers[:6]]
    extra = len(tickers) - len(shown)
    suffix = f",+{extra}" if extra > 0 else ""
    return ",".join(shown) + suffix


if __name__ == "__main__":
    main()
