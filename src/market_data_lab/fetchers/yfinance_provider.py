"""yfinance-backed daily OHLCV provider."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd

from market_data_lab.config import DEFAULT_INTERVAL, DEFAULT_PERIOD
from market_data_lab.models import normalize_ticker

PRICE_COLUMNS = [
    "date",
    "ticker",
    "open",
    "high",
    "low",
    "close",
    "adj_close",
    "volume",
    "dividends",
    "stock_splits",
    "currency",
    "source",
    "fetched_at",
]


def fetch_price_history(
    ticker: str,
    *,
    period: str = DEFAULT_PERIOD,
    start: str | None = None,
) -> pd.DataFrame:
    """Fetch daily OHLCV from yfinance and return the standard local schema."""

    normalized = normalize_ticker(ticker)
    import yfinance as yf

    yf_ticker = yf.Ticker(normalized)
    kwargs: dict[str, Any] = {
        "interval": DEFAULT_INTERVAL,
        "auto_adjust": False,
        "actions": True,
    }
    if start:
        kwargs["start"] = start
    else:
        kwargs["period"] = period

    history = yf_ticker.history(**kwargs)
    currency = _currency(yf_ticker)
    return normalize_price_history(history, normalized, currency=currency)


def normalize_price_history(
    history: pd.DataFrame,
    ticker: str,
    *,
    currency: str | None = None,
    source: str = "yfinance",
) -> pd.DataFrame:
    """Normalize provider output into the canonical Parquet schema."""

    normalized = normalize_ticker(ticker)
    if not isinstance(history, pd.DataFrame) or history.empty:
        return pd.DataFrame(columns=PRICE_COLUMNS)

    df = history.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [
            str(col[0] if col[0] else col[-1]).strip()
            for col in df.columns.to_flat_index()
        ]

    df = df.reset_index()
    date_column = next((col for col in df.columns if str(col).lower() in {"date", "datetime"}), df.columns[0])
    fetched_at = datetime.now(timezone.utc).isoformat()

    result = pd.DataFrame({
        "date": pd.to_datetime(df[date_column], utc=True, errors="coerce").dt.date,
        "ticker": normalized,
        "open": _numeric_column(df, "Open"),
        "high": _numeric_column(df, "High"),
        "low": _numeric_column(df, "Low"),
        "close": _numeric_column(df, "Close"),
        "adj_close": _numeric_column(df, "Adj Close"),
        "volume": _numeric_column(df, "Volume"),
        "dividends": _numeric_column(df, "Dividends"),
        "stock_splits": _numeric_column(df, "Stock Splits"),
        "currency": currency or "unavailable",
        "source": source,
        "fetched_at": fetched_at,
    })
    if result["adj_close"].isna().all():
        result["adj_close"] = result["close"]
    result = result.dropna(subset=["date", "close"])
    return result[PRICE_COLUMNS].sort_values("date").drop_duplicates("date", keep="last").reset_index(drop=True)


def empty_price_history() -> pd.DataFrame:
    """Return an empty DataFrame with the canonical schema."""

    return pd.DataFrame(columns=PRICE_COLUMNS)


def _numeric_column(df: pd.DataFrame, name: str) -> pd.Series:
    if name not in df.columns:
        return pd.Series([pd.NA] * len(df), index=df.index, dtype="Float64")
    return pd.to_numeric(df[name], errors="coerce")


def _currency(ticker: Any) -> str | None:
    for attr in ("fast_info", "info"):
        try:
            info = getattr(ticker, attr, None)
            if isinstance(info, dict):
                value = info.get("currency")
            else:
                value = getattr(info, "currency", None)
            if value:
                return str(value)
        except Exception:
            continue
    return None
