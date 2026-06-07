import { useEffect, useState } from "react";

import { getDashboardSnapshots } from "../api/marketApi";
import { DataQualityPanel } from "../components/DataQualityPanel";
import { StatusCards } from "../components/StatusCards";
import { TechnicalMatrix } from "../components/TechnicalMatrix";
import type { MarketStatus, TechnicalSnapshot } from "../model/types";

type LoadPhase = "idle" | "loading" | "ready" | "error";

function unavailableStatus(error?: string): MarketStatus {
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

export function MarketMatrixPage() {
  const [status, setStatus] = useState<MarketStatus | null>(null);
  const [snapshots, setSnapshots] = useState<TechnicalSnapshot[]>([]);
  const [phase, setPhase] = useState<LoadPhase>("idle");

  useEffect(() => {
    let cancelled = false;

    async function loadDashboard() {
      setPhase("loading");
      const data = await getDashboardSnapshots();
      if (cancelled) {
        return;
      }
      setStatus(data.status);
      setSnapshots(data.snapshots);
      setPhase(data.status.status === "unavailable" ? "error" : "ready");
    }

    loadDashboard().catch((error) => {
      if (!cancelled) {
        setStatus(unavailableStatus(error instanceof Error ? error.message : String(error)));
        setSnapshots([]);
        setPhase("error");
      }
    });

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="market-page">
      <MarketHero status={status} />
      <StatusCards status={status} />

      {phase === "error" && <MarketError status={status} />}

      <DataQualityPanel status={status} />

      <TechnicalMatrix
        snapshots={snapshots}
        status={status}
        loading={phase === "loading" || phase === "idle"}
      />
    </div>
  );
}

export function MarketHero({ status }: { status: MarketStatus | null }) {
  return (
    <section className="hero-card section-card">
      <div>
        <div className="eyebrow">Independent data workbench</div>
        <h1>Technical snapshots from local market history</h1>
        <p>
          Vite-powered research surface for cached OHLCV and deterministic setup
          metrics. Charts are available from each ticker detail page.
        </p>
      </div>
      <div className="backend-chip">
        <span className={status?.status === "ok" ? "status-dot" : "status-dot is-off"} />
        <span>{status?.status === "ok" ? "Backend online" : "Backend unavailable"}</span>
      </div>
    </section>
  );
}

export function MarketError({ status }: { status: MarketStatus | null }) {
  return (
    <div className="error-banner">
      Backend unavailable. Start Market Data Lab on port 8010, then refresh this page.
      {status?.error ? <span className="mono">{status.error}</span> : null}
    </div>
  );
}
