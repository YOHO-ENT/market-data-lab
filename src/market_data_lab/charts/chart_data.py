"""Build ECharts-ready chart JSON from cached price history."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd

from market_data_lab.config import SUPPORTED_CHART_RANGES
from market_data_lab.indicators.technical import clean, compute_indicators, prepare_history
from market_data_lab.models import normalize_ticker


def build_chart(
    ticker: str,
    df: pd.DataFrame,
    *,
    range_name: str = "1y",
) -> dict[str, Any] | None:
    """Return chart-ready technical series, or None when not displayable."""

    normalized = normalize_ticker(ticker)
    hist = prepare_history(df)
    if hist.empty or len(hist) < 30:
        return None

    days = SUPPORTED_CHART_RANGES.get(range_name, SUPPORTED_CHART_RANGES["1y"])
    chart_hist = hist.tail(days).reset_index(drop=True)
    indicators = compute_indicators(hist)
    close = hist["close"]
    dates = chart_hist["date"].reset_index(drop=True)
    ma20 = close.rolling(20).mean().tail(len(chart_hist)).reset_index(drop=True)
    ma50 = close.rolling(50).mean().tail(len(chart_hist)).reset_index(drop=True)
    ma200 = close.rolling(200).mean().tail(len(chart_hist)).reset_index(drop=True)
    as_of = str(pd.to_datetime(hist["date"].iloc[-1]).date())
    currency = str(hist["currency"].dropna().iloc[-1]) if "currency" in hist and not hist["currency"].dropna().empty else "unavailable"

    chart = {
        "ticker": normalized,
        "as_of": as_of,
        "currency": currency,
        "has_image": True,
        "points": [_point(chart_hist.iloc[idx]) for idx in range(len(chart_hist))],
        "ma20": _series_points(dates, ma20),
        "ma50": _series_points(dates, ma50),
        "ma200": _series_points(dates, ma200),
        "support_levels": indicators.get("support_levels", []),
        "resistance_levels": indicators.get("resistance_levels", []),
        "data_quality": {
            "status": "ok",
            "warnings": [],
            "source": "parquet",
            "rows": len(chart_hist),
            "as_of": as_of,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    }
    return clean(chart)


def _point(row: pd.Series) -> dict[str, Any]:
    close = _float(row.get("close"))
    return {
        "date": str(pd.to_datetime(row.get("date")).date()),
        "open": _float(row.get("open")) or close,
        "high": _float(row.get("high")) or close,
        "low": _float(row.get("low")) or close,
        "close": close,
        "volume": _int(row.get("volume")),
    }


def _series_points(dates: pd.Series, series: pd.Series) -> list[dict[str, Any]]:
    points = []
    for idx, value in enumerate(series):
        points.append({
            "date": str(pd.to_datetime(dates.iloc[idx]).date()),
            "value": _float(value),
        })
    return points


def _float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if pd.notna(result) else None


def _int(value: Any) -> int | None:
    value = _float(value)
    return int(value) if value is not None else None
