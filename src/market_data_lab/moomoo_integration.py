"""Read-only moomoo account-web adapter for Market Data Lab universes."""

from __future__ import annotations

import json
import math
import re
import urllib.parse
import urllib.request
from datetime import date, datetime
from typing import Any

from market_data_lab.config import (
    MOOMOO_ACCOUNT_WEB_URL,
    MOOMOO_EXPORT_GROUP_TYPE,
    MOOMOO_EXPORT_HOST,
    MOOMOO_EXPORT_MARKET,
    MOOMOO_EXPORT_PORT,
)
from market_data_lab.models import normalize_ticker, normalize_tickers

EXPORT_PATH = "api/research-universe/export"
_SLUG_RE = re.compile(r"[^a-z0-9_]+")


def fetch_research_universe(
    base_url: str = MOOMOO_ACCOUNT_WEB_URL,
    host: str = MOOMOO_EXPORT_HOST,
    port: int = MOOMOO_EXPORT_PORT,
    market: str = MOOMOO_EXPORT_MARKET,
    group_type: str = MOOMOO_EXPORT_GROUP_TYPE,
    timeout: float = 10.0,
) -> dict[str, Any]:
    """Fetch the read-only research-universe export from account-web."""

    url = _research_universe_export_url(
        base_url=base_url,
        host=host,
        port=port,
        market=market,
        group_type=group_type,
    )
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "market-data-lab/moomoo-integration",
        },
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset("utf-8")
        data = response.read().decode(charset)
    payload = json.loads(data)
    if not isinstance(payload, dict):
        raise ValueError("moomoo research universe export must be a JSON object")
    return _json_safe(payload)


def build_universe_from_export(payload: dict[str, Any]) -> dict[str, Any]:
    """Transform account-web export payload into Market Data Lab universe groups."""

    if not isinstance(payload, dict):
        raise ValueError("payload must be a mapping")

    items = payload.get("items") or []
    if not isinstance(items, list):
        raise ValueError("payload items must be a list")

    groups: dict[str, list[str]] = {
        "moomoo_positions": [],
    }
    group_meta: dict[str, dict[str, Any]] = {
        "moomoo_positions": {
            "label": "Moomoo Positions",
            "tags": ["moomoo", "positions"],
        },
    }
    all_tickers: list[str] = []
    skipped_items: list[dict[str, Any]] = []
    mapped_count = 0
    unsupported_count = 0
    invalid_count = 0

    watchlist_groups: dict[str, list[tuple[int, int, int, str]]] = {}
    watchlist_group_order: dict[str, int] = {}

    ordered_items = sorted(
        enumerate(items),
        key=lambda item: _order_key((item[1] if isinstance(item[1], dict) else {}).get("universe_order"), item[0]),
    )

    for item_order, (index, raw_item) in enumerate(ordered_items):
        item = raw_item if isinstance(raw_item, dict) else {}
        mapping_status = str(item.get("mapping_status") or "").strip().lower()
        if mapping_status != "mapped":
            unsupported_count += 1
            skipped_items.append(_skipped_item(index, item, "unsupported"))
            continue

        raw_ticker = item.get("market_data_ticker")
        if raw_ticker is None or not str(raw_ticker).strip():
            invalid_count += 1
            skipped_items.append(_skipped_item(index, item, "empty_ticker"))
            continue

        try:
            ticker = normalize_ticker(raw_ticker)
        except ValueError as exc:
            invalid_count += 1
            skipped_items.append(_skipped_item(index, item, "invalid_ticker", error=str(exc)))
            continue

        mapped_count += 1
        _append_unique(all_tickers, ticker)

        sources = _source_values(item.get("sources"))
        if item.get("held") is True or "positions" in sources:
            _append_unique(groups["moomoo_positions"], ticker)

        for ref_index, ref in enumerate(_watchlist_refs(item, sources)):
            watchlist_name = ref["group_name"]
            group_name = f"moomoo_watchlist_{_slug(watchlist_name)}"
            group_order = _order_value(ref.get("group_order"), len(watchlist_group_order))
            security_order = _order_value(ref.get("security_order"), item_order)
            if group_name not in watchlist_groups:
                watchlist_groups[group_name] = []
                watchlist_group_order[group_name] = group_order
                group_meta[group_name] = {
                    "label": f"Moomoo Watchlist: {watchlist_name or 'Unnamed'}",
                    "tags": ["moomoo", "watchlist", group_name.removeprefix("moomoo_watchlist_")],
                    "source": ref.get("source") or f"watchlist:{watchlist_name}",
                    "watchlist_name": watchlist_name or "Unnamed",
                    "group_order": group_order,
                }
            else:
                watchlist_group_order[group_name] = min(watchlist_group_order[group_name], group_order)
                group_meta[group_name]["group_order"] = watchlist_group_order[group_name]
            watchlist_groups[group_name].append((security_order, item_order, ref_index, ticker))

    for group_name in sorted(watchlist_groups, key=lambda name: (watchlist_group_order[name], name)):
        ordered_tickers = [
            ticker
            for _, _, _, ticker in sorted(watchlist_groups[group_name], key=lambda entry: entry[:3])
        ]
        groups[group_name] = normalize_tickers(ordered_tickers)

    groups = {group: normalize_tickers(tickers) for group, tickers in groups.items()}
    tickers = normalize_tickers(all_tickers)
    result = {
        "status": payload.get("status") or ("ok" if tickers else "empty"),
        "source": payload.get("source") or "moomoo-account-web",
        "synced_at": payload.get("synced_at"),
        "market": payload.get("market"),
        "positions_status": payload.get("positions_status"),
        "watchlists_status": payload.get("watchlists_status"),
        "item_count": len(items),
        "mapped_count": mapped_count,
        "unsupported_count": unsupported_count,
        "invalid_count": invalid_count,
        "group_count": len(groups),
        "ticker_count": len(tickers),
        "groups": groups,
        "group_meta": group_meta,
        "skipped_items": skipped_items,
    }
    return _json_safe(result)


