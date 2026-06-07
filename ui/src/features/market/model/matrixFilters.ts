import type { MarketStatus, TechnicalSnapshot } from "./types";

export const ALL_UNIVERSE_ID = "all";

export type MatrixSortKey =
  | "ticker"
  | "price"
  | "trend"
  | "trend_score"
  | "liquidity_score"
  | "volatility_20d"
  | "beta_vs_spy"
  | "max_drawdown_6m"
  | "rsi14"
  | "return_1m"
  | "return_3m"
  | "week52_position"
  | "volume_ratio"
  | "quality";

export type SortDirection = "asc" | "desc";

export interface MatrixFilterState {
  search: string;
  trend: string;
  quality: string;
  universeId: string;
  sortKey: MatrixSortKey;
  sortDirection: SortDirection;
}

export interface UniverseOption {
  id: string;
  label: string;
  tickers: string[];
}

export interface MatrixFilterOptions {
  trends: string[];
  qualities: string[];
  universes: UniverseOption[];
}

export const DEFAULT_MATRIX_FILTERS: MatrixFilterState = {
  search: "",
  trend: "all",
  quality: "all",
  universeId: ALL_UNIVERSE_ID,
  sortKey: "ticker",
  sortDirection: "asc",
};

const GROUP_FIELDS = ["groups", "universes", "ticker_groups", "cached_groups"];
const TICKER_LIST_FIELDS = ["tickers", "symbols", "cached_tickers", "members", "constituents"];
const LABEL_FIELDS = ["name", "label", "title", "universe", "group"];

export function getMatrixFilterOptions(
  snapshots: TechnicalSnapshot[],
  status: MarketStatus | null,
): MatrixFilterOptions {
  return {
    trends: distinctValues(snapshots.map((snapshot) => snapshot.trend)),
    qualities: distinctValues(
      snapshots.map((snapshot) => snapshot.data_quality?.status),
    ),
    universes: getUniverseOptions(status, snapshots),
  };
}

export function filterAndSortSnapshots(
  snapshots: TechnicalSnapshot[],
  filters: MatrixFilterState,
  universes: UniverseOption[],
): TechnicalSnapshot[] {
  const search = filters.search.trim().toLowerCase();
  const universe = universes.find((option) => option.id === filters.universeId);
  const universeTickers =
    universe && universe.id !== ALL_UNIVERSE_ID
      ? new Set(universe.tickers.map((ticker) => ticker.toUpperCase()))
      : null;

  return snapshots
    .filter((snapshot) => {
      if (search && !snapshotMatchesSearch(snapshot, search)) {
        return false;
      }
      if (filters.trend !== "all" && snapshot.trend !== filters.trend) {
        return false;
      }
      if (
        filters.quality !== "all" &&
        snapshot.data_quality?.status !== filters.quality
      ) {
        return false;
      }
      if (universeTickers && !universeTickers.has(snapshot.ticker.toUpperCase())) {
        return false;
      }
      return true;
    })
    .sort((a, b) => compareSnapshots(a, b, filters.sortKey, filters.sortDirection));
}

export function getUniverseOptions(
  status: MarketStatus | null,
  snapshots: TechnicalSnapshot[] = [],
): UniverseOption[] {
  const options: UniverseOption[] = [];
  const seenIds = new Set<string>();
  const fallbackTickers = snapshots.map((snapshot) => snapshot.ticker);
  const cachedTickers = normalizeTickerList(status?.cached_tickers);

  addUniverseOption(
    options,
    seenIds,
    ALL_UNIVERSE_ID,
    cachedTickers.length > 0 ? "All cached" : "All displayed",
    cachedTickers.length > 0 ? cachedTickers : fallbackTickers,
  );

  const snapshotTickers = normalizeTickerList(status?.snapshot_tickers);
  if (snapshotTickers.length > 0 && !sameTickerSet(snapshotTickers, cachedTickers)) {
    addUniverseOption(options, seenIds, "snapshots", "Snapshot tickers", snapshotTickers);
  }

  for (const field of GROUP_FIELDS) {
    for (const option of extractGroupedTickerOptions(status?.[field], field)) {
      addUniverseOption(options, seenIds, option.id, option.label, option.tickers);
    }
  }

  return options;
}

function snapshotMatchesSearch(snapshot: TechnicalSnapshot, search: string): boolean {
  const values = [
    snapshot.ticker,
    snapshot.trend,
    snapshot.breakout_status,
    snapshot.data_quality?.status,
  ];
  return values.some((value) => String(value || "").toLowerCase().includes(search));
}

