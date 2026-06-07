from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from market_data_lab.fetchers import PRICE_COLUMNS, fetch_price_history, normalize_price_history
from market_data_lab.models import normalize_ticker
from market_data_lab import services
from market_data_lab.storage import ParquetPriceStore


class FakeYFinanceModule:
    def __init__(self, history: pd.DataFrame, currency: str = "USD") -> None:
        self.history = history
        self.calls: list[tuple[str, dict]] = []
        self.currency = currency

    def Ticker(self, ticker: str):
        module = self

        class FakeTicker:
            fast_info = {"currency": module.currency}

            def history(self, **kwargs):
                module.calls.append((ticker, kwargs))
                return module.history

        return FakeTicker()


class FailingProvider:
    def __call__(self, ticker: str, *, start=None, period=None):
        raise RuntimeError("yfinance unavailable")


def yfinance_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Open": [100.0, 102.0],
            "High": [110.0, 112.0],
            "Low": [98.0, 101.0],
            "Close": [105.0, 108.0],
            "Adj Close": [104.5, 107.5],
            "Volume": [1000, 1200],
            "Dividends": [0.0, 0.25],
            "Stock Splits": [0.0, 0.0],
        },
        index=pd.to_datetime(["2024-01-02", "2024-01-03"]).rename("Date"),
    )


def standard_frame(dates: list[str], closes: list[float] | None = None) -> pd.DataFrame:
    closes = closes or [10.0 + index for index, _ in enumerate(dates)]
    fetched_at = pd.Timestamp("2024-01-10T00:00:00Z").isoformat()
    return pd.DataFrame(
        {
            "date": pd.to_datetime(dates),
            "ticker": "AAPL",
            "open": closes,
            "high": [value + 1 for value in closes],
            "low": [value - 1 for value in closes],
            "close": closes,
            "adj_close": closes,
            "volume": [100] * len(dates),
            "dividends": [0.0] * len(dates),
            "stock_splits": [0.0] * len(dates),
            "currency": "USD",
            "source": "test",
            "fetched_at": [fetched_at] * len(dates),
        }
    )


def test_normalize_ticker_uppercases_and_preserves_suffixes() -> None:
    assert normalize_ticker(" aapl ") == "AAPL"
    assert normalize_ticker("005930.ks") == "005930.KS"
    assert normalize_ticker("0700.hk") == "0700.HK"
    assert normalize_ticker("7203.t") == "7203.T"
    assert normalize_ticker("bhp.ax") == "BHP.AX"

    with pytest.raises(ValueError):
        normalize_ticker(" ")


def test_normalize_price_history_returns_standard_daily_fields() -> None:
    result = normalize_price_history(yfinance_frame(), "aapl", currency="USD")

    assert list(result.columns) == PRICE_COLUMNS
    assert result["ticker"].tolist() == ["AAPL", "AAPL"]
    assert result["date"].astype(str).tolist() == ["2024-01-02", "2024-01-03"]
    assert result["open"].tolist() == [100.0, 102.0]
    assert result["adj_close"].tolist() == [104.5, 107.5]
    assert result["dividends"].tolist() == [0.0, 0.25]
    assert result["stock_splits"].tolist() == [0.0, 0.0]
    assert result["currency"].tolist() == ["USD", "USD"]
    assert result["source"].tolist() == ["yfinance", "yfinance"]


def test_fetch_price_history_uses_yfinance_contract_and_default_period(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_yf = FakeYFinanceModule(yfinance_frame(), currency="USD")
    monkeypatch.setitem(sys.modules, "yfinance", fake_yf)

    result = fetch_price_history("msft")

    assert result["ticker"].tolist() == ["MSFT", "MSFT"]
    assert fake_yf.calls[0][0] == "MSFT"
    assert fake_yf.calls[0][1]["period"] == "5y"
    assert fake_yf.calls[0][1]["interval"] == "1d"


def test_parquet_store_writes_reads_deduped_sorted_dates(tmp_path: Path) -> None:
    store = ParquetPriceStore(tmp_path)
    frame = standard_frame(["2024-01-03", "2024-01-01", "2024-01-03"], closes=[30.0, 10.0, 31.0])

    path = store.write("aapl", frame)
    read = store.read("AAPL")

    assert path.exists()
    assert store.exists("aapl")
    assert read["date"].astype(str).tolist() == ["2024-01-01", "2024-01-03"]
    assert read["close"].tolist() == [10.0, 31.0]


def test_incremental_refresh_only_fetches_after_cached_max_date(tmp_path: Path) -> None:
    store = ParquetPriceStore(tmp_path)
    store.write("aapl", standard_frame(["2024-01-01", "2024-01-02"], closes=[10.0, 20.0]))

    class IncrementalProvider:
        def __init__(self) -> None:
            self.start = None

        def __call__(self, ticker: str, *, start=None, period=None):
            self.start = start
            return standard_frame(["2024-01-03"], closes=[30.0])

    provider = IncrementalProvider()
    refreshed, error = store.refresh("aapl", provider)

    assert error is None
    assert provider.start == "2024-01-03"
    assert refreshed["date"].astype(str).tolist() == ["2024-01-01", "2024-01-02", "2024-01-03"]
    assert refreshed["close"].tolist() == [10.0, 20.0, 30.0]


def test_incremental_refresh_keeps_existing_cache_when_yfinance_fails(tmp_path: Path) -> None:
    store = ParquetPriceStore(tmp_path)
    store.write("aapl", standard_frame(["2024-01-01"], closes=[10.0]))
    cached = store.read("aapl")

    refreshed, error = store.refresh("aapl", FailingProvider())

    assert error == "yfinance unavailable"
    pd.testing.assert_frame_equal(refreshed, cached)
    pd.testing.assert_frame_equal(store.read("aapl"), cached)


def test_incremental_refresh_returns_error_when_initial_fetch_fails(tmp_path: Path) -> None:
    store = ParquetPriceStore(tmp_path)

    refreshed, error = store.refresh("aapl", FailingProvider())

    assert refreshed.empty
    assert error == "yfinance unavailable"


def test_refresh_history_reports_stale_when_provider_fails_with_existing_cache(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    store = ParquetPriceStore(tmp_path)
    store.write("aapl", standard_frame(["2024-01-01"], closes=[10.0]))
    monkeypatch.setattr(services, "_store", lambda: store)
    monkeypatch.setattr(services, "_fetcher", lambda: FailingProvider())
    monkeypatch.setattr(services, "REFRESH_RUN_DIR", tmp_path / "runs" / "refresh")
    monkeypatch.setattr(services, "ensure_data_dirs", lambda: None)

    result = services.refresh_history(["aapl"])

    assert result.status == "partial"
    assert result.succeeded == 1
    assert result.failed == 0
    assert result.results[0].ticker == "AAPL"
    assert result.results[0].status == "stale"
    assert result.results[0].rows == 1
    assert store.read("AAPL")["close"].tolist() == [10.0]
