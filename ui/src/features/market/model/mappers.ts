import type { MarketStatus, TechnicalSnapshot } from "./types";

export function unavailableStatus(error?: string): MarketStatus {
  return {
    status: "unavailable",
    price_history_files: 0,
    cached_tickers: [],
    latest_as_of: null,
    stale_count: 0,
    stale_tickers: [],
    snapshots: 0,
    snapshot_tickers: [],
    entries: [],
    error,
  };
}

export function unavailableSnapshot(ticker: string, error?: string): TechnicalSnapshot {
  return {
    ticker,
    as_of: null,
    currency: "unavailable",
    price: null,
    ma20: null,
    ma50: null,
    ma200: null,
    distance_from_ma20: null,
    distance_from_ma50: null,
    distance_from_ma200: null,
    rsi14: null,
    atr14: null,
    return_1m: null,
    return_3m: null,
    return_6m: null,
    return_ytd: null,
    week52_high: null,
    week52_low: null,
    week52_position: null,
    support_levels: [],
    resistance_levels: [],
    trend: "unavailable",
    breakout_status: "unavailable",
    relative_strength_vs_spy: {
      benchmark: "SPY",
      status: "unavailable",
      periods: {},
    },
    volume_signal: {
      status: "unavailable",
    },
    data_quality: {
      status: "unavailable",
      warnings: error ? [error] : [],
    },
  };
}