def preview_research_universe(
    base_url: str = MOOMOO_ACCOUNT_WEB_URL,
    host: str = MOOMOO_EXPORT_HOST,
    port: int = MOOMOO_EXPORT_PORT,
    market: str = MOOMOO_EXPORT_MARKET,
    group_type: str = MOOMOO_EXPORT_GROUP_TYPE,
    timeout: float = 10.0,
) -> dict[str, Any]:
    """Fetch and transform the moomoo research universe without writing files."""

    payload = fetch_research_universe(
        base_url=base_url,
        host=host,
        port=port,
        market=market,
        group_type=group_type,
        timeout=timeout,
    )
    return build_universe_from_export(payload)


def _research_universe_export_url(
    *,
    base_url: str,
    host: str,
    port: int,
    market: str,
    group_type: str,
) -> str:
    base = str(base_url or "").strip()
    if not base:
        raise ValueError("base_url is required")
    endpoint = urllib.parse.urljoin(f"{base.rstrip('/')}/", EXPORT_PATH)
    query = urllib.parse.urlencode(
        {
            "host": str(host),
            "port": int(port),
            "market": str(market),
            "group_type": str(group_type),
        }
    )
    return f"{endpoint}?{query}"


def _append_unique(values: list[str], ticker: str) -> None:
    if ticker not in values:
        values.append(ticker)


def _order_value(value: Any, fallback: int) -> int:
    if isinstance(value, bool):
        return fallback
    if isinstance(value, (int, float)) and math.isfinite(value):
        return int(value)
    try:
        text = str(value).strip()
    except Exception:
        return fallback
    if not text:
        return fallback
    try:
        return int(float(text))
    except ValueError:
        return fallback


def _order_key(value: Any, fallback: int) -> tuple[int, int]:
    if isinstance(value, bool):
        return (1, fallback)
    if isinstance(value, (int, float)) and math.isfinite(value):
        return (0, int(value))
    try:
        text = str(value).strip()
    except Exception:
        return (1, fallback)
    if not text:
        return (1, fallback)
    try:
        return (0, int(float(text)))
    except ValueError:
        return (1, fallback)


def _slug(value: str) -> str:
    normalized = _SLUG_RE.sub("_", str(value or "").strip().lower()).strip("_")
    return normalized or "unnamed"


def _source_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        candidates = [value]
    else:
        try:
            candidates = list(value)
        except TypeError:
            candidates = []
    result: list[str] = []
    for candidate in candidates:
        source = str(candidate).strip()
        if source and source not in result:
            result.append(source)
    return result


def _watchlist_refs(item: dict[str, Any], sources: list[str]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    raw_refs = item.get("watchlist_refs")
    if isinstance(raw_refs, list):
        for raw_ref in raw_refs:
            if not isinstance(raw_ref, dict):
                continue
            group_name = str(raw_ref.get("group_name") or "").strip()
            if not group_name:
                continue
            refs.append(
                {
                    "group_name": group_name,
                    "group_order": raw_ref.get("group_order"),
                    "security_order": raw_ref.get("security_order"),
                    "source": f"watchlist:{group_name}",
                }
            )
    if refs:
        return refs

    for index, source in enumerate(sources):
        if not source.startswith("watchlist:"):
            continue
        group_name = source[len("watchlist:") :].strip()
        refs.append(
            {
                "group_name": group_name,
                "group_order": None,
                "security_order": None,
                "source": source,
            }
        )
    return refs


def _skipped_item(
    index: int,
    item: dict[str, Any],
    reason: str,
    *,
    error: str | None = None,
) -> dict[str, Any]:
    skipped = {
        "index": index,
        "reason": reason,
        "code": item.get("code"),
        "name": item.get("name"),
        "market_data_ticker": item.get("market_data_ticker"),
        "mapping_status": item.get("mapping_status"),
        "sources": _source_values(item.get("sources")),
    }
    if error:
        skipped["error"] = error
    return _json_safe(skipped)


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return str(value)
