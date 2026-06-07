"""Parquet storage for local price history."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import pandas as pd

from market_data_lab.config import DEFAULT_PERIOD, PRICE_HISTORY_DIR
from market_data_lab.fetchers.yfinance_provider import PRICE_COLUMNS, empty_price_history
from market_data_lab.models import normalize_ticker

PriceFetcher = Callable[..., pd.DataFrame]


class ParquetPriceStore:
    """Read/write one Parquet file per ticker."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or PRICE_HISTORY_DIR
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, ticker: str) -> Path:
        safe = normalize_ticker(ticker).replace("/", "_")
        return self.root / f"{safe}.parquet"

    def exists(self, ticker: str) -> bool:
        return self.path_for(ticker).exists()

    def read(self, ticker: str) -> pd.DataFrame:
        path = self.path_for(ticker)
        if not path.exists():
            raise FileNotFoundError(f"No cached price history for {normalize_ticker(ticker)}")
        df = pd.read_parquet(path)
        return self._normalize_cached(df, normalize_ticker(ticker))

    def write(self, ticker: str, df: pd.DataFrame) -> Path:
        normalized = self._normalize_cached(df, normalize_ticker(ticker))
        path = self.path_for(ticker)
        path.parent.mkdir(parents=True, exist_ok=True)
        normalized.to_parquet(path, index=False)
        return path

    def refresh(
        self,
        ticker: str,
        fetcher: PriceFetcher,
        *,
        period: str = DEFAULT_PERIOD,
        force: bool = False,
    ) -> tuple[pd.DataFrame, str | None]:
        """Refresh cached data, preserving stale cache on provider failure."""

        normalized = normalize_ticker(ticker)
        cached = None if force else self._read_optional(normalized)
        start = None
        if cached is not None and not cached.empty:
            last_date = pd.to_datetime(cached["date"]).max()
            start = (last_date + pd.Timedelta(days=1)).date().isoformat()

        try:
            fresh = fetcher(normalized, period=period, start=start)
        except Exception as exc:
            if cached is not None:
                return cached, str(exc)
            return empty_price_history(), str(exc)

        fresh = self._normalize_cached(fresh, normalized)
        if cached is not None and not cached.empty:
            if fresh.empty:
                return cached, None
            combined = pd.concat([cached, fresh], ignore_index=True)
        else:
            combined = fresh

        combined = self._normalize_cached(combined, normalized)
        if not combined.empty:
            self.write(normalized, combined)
        return combined, None if not combined.empty else "history unavailable"

    def _read_optional(self, ticker: str) -> pd.DataFrame | None:
        try:
            return self.read(ticker)
        except FileNotFoundError:
            return None

    @staticmethod
    def _normalize_cached(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
        if not isinstance(df, pd.DataFrame) or df.empty:
            return empty_price_history()
        normalized = df.copy()
        for column in PRICE_COLUMNS:
            if column not in normalized.columns:
                normalized[column] = pd.NA
        normalized["ticker"] = ticker
        normalized["date"] = pd.to_datetime(normalized["date"], errors="coerce").dt.date
        normalized = normalized.dropna(subset=["date", "close"])
        normalized = normalized[PRICE_COLUMNS]
        normalized = normalized.sort_values("date").drop_duplicates("date", keep="last")
        return normalized.reset_index(drop=True)
