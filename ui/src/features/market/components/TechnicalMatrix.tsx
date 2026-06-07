import { ArrowDownAZ, ArrowUpAZ, RotateCcw, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { DataTable } from "@/shared/ui/DataTable";
import {
  formatCompactPercent,
  formatLevelList,
  formatNumber,
  formatPercent,
  formatPrice,
  formatScore,
  normalizeLabel,
  trendClass,
} from "../model/formatters";
import {
  DEFAULT_MATRIX_FILTERS,
  filterAndSortSnapshots,
  getMatrixFilterOptions,
  type MatrixFilterState,
  type MatrixSortKey,
} from "../model/matrixFilters";
import type { MarketStatus, TechnicalSnapshot } from "../model/types";
import { QualityBadge } from "./QualityBadge";

export function TechnicalMatrix({
  snapshots,
  status,
  loading,
}: {
  snapshots: TechnicalSnapshot[];
  status: MarketStatus | null;
  loading: boolean;
}) {
  const navigate = useNavigate();
  const [filters, setFilters] = useState<MatrixFilterState>(DEFAULT_MATRIX_FILTERS);
  const options = useMemo(
    () => getMatrixFilterOptions(snapshots, status),
    [snapshots, status],
  );
  const filteredSnapshots = useMemo(
    () => filterAndSortSnapshots(snapshots, filters, options.universes),
    [snapshots, filters, options.universes],
  );
  const hasActiveFilters =
    filters.search.trim() ||
    filters.trend !== "all" ||
    filters.quality !== "all" ||
    filters.universeId !== "all";

  useEffect(() => {
    if (!options.universes.some((option) => option.id === filters.universeId)) {
      setFilters((current) => ({ ...current, universeId: "all" }));
    }
  }, [filters.universeId, options.universes]);

  const updateFilter = <Key extends keyof MatrixFilterState>(
    key: Key,
    value: MatrixFilterState[Key],
  ) => {
    setFilters((current) => ({ ...current, [key]: value }));
  };

  return (
    <section className="matrix-card section-card">
      <div className="matrix-header">
        <div>
          <h2>Technical Matrix</h2>
          <p>Cached tickers only. Snapshots are read from local Parquet history.</p>
        </div>
        <div className="matrix-count mono">
          {filteredSnapshots.length} of {snapshots.length} loaded
        </div>
      </div>

      <div className="matrix-toolbar">
        <label className="control-field search-control">
          <span className="control-label">Search</span>
          <span className="search-input-wrap">
            <Search size={15} aria-hidden="true" />
            <input
              aria-label="Search tickers"
              placeholder="Ticker or signal"
              value={filters.search}
              onChange={(event) => updateFilter("search", event.target.value)}
            />
          </span>
        </label>

        <label className="control-field">
          <span className="control-label">Trend</span>
          <select
            aria-label="Trend"
            value={filters.trend}
            onChange={(event) => updateFilter("trend", event.target.value)}
            disabled={loading || options.trends.length === 0}
          >
            <option value="all">All trends</option>
            {options.trends.map((trend) => (
              <option key={trend} value={trend}>
                {normalizeLabel(trend)}
              </option>
            ))}
          </select>
        </label>

        <label className="control-field">
          <span className="control-label">Quality</span>
          <select
            aria-label="Data quality"
            value={filters.quality}
            onChange={(event) => updateFilter("quality", event.target.value)}
            disabled={loading || options.qualities.length === 0}
          >
            <option value="all">All quality</option>
            {options.qualities.map((quality) => (
              <option key={quality} value={quality}>
                {normalizeLabel(quality)}
              </option>
            ))}
          </select>
        </label>

        <label className="control-field">
          <span className="control-label">Universe</span>
          <select
            aria-label="Universe"
            value={filters.universeId}
            onChange={(event) => updateFilter("universeId", event.target.value)}
            disabled={loading || options.universes.length <= 1}
          >
            {options.universes.map((universe) => (
              <option key={universe.id} value={universe.id}>
                {universe.label}
              </option>
            ))}
          </select>
        </label>

        <label className="control-field sort-control">
          <span className="control-label">Sort</span>
          <span className="sort-input-wrap">
            <select
              aria-label="Sort by"
              value={filters.sortKey}
              onChange={(event) =>
                updateFilter("sortKey", event.target.value as MatrixSortKey)
              }
              disabled={loading}
            >
              <option value="ticker">Ticker</option>
              <option value="price">Price</option>
              <option value="trend">Trend</option>
              <option value="trend_score">Trend score</option>
              <option value="liquidity_score">Liquidity score</option>
              <option value="volatility_20d">20D volatility</option>
              <option value="beta_vs_spy">Beta vs SPY</option>
              <option value="max_drawdown_6m">6M max drawdown</option>
              <option value="rsi14">RSI14</option>
              <option value="return_1m">1M return</option>
              <option value="return_3m">3M return</option>
              <option value="week52_position">52W position</option>
              <option value="volume_ratio">Volume ratio</option>
              <option value="quality">Quality</option>
            </select>
            <button
              type="button"
              className="icon-button"
              aria-label={
                filters.sortDirection === "asc" ? "Sort ascending" : "Sort descending"
              }
              title={
                filters.sortDirection === "asc" ? "Sort ascending" : "Sort descending"
              }
              onClick={() =>
                updateFilter(
                  "sortDirection",
                  filters.sortDirection === "asc" ? "desc" : "asc",
                )
              }
              disabled={loading}
            >
              {filters.sortDirection === "asc" ? (
                <ArrowDownAZ size={16} aria-hidden="true" />
              ) : (
                <ArrowUpAZ size={16} aria-hidden="true" />
              )}
            </button>
          </span>
        </label>

        {hasActiveFilters && (
          <button
            type="button"
            className="reset-filters-button"
            onClick={() => setFilters(DEFAULT_MATRIX_FILTERS)}
          >
            <RotateCcw size={14} aria-hidden="true" />
            Reset
          </button>
        )}
      </div>

      <DataTable>
        <thead>
          <tr>
            <th>Ticker</th>
            <th>Price</th>
            <th>Trend</th>
            <th>Vol / Beta</th>
            <th>Drawdown</th>
            <th>RSI14</th>
            <th>MA Distance</th>
            <th>Returns</th>
            <th>52W</th>
            <th>Support / Resistance</th>
            <th>RS vs SPY</th>
            <th>Liquidity</th>
            <th>Quality</th>
          </tr>
        </thead>
        <tbody>
          {loading ? (
            <tr>
              <td colSpan={13} className="table-empty">
                Loading cached market data...
              </td>
            </tr>
          ) : filteredSnapshots.length > 0 ? (
            filteredSnapshots.map((snapshot) => (
              <SnapshotRow
                key={snapshot.ticker}
                snapshot={snapshot}
                onSelect={() => navigate(`/market/${encodeURIComponent(snapshot.ticker)}`)}
              />
            ))
          ) : snapshots.length > 0 ? (
            <tr>
              <td colSpan={13} className="table-empty">
                No tickers match the current filters.
              </td>
            </tr>
          ) : (
            <tr>
              <td colSpan={13} className="table-empty">
                No cached tickers found. Refresh Market Data Lab from the CLI first.
              </td>
            </tr>
          )}
        </tbody>
      </DataTable>
    </section>
  );
}

function SnapshotRow({
  snapshot,
  onSelect,
}: {
  snapshot: TechnicalSnapshot;
  onSelect: () => void;
}) {
  const rs = snapshot.relative_strength_vs_spy;
  const volume = snapshot.volume_signal;

  return (
    <tr onClick={onSelect} data-testid={`market-row-${snapshot.ticker}`}>
      <td>
        <div className="ticker-cell">{snapshot.ticker}</div>
        <div className="subtle">{snapshot.as_of || "N/A"}</div>
      </td>
      <td className="mono">{formatPrice(snapshot.price, snapshot.currency)}</td>
      <td>
        <div className={trendClass(snapshot.trend)}>{normalizeLabel(snapshot.trend)}</div>
        <div className="subtle">{normalizeLabel(snapshot.breakout_status)}</div>
        <div className="subtle mono">Score {formatScore(snapshot.trend_score)}</div>
      </td>
      <td>
        <div className="stacked mono">
          <span>20D {formatPercent(snapshot.volatility_20d)}</span>
          <span>60D {formatPercent(snapshot.volatility_60d)}</span>
          <span>Beta {formatNumber(snapshot.beta_vs_spy, 2)}</span>
        </div>
      </td>
      <td>
        <div className="stacked mono">
          <span>6M {formatPercent(snapshot.max_drawdown_6m)}</span>
          <span>1Y {formatPercent(snapshot.max_drawdown_1y)}</span>
        </div>
      </td>
      <td>
        <div className="mono">{formatNumber(snapshot.rsi14, 1)}</div>
        <div className="subtle">ATR {formatNumber(snapshot.atr14, 2)}</div>
      </td>
      <td>
        <div className="stacked mono">
          <span>20D {formatPercent(snapshot.distance_from_ma20)}</span>
          <span>50D {formatPercent(snapshot.distance_from_ma50)}</span>
          <span>200D {formatPercent(snapshot.distance_from_ma200)}</span>
        </div>
      </td>
      <td>
        <div className="returns-grid mono">
          <span>1M {formatCompactPercent(snapshot.return_1m)}</span>
          <span>3M {formatCompactPercent(snapshot.return_3m)}</span>
          <span>6M {formatCompactPercent(snapshot.return_6m)}</span>
          <span>YTD {formatCompactPercent(snapshot.return_ytd)}</span>
        </div>
      </td>
      <td>
        <div className="mono">{formatPercent(snapshot.week52_position)}</div>
        <div className="subtle mono">
          High {formatPercent(snapshot.distance_from_52w_high)}
        </div>
        <div className="subtle mono">
          Low {formatPercent(snapshot.distance_from_52w_low)}
        </div>
        <div className="subtle">
          {formatPrice(snapshot.week52_low, snapshot.currency)} -{" "}
          {formatPrice(snapshot.week52_high, snapshot.currency)}
        </div>
      </td>
      <td>
        <div className="stacked">
          <span>
            <span className="subtle">S </span>
            <span className="mono">
              {formatLevelList(snapshot.support_levels, snapshot.currency)}
            </span>
          </span>
          <span>
            <span className="subtle">R </span>
            <span className="mono">
              {formatLevelList(snapshot.resistance_levels, snapshot.currency)}
            </span>
          </span>
        </div>
      </td>
      <td>
        <div>{normalizeLabel(rs?.status)}</div>
        <div className="subtle mono">3M {formatPercent(rs?.periods?.["3m"]?.spread)}</div>
      </td>
      <td>
        <div className="mono">Score {formatScore(snapshot.liquidity_score)}</div>
        <div className="subtle mono">Gap {formatPercent(snapshot.latest_gap_pct)}</div>
        <div className="subtle">
          {normalizeLabel(volume?.status)}{" "}
          <span className="mono">{formatMultiplier(volume?.ratio)}</span>
        </div>
      </td>
      <td>
        <QualityBadge status={snapshot.data_quality.status} />
      </td>
    </tr>
  );
}

function formatMultiplier(value: number | null | undefined): string {
  const formatted = formatNumber(value, 2);
  return formatted === "N/A" ? formatted : `${formatted}x`;
}
