import { ChevronRight, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { DataTable } from "@/shared/ui/DataTable";
import { getScreenViews } from "../api/marketApi";
import { QualityBadge } from "../components/QualityBadge";
import {
  formatNumber,
  formatPercent,
  formatPrice,
  formatScore,
  normalizeLabel,
  trendClass,
} from "../model/formatters";
import type { ScreenResult, ScreenView } from "../model/types";

type LoadPhase = "idle" | "loading" | "ready" | "error";

export function ScreenPage() {
  const navigate = useNavigate();
  const [views, setViews] = useState<ScreenView[]>([]);
  const [activeViewId, setActiveViewId] = useState("breakout_watch");
  const [phase, setPhase] = useState<LoadPhase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function loadScreenViews() {
      setPhase("loading");
      setError(null);
      const response = await getScreenViews();
      if (cancelled) {
        return;
      }
      setViews(response);
      setActiveViewId((current) =>
        response.some((view) => view.id === current)
          ? current
          : response[0]?.id || "breakout_watch",
      );
      setPhase("ready");
    }

    loadScreenViews().catch((loadError) => {
      if (!cancelled) {
        setError(loadError instanceof Error ? loadError.message : String(loadError));
        setViews([]);
        setPhase("error");
      }
    });

    return () => {
      cancelled = true;
    };
  }, []);

  const activeView = views.find((view) => view.id === activeViewId) || views[0] || null;
  const filteredRows = useMemo(() => {
    const query = search.trim().toLowerCase();
    const rows = activeView?.rows || [];
    if (!query) {
      return rows;
    }
    return rows.filter((row) =>
      [
        row.ticker,
        row.trend,
        row.breakout_status,
        row.data_quality?.status,
      ].some((value) => String(value || "").toLowerCase().includes(query)),
    );
  }, [activeView, search]);

  return (
    <div className="market-page">
      <section className="screen-header section-card">
        <div>
          <div className="eyebrow">Screener</div>
          <h1>Default technical watchlists</h1>
          <p>
            Breakout, support, relative strength, and oversold views from the local
            screen endpoint.
          </p>
        </div>
        <div className="screen-header-meta mono">
          {phase === "loading" || phase === "idle"
            ? "Loading"
            : `${views.reduce((total, view) => total + view.rows.length, 0)} matches`}
        </div>
      </section>

      {phase === "error" ? (
        <div className="error-banner">
          Screener data is unavailable.
          {error ? <span className="mono">{error}</span> : null}
        </div>
      ) : null}

      <section className="screen-card section-card">
        <div className="screen-tabs" role="tablist" aria-label="Screen views">
          {views.map((view) => (
            <button
              key={view.id}
              type="button"
              role="tab"
              aria-selected={view.id === activeViewId}
              className={`screen-tab ${view.id === activeViewId ? "is-active" : ""}`}
              onClick={() => setActiveViewId(view.id)}
            >
              <span>{view.label}</span>
              <span className="mono">{view.rows.length}</span>
            </button>
          ))}
        </div>

        <div className="screen-toolbar">
          <div>
            <h2>{activeView?.label || "Screen results"}</h2>
            {activeView?.description ? <p>{activeView.description}</p> : null}
            {activeView?.summary ? <p>{activeView.summary}</p> : null}
          </div>
          <label className="control-field screen-search">
            <span className="control-label">Search</span>
            <span className="search-input-wrap">
              <Search size={15} aria-hidden="true" />
              <input
                aria-label="Search screen results"
                placeholder="Ticker or signal"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
            </span>
          </label>
        </div>

        <DataTable>
          <thead>
            <tr>
              <th>Ticker</th>
              <th>Price</th>
              <th>Trend</th>
              <th>RSI14</th>
              <th>1M / 3M</th>
              <th>RS vs SPY</th>
              <th>52W</th>
              <th>Quality</th>
              <th aria-label="Open ticker" />
            </tr>
          </thead>
          <tbody>
            {phase === "loading" || phase === "idle" ? (
              <tr>
                <td colSpan={9} className="table-empty">
                  Loading screen results...
                </td>
              </tr>
            ) : filteredRows.length > 0 ? (
              filteredRows.map((row) => (
                <ScreenResultRow
                  key={`${activeView?.id}-${row.ticker}`}
                  row={row}
                  onSelect={() => navigate(`/market/${encodeURIComponent(row.ticker)}`)}
                />
              ))
            ) : activeView && activeView.rows.length > 0 ? (
              <tr>
                <td colSpan={9} className="table-empty">
                  No screen results match the current search.
                </td>
              </tr>
            ) : (
              <tr>
                <td colSpan={9} className="table-empty">
                  No tickers matched this screen.
                </td>
              </tr>
            )}
          </tbody>
        </DataTable>
      </section>
    </div>
  );
}

function ScreenResultRow({
  row,
  onSelect,
}: {
  row: ScreenResult;
  onSelect: () => void;
}) {
  const rs3m = row.relative_strength_vs_spy?.periods?.["3m"]?.spread;
  return (
    <tr onClick={onSelect} data-testid={`screen-row-${row.ticker}`}>
      <td>
        <div className="ticker-cell">{row.ticker}</div>
        <div className="subtle">{row.as_of || "N/A"}</div>
      </td>
      <td className="mono">{formatPrice(row.price, row.currency || "USD")}</td>
      <td>
        <div className={trendClass(row.trend)}>{normalizeLabel(row.trend)}</div>
        <div className="subtle">{normalizeLabel(row.breakout_status)}</div>
        <div className="subtle mono">Score {formatScore(row.trend_score)}</div>
      </td>
      <td>
        <div className="mono">{formatNumber(row.rsi14, 1)}</div>
        <div className="subtle mono">ATR {formatNumber(row.atr14, 2)}</div>
      </td>
      <td>
        <div className="stacked mono">
          <span>1M {formatPercent(row.return_1m, 0)}</span>
          <span>3M {formatPercent(row.return_3m, 0)}</span>
        </div>
      </td>
      <td>
        <div>{normalizeLabel(row.relative_strength_vs_spy?.status)}</div>
        <div className="subtle mono">3M {formatPercent(rs3m)}</div>
      </td>
      <td>
        <div className="mono">{formatPercent(row.week52_position)}</div>
        <div className="subtle mono">High {formatPercent(row.distance_from_52w_high)}</div>
      </td>
      <td>
        <QualityBadge status={row.data_quality?.status} />
      </td>
      <td className="table-action-cell">
        <ChevronRight size={16} aria-hidden="true" />
      </td>
    </tr>
  );
}
