import { Link } from "react-router-dom";

import { SectionCard } from "@/shared/ui/SectionCard";

export function OutOfScopePage() {
  return (
    <div className="market-page">
      <SectionCard className="scope-card">
        <div className="eyebrow">Market Data Lab V1</div>
        <h1>Outside the current scope</h1>
        <p>
          V1 focuses on cached technical snapshots and chart-ready market data.
          Backtesting, alerts, and watchlist editing will be separate additions.
        </p>
        <Link className="text-link" to="/market">
          Back to Market Matrix
        </Link>
      </SectionCard>
    </div>
  );
}