function compareSnapshots(
  a: TechnicalSnapshot,
  b: TechnicalSnapshot,
  sortKey: MatrixSortKey,
  direction: SortDirection,
): number {
  const first = getSortValue(a, sortKey);
  const second = getSortValue(b, sortKey);
  const firstMissing = isMissingSortValue(first);
  const secondMissing = isMissingSortValue(second);

  if (firstMissing && secondMissing) {
    return a.ticker.localeCompare(b.ticker);
  }
  if (firstMissing) {
    return 1;
  }
  if (secondMissing) {
    return -1;
  }

  let result: number;
  if (typeof first === "number" && typeof second === "number") {
    result = first - second;
  } else {
    result = String(first).localeCompare(String(second), undefined, {
      sensitivity: "base",
      numeric: true,
    });
  }

  if (result === 0) {
    result = a.ticker.localeCompare(b.ticker);
  }

  return direction === "asc" ? result : -result;
}

function getSortValue(
  snapshot: TechnicalSnapshot,
  sortKey: MatrixSortKey,
): number | string | null | undefined {
  if (sortKey === "volume_ratio") {
    return snapshot.volume_signal?.ratio;
  }
  if (sortKey === "quality") {
    return snapshot.data_quality?.status;
  }
  return snapshot[sortKey];
}

function isMissingSortValue(value: number | string | null | undefined): boolean {
  if (value == null || value === "") {
    return true;
  }
  return typeof value === "number" && !Number.isFinite(value);
}

function distinctValues(values: Array<string | null | undefined>): string[] {
  return Array.from(
    new Set(values.filter((value): value is string => Boolean(value))),
  ).sort((a, b) => a.localeCompare(b));
}

function extractGroupedTickerOptions(value: unknown, field: string): UniverseOption[] {
  if (!value) {
    return [];
  }

  if (Array.isArray(value)) {
    return value.flatMap((item, index) => {
      if (!isRecord(item)) {
        return [];
      }
      const label = readLabel(item) || `${startCase(field)} ${index + 1}`;
      const tickers = readTickerListFromRecord(item);
      return tickers.length > 0
        ? [{ id: `${field}:${slugify(label)}`, label, tickers }]
        : [];
    });
  }

  if (!isRecord(value)) {
    return [];
  }

  return Object.entries(value).flatMap(([key, groupValue]) => {
    const label = isRecord(groupValue) ? readLabel(groupValue) || key : key;
    const tickers = isRecord(groupValue)
      ? readTickerListFromRecord(groupValue)
      : normalizeTickerList(groupValue);
    return tickers.length > 0
      ? [{ id: `${field}:${slugify(label)}`, label: startCase(label), tickers }]
      : [];
  });
}

function readTickerListFromRecord(record: Record<string, unknown>): string[] {
  for (const field of TICKER_LIST_FIELDS) {
    const tickers = normalizeTickerList(record[field]);
    if (tickers.length > 0) {
      return tickers;
    }
  }
  return [];
}

function readLabel(record: Record<string, unknown>): string | null {
  for (const field of LABEL_FIELDS) {
    const value = record[field];
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }
  }
  return null;
}

function normalizeTickerList(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return Array.from(
    new Set(
      value
        .flatMap((item) => {
          if (typeof item === "string") {
            return [item];
          }
          if (isRecord(item)) {
            const ticker = item.ticker || item.symbol;
            return typeof ticker === "string" ? [ticker] : [];
          }
          return [];
        })
        .map((ticker) => ticker.trim().toUpperCase())
        .filter(Boolean),
    ),
  );
}

function addUniverseOption(
  options: UniverseOption[],
  seenIds: Set<string>,
  id: string,
  label: string,
  tickers: string[],
): void {
  const normalizedTickers = normalizeTickerList(tickers);
  const optionId = id || slugify(label);
  if (seenIds.has(optionId)) {
    return;
  }
  seenIds.add(optionId);
  options.push({
    id: optionId,
    label,
    tickers: normalizedTickers,
  });
}

function sameTickerSet(first: string[], second: string[]): boolean {
  if (first.length !== second.length) {
    return false;
  }
  const secondSet = new Set(second.map((ticker) => ticker.toUpperCase()));
  return first.every((ticker) => secondSet.has(ticker.toUpperCase()));
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function slugify(value: string): string {
  return value.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

function startCase(value: string): string {
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}
