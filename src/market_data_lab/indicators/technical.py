"""Deterministic technical indicators from daily OHLCV data."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

import pandas as pd


def compute_indicators(
    df: pd.DataFrame,
    *,
    benchmark_df: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Compute V1 technical indicators from a canonical price DataFrame."""

    hist = prepare_history(df)
    if hist.empty or "close" not in hist.columns:
        return unavailable_indicators("history unavailable")

    close = hist["close"]
    high = hist.get("high", close)
    low = hist.get("low", close)
    volume = hist.get("volume", pd.Series([pd.NA] * len(hist), index=hist.index))
    return_prices = return_price_series(hist)
    price = _finite(close.iloc[-1])
    if price is None:
        return unavailable_indicators("latest price unavailable")

    ma20 = rolling_last(close, 20)
    ma50 = rolling_last(close, 50)
    ma200 = rolling_last(close, 200)
    avg_volume_20d = rolling_last(volume, 20)
    latest_volume = _finite(volume.iloc[-1]) if len(volume) else None
    relative_volume = _ratio(latest_volume, avg_volume_20d)
    week52_high = _finite(high.tail(252).max())
    week52_low = _finite(low.tail(252).min())
    support_levels, resistance_levels = support_resistance(hist, price)

    result = {
        "price": _round_price(price),
        "ma20": _round_price(ma20),
        "ma50": _round_price(ma50),
        "ma200": _round_price(ma200),
        "distance_from_ma20": _pct_distance(price, ma20),
        "distance_from_ma50": _pct_distance(price, ma50),
        "distance_from_ma200": _pct_distance(price, ma200),
        "rsi14": _round(rsi(close, 14), 2),
        "atr14": _round_price(atr(high, low, close, 14)),
        "return_1m": _period_return(return_prices, 21),
        "return_3m": _period_return(return_prices, 63),
        "return_6m": _period_return(return_prices, 126),
        "return_ytd": _ytd_return(hist, return_prices),
        "volatility_20d": volatility(return_prices, 20),
        "volatility_60d": volatility(return_prices, 60),
        "beta_vs_spy": beta_vs_benchmark(hist, benchmark_df),
        "max_drawdown_6m": max_drawdown(return_prices, 126),
        "max_drawdown_1y": max_drawdown(return_prices, 252),
        "week52_high": _round_price(week52_high),
        "week52_low": _round_price(week52_low),
        "week52_position": _week52_position(price, week52_high, week52_low),
        "distance_from_52w_high": _pct_distance(price, week52_high),
        "distance_from_52w_low": _pct_distance(price, week52_low),
        "latest_gap_pct": latest_gap_pct(hist),
        "liquidity_score": liquidity_score(close, volume),
        "trend_score": trend_score(price, ma20, ma50, ma200),
        "support_levels": support_levels,
        "resistance_levels": resistance_levels,
        "trend": trend(price, ma20, ma50, ma200),
        "breakout_status": breakout_status(price, support_levels, resistance_levels, relative_volume),
        "relative_strength_vs_spy": relative_strength(return_prices, benchmark_df),
        "volume_signal": {
            "status": volume_status(relative_volume),
            "latest_volume": _int_or_none(latest_volume),
            "avg_20d": _int_or_none(avg_volume_20d),
            "ratio": _round(relative_volume, 2),
        },
    }
    return clean(result)


