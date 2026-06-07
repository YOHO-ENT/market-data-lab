from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from market_data_lab.charts import build_chart
from market_data_lab.indicators import compute_indicators
from market_data_lab.snapshots import build_snapshot

V13_INDICATOR_KEYS = {
    "volatility_20d",
    "volatility_60d",
    "beta_vs_spy",
    "max_drawdown_6m",
    "max_drawdown_1y",
    "distance_from_52w_high",
    "distance_from_52w_low",
    "latest_gap_pct",
    "liquidity_score",
    "trend_score",
}


def _history(*, rows: int = 260, slope: float = 0.18, volume_spike: bool = True) -> pd.DataFrame:
    end = pd.Timestamp.today().normalize()
    if end.weekday() >= 5:
        end = end - pd.offsets.BDay(1)
    dates = pd.bdate_range(end=end, periods=rows)
    values: list[float] = []
    for idx in range(rows):
        wave = 2.6 * math.sin(idx / 5.0)
        values.append(100.0 + idx * slope + wave)

    close = pd.Series(values, index=dates, dtype=float)
    high = close + 1.1
    low = close - 1.1
    volume = pd.Series([1_000_000 + (idx % 10) * 10_000 for idx in range(rows)], index=dates, dtype=float)
    if volume_spike:
        volume.iloc[-1] = 1_800_000

    return pd.DataFrame(
        {
            "date": dates,
            "ticker": "BSX",
            "open": close.values - 0.25,
            "high": high.values,
            "low": low.values,
            "close": close.values,
            "adj_close": close.values,
            "volume": volume.values,
            "dividends": [0.0] * rows,
            "stock_splits": [0.0] * rows,
            "currency": "USD",
            "source": "test",
            "fetched_at": [pd.Timestamp.now(tz="UTC").isoformat()] * rows,
        }
    )


def test_compute_indicators_calculates_v1_metric_set() -> None:
    indicators = compute_indicators(_history())

    assert V13_INDICATOR_KEYS.issubset(indicators)
    assert indicators["price"] is not None
    assert indicators["ma20"] is not None
    assert indicators["ma50"] is not None
    assert indicators["ma200"] is not None
    assert indicators["distance_from_ma20"] is not None
    assert 0 <= indicators["rsi14"] <= 100
    assert indicators["atr14"] > 0
    assert indicators["return_1m"] is not None
    assert indicators["return_3m"] is not None
    assert indicators["return_6m"] is not None
    assert indicators["return_ytd"] is not None
    assert indicators["volatility_20d"] >= 0
    assert indicators["volatility_60d"] >= 0
    assert indicators["beta_vs_spy"] is None
    assert -1 <= indicators["max_drawdown_6m"] <= 0
    assert -1 <= indicators["max_drawdown_1y"] <= 0
    assert indicators["week52_high"] >= indicators["week52_low"]
    assert 0 <= indicators["week52_position"] <= 1
    assert indicators["distance_from_52w_high"] <= 0
    assert indicators["distance_from_52w_low"] >= 0
    assert indicators["latest_gap_pct"] is not None
    assert 0 <= indicators["liquidity_score"] <= 100
    assert 0 <= indicators["trend_score"] <= 100
    assert indicators["support_levels"]
    assert indicators["resistance_levels"]
    assert indicators["trend"] in {"bullish", "constructive", "neutral", "bearish"}
    assert indicators["breakout_status"] in {
        "breakout",
        "near_breakout",
        "breakdown",
        "near_support",
        "range_bound",
    }
    assert indicators["volume_signal"]["status"] == "above_average"
    assert "NaN" not in json.dumps(indicators, allow_nan=False)


def test_compute_indicators_uses_benchmark_for_beta_when_available() -> None:
    indicators = compute_indicators(_history(slope=0.22), benchmark_df=_history(slope=0.05, volume_spike=False))

    assert indicators["beta_vs_spy"] is not None
    assert -5 <= indicators["beta_vs_spy"] <= 5
    assert indicators["relative_strength_vs_spy"]["benchmark"] == "SPY"
    assert indicators["relative_strength_vs_spy"]["status"] in {
        "outperforming",
        "underperforming",
        "in_line",
    }
    assert "NaN" not in json.dumps(indicators, allow_nan=False)


