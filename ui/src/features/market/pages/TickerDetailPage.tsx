import { ArrowLeft } from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
  getMarketStatus,
  getTickerChart,
  getTickerSnapshot,
} from "../api/marketApi";
import { StatusCards } from "../components/StatusCards";
import { TechnicalChartPanel } from "../components/TechnicalChartPanel";
import {
  formatLevelList,
  formatNumber,
  formatPercent,
  formatPrice,
  formatScore,
  normalizeLabel,
  trendClass,
} from "../model/formatters";
import type { MarketStatus, TechnicalChart, TechnicalSnapshot } from "../model/types";
import { QualityBadge } from "../components/QualityBadge";
import { MarketError, MarketHero } from "./MarketMatrixPage";

type LoadPhase = "idle" | "loading" | "ready" | "error";

export function TickerDetailPage() {
  const params = useParams();
  const ticker = params.ticker?.trim().toUpperCase() || "";
  const [status, setStatus] = useState<MarketStatus | null>(null);
  const [snapshot, setSnapshot] = useState<TechnicalSnapshot | null>(null);
  const [chart, setChart] = useState<TechnicalChart | null>(null);
  const [phase, setPhase] = useState<LoadPhase>("idle");
  const [chartLoading, setChartLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function loadDetail() {
      if (!ticker) {
        setPhase("error");
        return;
      }
      setPhase("loading");
      const [statusResponse, snapshotResponse] = await Promise.all([
        getMarketStatus(),
        getTickerSnapshot(ticker),
      ]);
      if (cancelled) {
        return;
      }
      setStatus(statusResponse);
      setSnapshot(snapshotResponse);
      setPhase(statusResponse.status === "unavailable" ? "error" : "ready");
    }

    loadDetail().catch((error) => {
      if (!cancelled) {
        setStatus({
          status: "unavailable",
          price_history_files: 0,
          cached_tickers: [],
          latest_as_of: null,
          stale_count: 0,
          stale_tickers: [],
          snapshots: 0,
          snapshot_tickers: [],
          entries: [],
          error: error instanceof Error ? error.message : String(error),
        });
        setSnapshot(null);
        setPhase("error");
      }
    });

    return () => {
      cancelled = true;
    };
  }, [ticker]);

  useEffect(() => {
    if (!snapshot || snapshot.data_quality.status === "unavailable") {
      setChart(null);
      return;
    }

    let cancelled = false;
    setChartLoading(true);
    getTickerChart(snapshot.ticker, "1y")
      .then((response) => {
        if (!cancelled) {
          setChart(response);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setChartLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [snapshot]);

  return (
    <div className="market-page">
      <MarketHero status={status} />
      <StatusCards status={status} />

      {phase === "error" && <MarketError status={status} />}

      <Link className="back-link" to="/market">
        <ArrowLeft size={16} />
        Back to Market Matrix
      </Link>

      <section className="detail-layout">
        <TickerSummary snapshot={snapshot} loading={phase === "loading" || phase === "idle"} />
        <TechnicalChartPanel chart={chart} snapshot={snapshot} loading={chartLoading} />
      </section>
    </div>
  );
}

function TickerSummary({
  snapshot,
  loading,
}: {
  snapshot: TechnicalSnapshot | null;
  loading: boolean;
}) {
  if (loading) {
    return (
      <section className="ticker-summary section-card">
        <div className="table-empty">Loading ticker snapshot...</div>
      </section>
    );
  }

  if (!snapshot) {
    return (
      <section className="ticker-summary section-card">
        <div className="table-empty">Ticker snapshot is unavailable.</div>
      </section>
    );
  }

  return (
    <section className="ticker-summary section-card">
      <div className="eyebrow">Ticker detail</div>
      <div className="summary-heading">
        <h2>{snapshot.ticker}</h2>
        <div className="summary-price">
          {formatPrice(snapshot.price, snapshot.currency)}
          <span>as of {snapshot.as_of || "N/A"}</span>
        </div>
      </div>
      <div className="detail-section-title">Snapshot summary</div>
      <div className="summary-grid">
        <SummaryMetric label="Trend" value={normalizeLabel(snapshot.trend)} tone={trendClass(snapshot.trend)} />
        <SummaryMetric label="Breakout" value={normalizeLabel(snapshot.breakout_status)} />
        <SummaryMetric label="RSI14" value={formatNumber(snapshot.rsi14, 1)} />
        <SummaryMetric label="ATR14" value={formatNumber(snapshot.atr14, 2)} />
        <SummaryMetric label="MA20 distance" value={formatPercent(snapshot.distance_from_ma20)} />
        <SummaryMetric label="MA50 distance" value={formatPercent(snapshot.distance_from_ma50)} />
        <SummaryMetric label="MA200 distance" value={formatPercent(snapshot.distance_from_ma200)} />
        <SummaryMetric label="52W position" value={formatPercent(snapshot.week52_position)} />
      </div>

      <div className="detail-sections">
        <DeterministicMetricsSection snapshot={snapshot} />

        <DetailSection title="Support / Resistance">
          <div className="detail-metric-grid">
            <DetailMetric
              label="Support"
              value={formatLevelList(snapshot.support_levels, snapshot.currency)}
            />
            <DetailMetric
              label="Resistance"
              value={formatLevelList(snapshot.resistance_levels, snapshot.currency)}
            />
            <DetailMetric
              label="52W low"
              value={formatPrice(snapshot.week52_low, snapshot.currency)}
            />
            <DetailMetric
              label="52W high"
              value={formatPrice(snapshot.week52_high, snapshot.currency)}
            />
          </div>
        </DetailSection>

        <RelativeStrengthSection snapshot={snapshot} />
        <VolumeSection snapshot={snapshot} />
        <QualityWarningsSection snapshot={snapshot} />
      </div>
    </section>
  );
}

function DeterministicMetricsSection({ snapshot }: { snapshot: TechnicalSnapshot }) {
  return (
    <DetailSection title="Deterministic metrics">
      <div className="detail-metric-grid deterministic-metrics" data-testid="detail-metrics-section">
        <DetailMetric label="Trend score" value={formatScore(snapshot.trend_score)} />
        <DetailMetric label="Liquidity score" value={formatScore(snapshot.liquidity_score)} />
        <DetailMetric label="20D volatility" value={formatPercent(snapshot.volatility_20d)} />
        <DetailMetric label="60D volatility" value={formatPercent(snapshot.volatility_60d)} />
        <DetailMetric label="Beta vs SPY" value={formatNumber(snapshot.beta_vs_spy, 2)} />
        <DetailMetric label="6M max drawdown" value={formatPercent(snapshot.max_drawdown_6m)} />
        <DetailMetric label="1Y max drawdown" value={formatPercent(snapshot.max_drawdown_1y)} />
        <DetailMetric label="52W high distance" value={formatPercent(snapshot.distance_from_52w_high)} />
        <DetailMetric label="52W low distance" value={formatPercent(snapshot.distance_from_52w_low)} />
        <DetailMetric label="Latest gap" value={formatPercent(snapshot.latest_gap_pct)} />
      </div>
    </DetailSection>
  );
}

function DetailSection({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="detail-section">
      <div className="detail-section-title">{title}</div>
      {children}
    </div>
  );
}

function DetailMetric({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: string;
}) {
  return (
    <div className="detail-metric">
      <div className="summary-label">{label}</div>
      <div className={`detail-metric-value ${tone || ""}`}>{value}</div>
    </div>
  );
}

function RelativeStrengthSection({ snapshot }: { snapshot: TechnicalSnapshot }) {
  const rs = snapshot.relative_strength_vs_spy;
  const benchmark = rs?.benchmark || "SPY";
  const periods = Object.entries(rs?.periods || {}).sort(([first], [second]) =>
    periodSortValue(first) - periodSortValue(second),
  );

  return (
    <DetailSection title="Relative strength">
      <div className="detail-metric-grid">
        <DetailMetric label="Benchmark" value={benchmark} />
        <DetailMetric label="Status" value={normalizeLabel(rs?.status)} />
      </div>
      {periods.length > 0 ? (
        <div className="rs-periods">
          {periods.map(([period, values]) => (
            <div className="rs-period-row" key={period}>
              <div className="summary-label">{period.toUpperCase()}</div>
              <div className="mono">{formatPercent(values.spread)}</div>
              <div className="subtle">
                {snapshot.ticker} {formatPercent(values.return)} / {benchmark}{" "}
                {formatPercent(values.benchmark_return)}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="detail-empty">Relative strength data is unavailable.</div>
      )}
    </DetailSection>
  );
}

function VolumeSection({ snapshot }: { snapshot: TechnicalSnapshot }) {
  const volume = snapshot.volume_signal;

  return (
    <DetailSection title="Volume">
      <div className="detail-metric-grid">
        <DetailMetric label="Signal" value={normalizeLabel(volume?.status)} />
        <DetailMetric label="Ratio" value={`${formatNumber(volume?.ratio, 2)}x`} />
        <DetailMetric label="Latest volume" value={formatNumber(volume?.latest_volume, 0)} />
        <DetailMetric label="20D average" value={formatNumber(volume?.avg_20d, 0)} />
      </div>
    </DetailSection>
  );
}

function QualityWarningsSection({ snapshot }: { snapshot: TechnicalSnapshot }) {
  const warnings = snapshot.data_quality.warnings || [];

  return (
    <DetailSection title="Quality warnings">
      <div className="quality-summary">
        <QualityBadge status={snapshot.data_quality.status} />
        <span className="subtle">
          {snapshot.data_quality.source || snapshot.data_quality.generated_at || "Snapshot feed"}
        </span>
      </div>
      {warnings.length > 0 ? (
        <ul className="quality-warning-list">
          {warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      ) : (
        <div className="detail-empty">No quality warnings reported.</div>
      )}
    </DetailSection>
  );
}

function periodSortValue(period: string): number {
  const order: Record<string, number> = {
    "1m": 1,
    "3m": 2,
    "6m": 3,
    ytd: 4,
    "1y": 5,
  };
  return order[period.toLowerCase()] || 99;
}

function SummaryMetric({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: string;
}) {
  return (
    <div className="summary-metric">
      <div className="summary-label">{label}</div>
      <div className={`summary-value ${tone || ""}`}>{value}</div>
    </div>
  );
}
