import { AlertTriangle, CheckCircle2, Clock3, XCircle } from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { getRefreshRuns } from "../api/marketApi";
import { QualityBadge } from "../components/QualityBadge";
import type { RefreshRun, RunIssue } from "../model/types";

type LoadPhase = "idle" | "loading" | "ready" | "error";

export function RunsPage() {
  const [runs, setRuns] = useState<RefreshRun[]>([]);
  const [phase, setPhase] = useState<LoadPhase>("idle");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadRuns() {
      setPhase("loading");
      setError(null);
      const response = await getRefreshRuns();
      if (cancelled) {
        return;
      }
      setRuns(response);
      setPhase("ready");
    }

    loadRuns().catch((loadError) => {
      if (!cancelled) {
        setError(loadError instanceof Error ? loadError.message : String(loadError));
        setRuns([]);
        setPhase("error");
      }
    });

    return () => {
      cancelled = true;
    };
  }, []);

  const summary = useMemo(() => summarizeRuns(runs), [runs]);

  return (
    <div className="market-page">
      <section className="screen-header section-card">
        <div>
          <div className="eyebrow">Runs</div>
          <h1>Recent refresh runs</h1>
          <p>Read-only operational history for completed market data refreshes.</p>
        </div>
        <div className="screen-header-meta">
          <Clock3 size={16} aria-hidden="true" />
          <span className="mono">{runs.length} runs</span>
        </div>
      </section>

      {phase === "error" ? (
        <div className="error-banner">
          Refresh run history is unavailable.
          {error ? <span className="mono">{error}</span> : null}
        </div>
      ) : null}

      <section className="run-summary-grid">
        <RunSummaryCard icon={<CheckCircle2 size={18} />} label="Succeeded" value={summary.succeeded} />
        <RunSummaryCard icon={<XCircle size={18} />} label="Failed" value={summary.failed} />
        <RunSummaryCard icon={<AlertTriangle size={18} />} label="Stale" value={summary.stale} />
      </section>

      <section className="runs-card section-card">
        <div className="matrix-header">
          <div>
            <h2>Run history</h2>
            <p>Failures and stale cache outcomes are shown inline for each run.</p>
          </div>
        </div>

        <div className="runs-list">
          {phase === "loading" || phase === "idle" ? (
            <div className="table-empty">Loading refresh runs...</div>
          ) : runs.length > 0 ? (
            runs.map((run) => <RunRow key={run.id} run={run} />)
          ) : (
            <div className="table-empty">No refresh runs have been recorded yet.</div>
          )}
        </div>
      </section>
    </div>
  );
}

function RunSummaryCard({
  icon,
  label,
  value,
}: {
  icon: ReactNode;
  label: string;
  value: number;
}) {
  return (
    <div className="metric-card run-summary-card">
      <div className="run-summary-icon" aria-hidden="true">
        {icon}
      </div>
      <div>
        <div className="metric-label">{label}</div>
        <div className="metric-value">{value.toLocaleString("en-US")}</div>
      </div>
    </div>
  );
}

function RunRow({ run }: { run: RefreshRun }) {
  const failedCount = run.failed ?? run.failures.length;
  const staleCount = run.stale ?? run.stale_tickers.length;

  return (
    <article className="run-row" data-testid={`run-row-${run.id}`}>
      <div className="run-row-main">
        <div>
          <div className="run-row-title">
            <span className="mono">{run.id}</span>
            <QualityBadge status={run.status} />
          </div>
          <div className="run-row-meta">
            <span>Started {formatDateTime(run.started_at)}</span>
            {run.finished_at ? <span>Finished {formatDateTime(run.finished_at)}</span> : null}
            {run.period ? <span>{run.period}</span> : null}
            {run.universe ? <span>{run.universe}</span> : null}
          </div>
          {run.summary ? <p>{run.summary}</p> : null}
        </div>
        <div className="run-count-grid">
          <RunCount label="Total" value={run.total} />
          <RunCount label="Succeeded" value={run.succeeded} />
          <RunCount label="Failed" value={failedCount} />
          <RunCount label="Stale" value={staleCount} />
        </div>
      </div>

      <div className="run-issue-grid">
        <RunIssueList title="Failures" issues={run.failures} emptyLabel="No failures" />
        <RunIssueList title="Stale" issues={run.stale_tickers} emptyLabel="No stale tickers" />
      </div>
    </article>
  );
}

function RunCount({
  label,
  value,
}: {
  label: string;
  value: number | null | undefined;
}) {
  return (
    <div className="run-count">
      <span>{label}</span>
      <strong className="mono">{value == null ? "N/A" : value.toLocaleString("en-US")}</strong>
    </div>
  );
}

function RunIssueList({
  title,
  issues,
  emptyLabel,
}: {
  title: string;
  issues: RunIssue[];
  emptyLabel: string;
}) {
  return (
    <div className="run-issue-list">
      <div className="detail-section-title">{title}</div>
      {issues.length > 0 ? (
        <ul>
          {issues.slice(0, 8).map((issue) => (
            <li key={`${issue.id}-${issue.ticker || issue.message || ""}`}>
              {issue.ticker ? (
                <Link className="ticker-link mono" to={`/market/${encodeURIComponent(issue.ticker)}`}>
                  {issue.ticker}
                </Link>
              ) : null}
              <span>{issue.message || normalizeIssueStatus(issue.status)}</span>
              {issue.as_of ? <span className="subtle">as of {issue.as_of}</span> : null}
            </li>
          ))}
        </ul>
      ) : (
        <div className="detail-empty">{emptyLabel}</div>
      )}
    </div>
  );
}

function summarizeRuns(runs: RefreshRun[]) {
  return runs.reduce(
    (summary, run) => ({
      succeeded: summary.succeeded + (run.succeeded || 0),
      failed: summary.failed + (run.failed ?? run.failures.length),
      stale: summary.stale + (run.stale ?? run.stale_tickers.length),
    }),
    { succeeded: 0, failed: 0, stale: 0 },
  );
}

function normalizeIssueStatus(status: string | undefined): string {
  return status ? status.replaceAll("_", " ") : "Issue reported";
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) {
    return "N/A";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}
