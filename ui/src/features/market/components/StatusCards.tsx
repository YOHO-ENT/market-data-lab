import { MetricCard } from "@/shared/ui/MetricCard";
import type { MarketStatus } from "../model/types";

export function StatusCards({ status }: { status: MarketStatus | null }) {
  return (
    <section className="status-grid" aria-label="Market Data Lab status">
      <MetricCard
        label="Cached tickers"
        value={status?.cached_ticker_count ?? status?.cached_tickers.length ?? 0}
      />
      <MetricCard label="Latest as of" value={status?.latest_as_of || "N/A"} mono />
      <MetricCard label="Stale tickers" value={status?.stale_count ?? 0} />
      <MetricCard label="Snapshot files" value={status?.snapshot_count ?? status?.snapshots ?? 0} />
    </section>
  );
}