def prepare_history(df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame()
    hist = df.copy()
    hist["date"] = pd.to_datetime(hist["date"], errors="coerce")
    hist = hist.dropna(subset=["date"])
    hist = hist.sort_values("date").drop_duplicates("date", keep="last")
    for column in ("open", "high", "low", "close", "adj_close", "volume"):
        if column in hist.columns:
            hist[column] = pd.to_numeric(hist[column], errors="coerce")
    return hist.reset_index(drop=True)


def rolling_last(series: pd.Series, window: int) -> float | None:
    if len(series.dropna()) < window:
        return None
    return _finite(series.rolling(window).mean().iloc[-1])


def rsi(close: pd.Series, window: int = 14) -> float | None:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(window).mean()
    loss = (-delta.clip(upper=0)).rolling(window).mean()
    avg_gain = _finite(gain.iloc[-1])
    avg_loss = _finite(loss.iloc[-1])
    if avg_gain is None or avg_loss is None:
        return None
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return _finite(100 - (100 / (1 + rs)))


def atr(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> float | None:
    previous_close = close.shift(1)
    true_range = pd.concat([
        high - low,
        (high - previous_close).abs(),
        (low - previous_close).abs(),
    ], axis=1).max(axis=1)
    if len(true_range.dropna()) < window:
        return None
    return _finite(true_range.rolling(window).mean().iloc[-1])


def support_resistance(hist: pd.DataFrame, price: float, window: int = 3) -> tuple[list[float], list[float]]:
    recent = hist.tail(126).reset_index(drop=True)
    lows = recent["low"] if "low" in recent else recent["close"]
    highs = recent["high"] if "high" in recent else recent["close"]
    swing_lows: list[float] = []
    swing_highs: list[float] = []
    for idx in range(window, len(recent) - window):
        low = _finite(lows.iloc[idx])
        high = _finite(highs.iloc[idx])
        if low is not None and low == _finite(lows.iloc[idx - window:idx + window + 1].min()):
            swing_lows.append(low)
        if high is not None and high == _finite(highs.iloc[idx - window:idx + window + 1].max()):
            swing_highs.append(high)
    supports = sorted({round(v, 4) for v in swing_lows if v <= price}, key=lambda v: abs(price - v))[:3]
    resistances = sorted({round(v, 4) for v in swing_highs if v >= price}, key=lambda v: abs(price - v))[:3]
    if not supports and not lows.dropna().empty:
        supports = [_round_price(lows.tail(126).min())]
    if not resistances and not highs.dropna().empty:
        resistances = [_round_price(highs.tail(126).max())]
    return clean(supports), clean(resistances)


def trend(price: float, ma20: float | None, ma50: float | None, ma200: float | None) -> str:
    if ma20 and ma50 and ma200 and price > ma20 > ma50 > ma200:
        return "bullish"
    if ma50 and ma200 and price > ma50 and ma50 >= ma200:
        return "constructive"
    if ma50 and ma200 and price < ma50 and ma50 < ma200:
        return "bearish"
    return "neutral"


def breakout_status(
    price: float,
    supports: list[float],
    resistances: list[float],
    relative_volume: float | None,
) -> str:
    high_volume = relative_volume is not None and relative_volume > 1.2
    nearest_resistance = resistances[0] if resistances else None
    nearest_support = supports[0] if supports else None
    if nearest_resistance and price > nearest_resistance and high_volume:
        return "breakout"
    if nearest_support and price < nearest_support and high_volume:
        return "breakdown"
    if nearest_resistance and 0 <= (nearest_resistance - price) / nearest_resistance <= 0.03:
        return "near_breakout"
    if nearest_support and 0 <= (price - nearest_support) / nearest_support <= 0.03:
        return "near_support"
    return "range_bound"


def volume_status(relative_volume: float | None) -> str:
    if relative_volume is None:
        return "unavailable"
    if relative_volume > 1.2:
        return "above_average"
    if relative_volume < 0.8:
        return "below_average"
    return "normal"


def relative_strength(close: pd.Series, benchmark_df: pd.DataFrame | None) -> dict[str, Any]:
    if benchmark_df is None or benchmark_df.empty:
        return {"benchmark": "SPY", "status": "unavailable", "periods": {}}
    bench = prepare_history(benchmark_df)
    if bench.empty or "close" not in bench:
        return {"benchmark": "SPY", "status": "unavailable", "periods": {}}
    benchmark_prices = return_price_series(bench)
    periods = {}
    spreads = []
    for label, days in (("1m", 21), ("3m", 63), ("6m", 126)):
        own = _period_return(close, days)
        other = _period_return(benchmark_prices, days)
        spread = None if own is None or other is None else own - other
        periods[label] = {"return": own, "benchmark_return": other, "spread": spread}
        if spread is not None:
            spreads.append(spread)
    avg = sum(spreads) / len(spreads) if spreads else None
    if avg is None:
        status = "unavailable"
    elif avg > 0.03:
        status = "outperforming"
    elif avg < -0.03:
        status = "underperforming"
    else:
        status = "in_line"
    return clean({"benchmark": "SPY", "status": status, "periods": periods})


def return_price_series(hist: pd.DataFrame) -> pd.Series:
    """Return adjusted closes when usable, otherwise close prices."""

    close = _price_series(hist["close"]) if "close" in hist else pd.Series(dtype=float)
    if "adj_close" not in hist:
        return close
    adjusted = _price_series(hist["adj_close"])
    return adjusted if _usable_price_series(adjusted, len(close.dropna())) else close


def volatility(prices: pd.Series, window: int) -> float | None:
    returns = daily_returns(prices)
    if len(returns) < window:
        return None
    std_dev = _finite(returns.tail(window).std())
    if std_dev is None:
        return None
    return _round(std_dev * math.sqrt(252), 4)


def beta_vs_benchmark(
    hist: pd.DataFrame,
    benchmark_df: pd.DataFrame | None,
    *,
    window: int = 252,
    min_periods: int = 60,
) -> float | None:
    if benchmark_df is None or benchmark_df.empty:
        return None
    bench = prepare_history(benchmark_df)
    if bench.empty or "close" not in bench:
        return None

    own_returns = daily_returns(_dated_return_prices(hist))
    benchmark_returns = daily_returns(_dated_return_prices(bench))
    aligned = pd.concat({"own": own_returns, "benchmark": benchmark_returns}, axis=1).dropna().tail(window)
    if len(aligned) < min_periods:
        return None

    benchmark_variance = _finite(aligned["benchmark"].var())
    if benchmark_variance in (None, 0):
        return None
    beta = aligned["own"].cov(aligned["benchmark"]) / benchmark_variance
    return _round(beta, 4)


def max_drawdown(prices: pd.Series, days: int) -> float | None:
    values = _price_series(prices).dropna().tail(days)
    if len(values) < 2:
        return None
    running_high = values.cummax()
    drawdowns = (values / running_high) - 1
    return _round(drawdowns.min(), 4)


def latest_gap_pct(hist: pd.DataFrame) -> float | None:
    if "open" not in hist or "close" not in hist or len(hist) < 2:
        return None
    latest_open = _finite(hist["open"].iloc[-1])
    previous_close = _last_finite(hist["close"].iloc[:-1])
    if latest_open is None or previous_close is None:
        return None
    return _pct(latest_open, previous_close)


def liquidity_score(close: pd.Series, volume: pd.Series, window: int = 20) -> float | None:
    prices = _price_series(close)
    volumes = _positive_series(volume)
    dollar_volume = (prices * volumes).dropna().tail(window)
    if dollar_volume.empty:
        return None
    average_dollar_volume = _finite(dollar_volume.mean())
    if average_dollar_volume is None or average_dollar_volume <= 0:
        return None
    score = ((math.log10(average_dollar_volume) - 5) / 5) * 100
    return _round(min(100, max(0, score)), 1)


def trend_score(price: float, ma20: float | None, ma50: float | None, ma200: float | None) -> float | None:
    checks = []
    if ma20:
        checks.append(price > ma20)
    if ma50:
        checks.append(price > ma50)
    if ma200:
        checks.append(price > ma200)
    if ma20 and ma50:
        checks.append(ma20 > ma50)
    if ma50 and ma200:
        checks.append(ma50 > ma200)
    if not checks:
        return None
    return _round((sum(1 for passed in checks if passed) / len(checks)) * 100, 1)


def unavailable_indicators(reason: str) -> dict[str, Any]:
    return {
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
        "warnings": [reason],
    }


def clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clean(v) for v in value]
    if isinstance(value, tuple):
        return [clean(v) for v in value]
    if isinstance(value, (pd.Timestamp, datetime)):
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
            return clean(value.item())
        except Exception:
            return str(value)
    return value


def _period_return(close: pd.Series, days: int) -> float | None:
    values = close.dropna()
    if len(values) <= days:
        return None
    return _pct(values.iloc[-1], values.iloc[-days - 1])


def _ytd_return(hist: pd.DataFrame, prices: pd.Series | None = None) -> float | None:
    prices = prices if prices is not None else hist["close"]
    current_year = pd.to_datetime(hist["date"].iloc[-1]).year
    ytd = hist[pd.to_datetime(hist["date"]).dt.year == current_year]
    if ytd.empty:
        return None
    ytd_prices = prices.loc[ytd.index].dropna()
    if ytd_prices.empty:
        return None
    return _pct(prices.dropna().iloc[-1], ytd_prices.iloc[0])


def _week52_position(price: float, high: float, low: float) -> float | None:
    if not high or not low or high == low:
        return None
    return _round((price - low) / (high - low), 4)


def _pct(current: float, previous: float) -> float | None:
    current = _finite(current)
    previous = _finite(previous)
    if current is None or previous in (None, 0):
        return None
    return _round((current / previous) - 1, 4)


def _pct_distance(price: float, ma: float | None) -> float | None:
    if ma in (None, 0):
        return None
    return _round((price - ma) / ma, 4)


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def daily_returns(prices: pd.Series) -> pd.Series:
    values = _price_series(prices).dropna()
    returns = values.pct_change(fill_method=None)
    return _clean_numeric_series(returns).dropna()


def _dated_return_prices(hist: pd.DataFrame) -> pd.Series:
    dates = pd.to_datetime(hist["date"], errors="coerce").dt.date
    prices = return_price_series(hist)
    series = pd.Series(prices.to_numpy(), index=pd.Index(dates))
    return series[pd.notna(series.index)].sort_index()


def _usable_price_series(series: pd.Series, reference_count: int | None = None) -> bool:
    values = series.dropna()
    required = 2
    if reference_count is not None and reference_count > required:
        required = max(required, math.ceil(reference_count * 0.9))
    return len(values) >= required and _finite(values.iloc[-1]) is not None


def _price_series(series: pd.Series) -> pd.Series:
    return _positive_series(series)


def _positive_series(series: pd.Series) -> pd.Series:
    numeric = _clean_numeric_series(series)
    return numeric.where(numeric > 0)


def _clean_numeric_series(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    return numeric.where(numeric.map(lambda value: _finite(value) is not None))


def _last_finite(series: pd.Series) -> float | None:
    for value in reversed(series.tolist()):
        finite = _finite(value)
        if finite is not None:
            return finite
    return None


def _finite(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _round(value: Any, digits: int) -> float | None:
    value = _finite(value)
    return round(value, digits) if value is not None else None


def _round_price(value: Any) -> float | None:
    value = _finite(value)
    if value is None:
        return None
    return round(value, 4) if abs(value) < 10 else round(value, 2)


def _int_or_none(value: Any) -> int | None:
    value = _finite(value)
    return int(value) if value is not None else None
