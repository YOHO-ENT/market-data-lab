"""Build compact technical snapshots from cached price history."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd

from market_data_lab.indicators.technical import clean, compute_indicators, prepare_history
from market_data_lab.models import normalize_ticker


def build_snapshot(
    ticker: str,
    df: pd.DataFrame,
    *,
    benchmark_df: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Return a deterministic technical snapshot for one ticker."""

    normalized = normalize_ticker(ticker)
    hist = prepare_history(df)
    if hist.empty:
        return _unavailable_snapshot(normalized, "history unavailable")

    indicators = compute_indicators(hist, benchmark_df=benchmark_df)
    as_of = str(pd.to_datetime(hist["date"].iloc[-1]).date())
    currency = str(hist["currency"].dropna().iloc[-1]) if "currency" in hist and not hist["currency"].dropna().empty else "unavailable"
    warnings = list(indicators.pop("warnings", []))
    if len(hist) < 200:
        warnings.append(f"only {len(hist)} trading days available; MA200 may be unavailable")

    snapshot = {
        "ticker": normalized,
        "as_of": as_of,
        "currency": currency,
        **indicators,
        "data_quality": {
            "status": "ok" if not warnings else "partial",
            "warnings": warnings,
            "source": "parquet",
            "rows": len(hist),
            "as_of": as_of,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    }
    return clean(snapshot)


def _unavailable_snapshot(ticker: str, warning: str) -> dict[str, Any]:
    return {
        "ticker": ticker,
        "as_of": datetime.now(timezone.utc).date().isoformat(),
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
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    }