def test_return_indicators_prefer_adj_close_when_usable() -> None:
    history = _history(slope=0)
    history["open"] = 99.75
    history["high"] = 101.0
    history["low"] = 99.0
    history["close"] = 100.0
    history["adj_close"] = [50.0 + idx * 0.2 for idx in range(len(history))]

    indicators = compute_indicators(history)

    assert indicators["price"] == 100.0
    assert indicators["return_1m"] > 0
    assert indicators["return_3m"] > 0
    assert indicators["max_drawdown_6m"] == 0
    assert "NaN" not in json.dumps(indicators, allow_nan=False)


def test_return_indicators_fallback_to_close_when_adj_close_is_sparse() -> None:
    history = _history(slope=0.2)
    history["adj_close"] = pd.NA
    history.loc[len(history) - 1, "adj_close"] = history["close"].iloc[-1]

    indicators = compute_indicators(history)

    assert indicators["return_1m"] is not None
    assert indicators["return_3m"] is not None
    assert indicators["max_drawdown_1y"] is not None
    assert "NaN" not in json.dumps(indicators, allow_nan=False)


def test_build_snapshot_contains_required_fields_and_relative_strength() -> None:
    history = _history(slope=0.22)
    spy = _history(slope=0.05, volume_spike=False)

    snapshot = build_snapshot("bsx", history, benchmark_df=spy)

    expected_keys = {
        "ticker",
        "as_of",
        "price",
        "currency",
        "ma20",
        "ma50",
        "ma200",
        "distance_from_ma20",
        "distance_from_ma50",
        "distance_from_ma200",
        "rsi14",
        "atr14",
        "return_1m",
        "return_3m",
        "return_6m",
        "return_ytd",
        "volatility_20d",
        "volatility_60d",
        "beta_vs_spy",
        "max_drawdown_6m",
        "max_drawdown_1y",
        "week52_high",
        "week52_low",
        "week52_position",
        "distance_from_52w_high",
        "distance_from_52w_low",
        "latest_gap_pct",
        "liquidity_score",
        "trend_score",
        "support_levels",
        "resistance_levels",
        "trend",
        "breakout_status",
        "relative_strength_vs_spy",
        "volume_signal",
        "data_quality",
    }
    assert expected_keys.issubset(snapshot)
    assert snapshot["ticker"] == "BSX"
    assert snapshot["currency"] == "USD"
    assert snapshot["relative_strength_vs_spy"]["benchmark"] == "SPY"
    assert snapshot["beta_vs_spy"] is not None
    assert snapshot["volatility_20d"] >= 0
    assert snapshot["volatility_60d"] >= 0
    assert -1 <= snapshot["max_drawdown_6m"] <= 0
    assert -1 <= snapshot["max_drawdown_1y"] <= 0
    assert snapshot["distance_from_52w_high"] <= 0
    assert snapshot["distance_from_52w_low"] >= 0
    assert snapshot["latest_gap_pct"] is not None
    assert 0 <= snapshot["liquidity_score"] <= 100
    assert 0 <= snapshot["trend_score"] <= 100
    assert snapshot["data_quality"]["source"] == "parquet"
    assert "NaN" not in json.dumps(snapshot, allow_nan=False)


def test_build_snapshot_marks_relative_strength_unavailable_without_benchmark_df() -> None:
    snapshot = build_snapshot("BSX", _history())

    assert snapshot["relative_strength_vs_spy"] == {
        "benchmark": "SPY",
        "status": "unavailable",
        "periods": {},
    }
    assert snapshot["beta_vs_spy"] is None
    assert "NaN" not in json.dumps(snapshot, allow_nan=False)


def test_build_chart_returns_chart_ready_json() -> None:
    chart = build_chart("bsx", _history(), range_name="6mo")

    assert chart is not None
    assert chart["ticker"] == "BSX"
    assert chart["has_image"] is True
    assert len(chart["points"]) == 126
    assert len(chart["ma20"]) == 126
    assert len(chart["ma50"]) == 126
    assert len(chart["ma200"]) == 126
    assert chart["ma20"][0]["date"]
    assert chart["support_levels"]
    assert chart["resistance_levels"]
    assert chart["data_quality"]["status"] == "ok"
    assert "NaN" not in json.dumps(chart, allow_nan=False)


def test_missing_close_rows_are_dropped_without_nan_pollution() -> None:
    history = _history()
    history.loc[10, "close"] = None

    snapshot = build_snapshot("BSX", history)

    assert snapshot["data_quality"]["status"] == "ok"
    assert snapshot["price"] is not None
    assert "NaN" not in json.dumps(snapshot, allow_nan=False)
