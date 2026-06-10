"""One-way sync from Market Data Lab universe to Firn watchlist.

The richer Firn shape is:

Market Data Lab keeps chart/cache groups plus optional metadata:

    groups:
      category_key: [...]
    group_meta:
      category_key:
        label: Human Label
        tags: [category_key]

Firn receives the richer watchlist shape:

    categories:
      category_key:
        label: Human Label
        tags: [category_key]
        tickers: [...]
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from market_data_lab.config import FIRN_WATCHLIST_PATH, UNIVERSE_PATH
from market_data_lab.models import normalize_ticker, normalize_tickers

DEFAULT_UNIVERSE_PATH = UNIVERSE_PATH
DEFAULT_FIRN_WATCHLIST_PATH = FIRN_WATCHLIST_PATH

_GROUP_RE = re.compile(r"[^a-z0-9_]+")


def sync_configs(
    *,
    prefer: str = "universe",
    universe_path: Path = DEFAULT_UNIVERSE_PATH,
    watchlist_path: Path | None = DEFAULT_FIRN_WATCHLIST_PATH,
) -> str:
    """Synchronize Lab universe to Firn watchlist and return ``"universe"``.

    Market Data Lab no longer accepts Firn as a source of truth. ``prefer`` is
    kept for old callers, but only ``"universe"`` is accepted to avoid an
    accidental Firn -> Lab overwrite.
    """

    universe_path = Path(universe_path)
    if prefer != "universe":
        raise ValueError("Market Data Lab only supports universe -> Firn watchlist sync")
    if not universe_path.exists():
        return "none"
    if watchlist_path is None:
        return "none"
    watchlist_path = Path(watchlist_path)
    sync_universe_to_watchlist(universe_path=universe_path, watchlist_path=watchlist_path)
    return "universe"


def sync_watchlist_to_universe(
    *,
    watchlist_path: Path | None = DEFAULT_FIRN_WATCHLIST_PATH,
    universe_path: Path = DEFAULT_UNIVERSE_PATH,
) -> None:
    """Legacy converter kept for tests/tools; runtime sync must not call this."""

    if watchlist_path is None:
        raise ValueError("FIRN_WATCHLIST_PATH is required for watchlist -> universe conversion")
    payload = _load_yaml(Path(watchlist_path))
    categories = normalize_watchlist_categories(payload.get("categories") or payload)
    groups: dict[str, list[str]] = {}
    group_meta: dict[str, dict[str, Any]] = {}
    for key, category in categories.items():
        tickers = normalize_tickers(category.get("tickers") or [])
        groups[key] = tickers
        group_meta[key] = {
            "label": category.get("label") or _label_from_key(key),
            "tags": _normalize_tags(category.get("tags"), key),
        }

    existing = _load_yaml(Path(universe_path)) if Path(universe_path).exists() else {}
    existing["groups"] = groups
    existing["group_meta"] = group_meta
    _write_yaml(Path(universe_path), existing)


def sync_universe_to_watchlist(
    *,
    universe_path: Path = DEFAULT_UNIVERSE_PATH,
    watchlist_path: Path | None = DEFAULT_FIRN_WATCHLIST_PATH,
) -> None:
    if watchlist_path is None:
        raise ValueError("FIRN_WATCHLIST_PATH is required for universe -> watchlist sync")
    universe = _load_yaml(Path(universe_path))
    existing = _load_yaml(Path(watchlist_path)) if Path(watchlist_path).exists() else {}
    existing_categories = existing.get("categories") or {}
    categories = universe_to_watchlist_categories(universe, existing_categories=existing_categories)

    _write_yaml(Path(watchlist_path), {"categories": categories})


def universe_to_watchlist_categories(
    universe: dict[str, Any],
    *,
    existing_categories: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Convert a Market Data Lab universe mapping to Firn watchlist categories."""

    groups = universe.get("groups") or {}
    group_meta = universe.get("group_meta") or {}
    existing_categories = existing_categories or {}

    categories: dict[str, dict[str, Any]] = {}
    for raw_key, raw_tickers in groups.items():
        key = _normalize_group_key(str(raw_key))
        meta = group_meta.get(raw_key) or group_meta.get(key) or {}
        previous = existing_categories.get(key) or existing_categories.get(raw_key) or {}
        categories[key] = {
            "label": meta.get("label") or previous.get("label") or _label_from_key(key),
            "tags": _normalize_tags(meta.get("tags") or previous.get("tags"), key),
            "tickers": normalize_tickers(_ticker_values(raw_tickers)),
        }
    return categories


def normalize_watchlist_categories(categories: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(categories, dict):
        raise ValueError("watchlist categories must be a mapping")

    normalized: dict[str, dict[str, Any]] = {}
    for raw_key, raw_category in categories.items():
        key = _normalize_group_key(str(raw_key))
        category = raw_category if isinstance(raw_category, dict) else {"tickers": raw_category}
        normalized[key] = {
            "label": str(category.get("label") or _label_from_key(key)),
            "tags": _normalize_tags(category.get("tags"), key),
            "tickers": normalize_tickers(_ticker_values(category.get("tickers") or [])),
        }
    return normalized


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML config must be a mapping: {path}")
    return data


def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, default_flow_style=False, allow_unicode=True),
        encoding="utf-8",
    )


def _ticker_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [normalize_ticker(value)]
    try:
        values = list(value)
    except TypeError as exc:
        raise ValueError("tickers must be a list") from exc
    return [str(ticker) for ticker in values]


def _normalize_tags(value: Any, fallback: str) -> list[str]:
    if value is None:
        return [fallback]
    if isinstance(value, str):
        candidates = [value]
    else:
        try:
            candidates = [str(item) for item in value]
        except TypeError:
            candidates = [fallback]
    tags: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        tag = candidate.strip().lower().replace(" ", "-")
        if tag and tag not in seen:
            seen.add(tag)
            tags.append(tag)
    return tags or [fallback]


def _normalize_group_key(key: str) -> str:
    normalized = _GROUP_RE.sub("_", key.strip().lower()).strip("_")
    if not normalized:
        raise ValueError("group key is required")
    return normalized


def _label_from_key(key: str) -> str:
    return key.replace("_", " ").replace("-", " ").title()
