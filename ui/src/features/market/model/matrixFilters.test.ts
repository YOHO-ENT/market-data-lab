import { describe, expect, it } from "vitest";

import {
  DEFAULT_MATRIX_FILTERS,
  filterAndSortSnapshots,
  getMatrixFilterOptions,
  type MatrixSortKey,
  type SortDirection,
} from "./matrixFilters";
import type { MarketStatus, TechnicalSnapshot } from "./types";

const baseStatus: MarketStatus = {
  status: "ok",
  price_history_files: 3,
  cached_tickers: ["AAPL", "BSX", "MSFT"],
  latest_as_of: "2026-06-05",
  stale_count: 0,
  stale_tickers: [],
  snapshots: 3,
  snapshot_tickers: ["AAPL", "BSX", "MSFT"],
  entries: [],
};

function makeSnapshot(
  overrides: Partial<TechnicalSnapshot> & Pick<TechnicalSnapshot, "ticker">,
): TechnicalSnapshot {
  const { data_quality, ticker, ...snapshotOverrides } = overrides;
  const baseSnapshot: TechnicalSnapshot = {
    ticker,
    as_of: "2026-06-05",
    currency: "USD",
    price: 100,
    ma20: 95,
    ma50: 90,
    ma200: 80,
    distance_from_ma20: 0.05,
    distance_from_ma50: 0.1,
    distance_from_ma200: 0.2,
    rsi14: 55,
    atr14: 2,
    return_1m: 0.02,
    return_3m: 0.05,
    return_6m: 0.07,
    return_ytd: 0.1,
    week52_high: 120,
    week52_low: 80,
    week52_position: 0.7,
    support_levels: [95],
    resistance_levels: [110],
    trend: "neutral",
    breakout_status: "range_bound",
    relative_strength_vs_spy: {
      benchmark: "SPY",
      status: "neutral",
      periods: {},
    },
    volume_signal: {
      status: "normal",
      ratio: 1,
    },
    data_quality: {
      status: "ok",
      warnings: [],
    },
  };

  return {
    ...baseSnapshot,
    ...snapshotOverrides,
    data_quality: {
      status: data_quality?.status || "ok",
      warnings: data_quality?.warnings || [],
    },
  };
}

const snapshots = [
  makeSnapshot({
    ticker: "AAPL",
    price: 307.3,
    trend: "bullish",
    breakout_status: "near_support",
    data_quality: { status: "ok", warnings: [] },
    volume_signal: { status: "normal", ratio: 0.89 },
  }),
  makeSnapshot({
    ticker: "BSX",
    price: 48.55,
    trend: "bearish",
    data_quality: { status: "partial", warnings: ["short history"] },
    volume_signal: { status: "elevated", ratio: 1.4 },
  }),
  makeSnapshot({
    ticker: "MSFT",
    price: null,
    trend: "constructive",
    data_quality: { status: "stale", warnings: [] },
    volume_signal: { status: "normal", ratio: 0.7 },
  }),
];

describe("matrix filters", () => {
  it("extracts optional group universes and falls back to cached tickers", () => {
    const options = getMatrixFilterOptions(snapshots, {
      ...baseStatus,
      groups: {
        "Mega Cap": ["AAPL", "MSFT"],
        Medtech: ["BSX"],
      },
    });

    expect(options.universes.map((option) => option.label)).toEqual([
      "All cached",
      "Mega Cap",
      "Medtech",
    ]);

    const fallback = getMatrixFilterOptions(snapshots, baseStatus);
    expect(fallback.universes).toHaveLength(1);
    expect(fallback.universes[0]).toMatchObject({
      id: "all",
      label: "All cached",
      tickers: ["AAPL", "BSX", "MSFT"],
    });
  });

  it("filters by search, trend, quality, and universe", () => {
    const options = getMatrixFilterOptions(snapshots, {
      ...baseStatus,
      groups: {
        Medtech: ["BSX"],
      },
    });

    const filtered = filterAndSortSnapshots(
      snapshots,
      {
        ...DEFAULT_MATRIX_FILTERS,
        search: "bs",
        trend: "bearish",
        quality: "partial",
        universeId: "groups:medtech",
      },
      options.universes,
    );

    expect(filtered.map((snapshot) => snapshot.ticker)).toEqual(["BSX"]);
  });

  it("sorts numerics in both directions with missing values last", () => {
    const options = getMatrixFilterOptions(snapshots, baseStatus);

    const ascending = filterAndSortSnapshots(
      snapshots,
      { ...DEFAULT_MATRIX_FILTERS, sortKey: "price", sortDirection: "asc" },
      options.universes,
    );
    expect(ascending.map((snapshot) => snapshot.ticker)).toEqual([
      "BSX",
      "AAPL",
      "MSFT",
    ]);

    const descending = filterAndSortSnapshots(
      snapshots,
      { ...DEFAULT_MATRIX_FILTERS, sortKey: "price", sortDirection: "desc" },
      options.universes,
    );
    expect(descending.map((snapshot) => snapshot.ticker)).toEqual([
      "AAPL",
      "BSX",
      "MSFT",
    ]);
  });

  it("sorts V1.3 metric keys with missing values last", () => {
    const metricSnapshots = [
      makeSnapshot({
        ticker: "LOW",
        trend_score: 25,
        liquidity_score: 15,
        volatility_20d: 0.12,
        beta_vs_spy: 0.7,
        max_drawdown_6m: -0.24,
      }),
      makeSnapshot({
        ticker: "HIGH",
        trend_score: 80,
        liquidity_score: 90,
        volatility_20d: 0.44,
        beta_vs_spy: 1.3,
        max_drawdown_6m: -0.05,
      }),
      makeSnapshot({
        ticker: "MISSING",
        trend_score: null,
        liquidity_score: null,
        volatility_20d: null,
        beta_vs_spy: null,
        max_drawdown_6m: null,
      }),
    ];
    const options = getMatrixFilterOptions(metricSnapshots, {
      ...baseStatus,
      cached_tickers: ["LOW", "HIGH", "MISSING"],
      snapshot_tickers: ["LOW", "HIGH", "MISSING"],
    });
    const cases: Array<{
      sortKey: MatrixSortKey;
      sortDirection: SortDirection;
      expected: string[];
    }> = [
      { sortKey: "trend_score", sortDirection: "desc", expected: ["HIGH", "LOW", "MISSING"] },
      { sortKey: "liquidity_score", sortDirection: "asc", expected: ["LOW", "HIGH", "MISSING"] },
      { sortKey: "volatility_20d", sortDirection: "desc", expected: ["HIGH", "LOW", "MISSING"] },
      { sortKey: "beta_vs_spy", sortDirection: "asc", expected: ["LOW", "HIGH", "MISSING"] },
      { sortKey: "max_drawdown_6m", sortDirection: "asc", expected: ["LOW", "HIGH", "MISSING"] },
    ];

    for (const testCase of cases) {
      const sorted = filterAndSortSnapshots(
        metricSnapshots,
        {
          ...DEFAULT_MATRIX_FILTERS,
          sortKey: testCase.sortKey,
          sortDirection: testCase.sortDirection,
        },
        options.universes,
      );
      expect(sorted.map((snapshot) => snapshot.ticker)).toEqual(testCase.expected);
    }
  });
});
