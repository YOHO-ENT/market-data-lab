import { useState } from "react";
import { Link } from "react-router-dom";

import { normalizeLabel } from "../model/formatters";
import type { MarketStatus } from "../model/types";
import { QualityBadge } from "./QualityBadge";

interface QualityCheckView {
  id: string;
  label: string;
  status?: string;
  detail?: string;
  value?: string;
  issueType: string;
  issueTypeLabel: string;
  tickers: string[];
  isProblem: boolean;
}

const LABEL_FIELDS = ["label", "name", "check", "id", "key"];
const STATUS_FIELDS = ["status", "state", "result", "severity"];
const DETAIL_FIELDS = ["message", "description", "detail", "details", "warning", "reason"];
const VALUE_FIELDS = [
  "value",
  "actual",
  "count",
  "issue_count",
  "rows",
  "as_of",
  "generated_at",
  "tickers",
  "symbols",
];
const TICKER_FIELDS = ["ticker", "symbol"];
const TICKER_LIST_FIELDS = [
  "tickers",
  "symbols",
  "affected_tickers",
  "affected_symbols",
  "stale_tickers",
  "missing_tickers",
];
const ISSUE_COLLECTION_FIELDS = [
  "issues",
  "items",
  "problems",
  "rows",
  "failures",
  "failed",
  "affected",
];
const QUALITY_CHECK_IDS = [
  "stale",
  "short_history",
  "missing_price",
  "missing_volume",
  "invalid_values",
];
const METADATA_FIELDS = new Set([
  "status",
  "state",
  "result",
  "severity",
  "summary",
  "message",
  "description",
  "detail",
  "details",
  "warning",
  "warnings",
  "reason",
  "source",
  "rows",
  "as_of",
  "generated_at",
  "issue_count",
  "checks",
]);
const STATUS_WORDS = new Set([
  "ok",
  "pass",
  "passed",
  "healthy",
  "success",
  "partial",
  "warn",
  "warning",
  "degraded",
  "stale",
  "unavailable",
  "fail",
  "failed",
  "error",
  "critical",
]);

export function DataQualityPanel({ status }: { status: MarketStatus | null }) {
  const [issueType, setIssueType] = useState("all");
  const report = isRecord(status?.data_quality_report) ? status.data_quality_report : null;
  const quality = readQualitySource(status);
  const checks = normalizeQualityChecks(readChecks(report) ?? readChecks(quality));

  if (!report && !quality) {
    return null;
  }

  if (checks.length === 0) {
    return null;
  }

  const reportStatus =
    normalizeCheckStatus(readFirstString(report, STATUS_FIELDS)) ||
    normalizeCheckStatus(readFirstString(quality, STATUS_FIELDS)) ||
    status?.cache_status ||
    status?.status;
  const summary = readString(report?.summary) || readString(quality?.summary);
  const problems = checks.filter((check) => check.isProblem);
  const issueTypes = Array.from(
    new Map(problems.map((problem) => [problem.issueType, problem.issueTypeLabel])),
  );
  const activeIssueType = issueTypes.some(([id]) => id === issueType) ? issueType : "all";
  const filteredProblems =
    activeIssueType === "all"
      ? problems
      : problems.filter((problem) => problem.issueType === activeIssueType);

  return (
    <section className="quality-panel section-card" data-testid="market-quality-panel">
      <div className="quality-panel-header">
        <div>
          <div className="eyebrow">Data Quality</div>
          <h2>Snapshot checks</h2>
          {summary ? <p>{summary}</p> : null}
        </div>
        <div className="quality-panel-meta">
          <QualityBadge status={reportStatus} />
          <span className="mono">{checks.length} checks</span>
        </div>
      </div>

      <div className="quality-check-grid">
        {checks.map((check) => (
          <div className="quality-check-row" key={check.id}>
            <div className="quality-check-main">
              <span>{normalizeLabel(check.label)}</span>
              {check.detail ? <span className="subtle">{check.detail}</span> : null}
            </div>
            {check.value ? <span className="quality-check-value mono">{check.value}</span> : null}
            <QualityBadge status={check.status} />
          </div>
        ))}
      </div>

      <div className="quality-problem-panel">
        <div className="quality-problem-header">
          <div>
            <div className="detail-section-title">Problem list</div>
            <p>
              {problems.length > 0
                ? `${problems.length} issue groups reported.`
                : "No quality problems reported."}
            </p>
          </div>
          {issueTypes.length > 1 ? (
            <label className="control-field quality-filter">
              <span className="control-label">Issue type</span>
              <select
                aria-label="Issue type"
                value={activeIssueType}
                onChange={(event) => setIssueType(event.target.value)}
              >
                <option value="all">All issues</option>
                {issueTypes.map(([id, label]) => (
                  <option key={id} value={id}>
                    {normalizeLabel(label)}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
        </div>

        {filteredProblems.length > 0 ? (
          <div className="quality-problem-list" data-testid="quality-problem-list">
            {filteredProblems.map((problem) => (
              <div className="quality-problem-row" key={problem.id}>
                <div className="quality-problem-main">
                  <span>{normalizeLabel(problem.issueTypeLabel)}</span>
                  {problem.detail ? <span className="subtle">{problem.detail}</span> : null}
                  {problem.tickers.length > 0 ? (
                    <div className="quality-ticker-links">
                      {problem.tickers.map((ticker) => (
                        <Link
                          key={ticker}
                          className="ticker-link mono"
                          to={`/market/${encodeURIComponent(ticker)}`}
                        >
                          {ticker}
                        </Link>
                      ))}
                    </div>
                  ) : null}
                </div>
                {problem.value ? (
                  <span className="quality-check-value mono">{problem.value}</span>
                ) : null}
                <QualityBadge status={problem.status} />
              </div>
            ))}
          </div>
        ) : null}
      </div>
    </section>
  );
}

function readChecks(record: Record<string, unknown> | null): unknown {
  if (!record) {
    return undefined;
  }
  if (Array.isArray(record.checks)) {
    return record.checks;
  }
  if (isRecord(record.checks) && Object.keys(record.checks).length > 0) {
    const knownChecks = pickKnownQualityChecks(record.checks);
    if (Object.keys(knownChecks).length > 0) {
      return knownChecks;
    }
    const nestedChecks = pickNestedQualityChecks(record.checks);
    if (Object.keys(nestedChecks).length > 0) {
      return nestedChecks;
    }
    return record.checks;
  }

  const knownChecks = pickKnownQualityChecks(record);
  if (Object.keys(knownChecks).length > 0) {
    return knownChecks;
  }

  const nestedChecks = pickNestedQualityChecks(record);
  if (Object.keys(nestedChecks).length > 0) {
    return nestedChecks;
  }

  return undefined;
}

function normalizeQualityChecks(value: unknown): QualityCheckView[] {
  if (Array.isArray(value)) {
    return value
      .map((item, index) => normalizeQualityCheck(item, `check-${index + 1}`, index))
      .filter((check): check is QualityCheckView => Boolean(check));
  }

  if (!isRecord(value)) {
    return [];
  }

  return Object.entries(value)
    .map(([key, item], index) => normalizeQualityCheck(item, key, index))
    .filter((check): check is QualityCheckView => Boolean(check));
}

function normalizeQualityCheck(
  value: unknown,
  fallbackLabel: string,
  index: number,
): QualityCheckView | null {
  if (!isRecord(value)) {
    const inferredStatus = inferStatusFromValue(value);
    const formattedValue = formatUnknownValue(value);
    return {
      id: `${index}-${slugify(fallbackLabel)}`,
      label: fallbackLabel,
      status: inferredStatus,
      detail: typeof value === "string" && !inferredStatus ? formattedValue : undefined,
      value: inferredStatus ? formattedValue : undefined,
      issueType: slugify(fallbackLabel),
      issueTypeLabel: fallbackLabel,
      tickers: [],
      isProblem: isProblemStatus(inferredStatus) || valueIndicatesProblem(value),
    };
  }

  const label = readFirstString(value, LABEL_FIELDS) || fallbackLabel;
  const rawValue = VALUE_FIELDS.map((field) => value[field]).find(isDisplayableValue);
  const status =
    normalizeCheckStatus(readFirstString(value, STATUS_FIELDS), value.passed) ||
    inferStatusFromValue(rawValue);
  const detail = readFirstString(value, DETAIL_FIELDS);

  return {
    id: `${index}-${slugify(label)}`,
    label,
    status,
    detail,
    value: rawValue == null ? undefined : formatUnknownValue(rawValue),
    issueType: slugify(label),
    issueTypeLabel: label,
    tickers: extractTickerList(value),
    isProblem:
      isProblemStatus(status) ||
      valueIndicatesProblem(rawValue) ||
      extractTickerList(value).length > 0,
  };
}

function normalizeCheckStatus(
  status: string | undefined,
  passed?: unknown,
): string | undefined {
  if (status) {
    const normalized = status.toLowerCase();
    if (["pass", "passed", "healthy", "success"].includes(normalized)) {
      return "ok";
    }
    if (["warn", "warning", "degraded"].includes(normalized)) {
      return "partial";
    }
    if (["fail", "failed", "error", "critical"].includes(normalized)) {
      return "unavailable";
    }
    return normalized;
  }

  if (typeof passed === "boolean") {
    return passed ? "ok" : "partial";
  }

  return undefined;
}

function readQualitySource(status: MarketStatus | null): Record<string, unknown> | null {
  const candidates = [status?.quality, status?.data_quality];
  for (const candidate of candidates) {
    if (isRecord(candidate)) {
      return candidate;
    }
  }
  return null;
}

function pickKnownQualityChecks(record: Record<string, unknown>): Record<string, unknown> {
  const checks: Record<string, unknown> = {};
  for (const id of QUALITY_CHECK_IDS) {
    if (record[id] !== undefined) {
      checks[id] = record[id];
    }
  }
  return checks;
}

function pickNestedQualityChecks(record: Record<string, unknown>): Record<string, unknown> {
  const checks: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(record)) {
    if (!METADATA_FIELDS.has(key) && isPotentialCheckValue(value)) {
      checks[key] = value;
    }
  }
  return checks;
}

function isPotentialCheckValue(value: unknown): boolean {
  if (value == null) {
    return false;
  }
  if (Array.isArray(value) || isRecord(value)) {
    return true;
  }
  return ["boolean", "number", "string"].includes(typeof value);
}

function inferStatusFromValue(value: unknown): string | undefined {
  if (typeof value === "boolean") {
    return value ? "partial" : "ok";
  }
  if (typeof value === "number" && Number.isFinite(value)) {
    return value === 0 ? "ok" : "partial";
  }
  if (Array.isArray(value)) {
    return value.length === 0 ? "ok" : "partial";
  }
  if (typeof value === "string") {
    const normalized = value.trim().toLowerCase();
    return STATUS_WORDS.has(normalized) ? normalizeCheckStatus(normalized) : undefined;
  }
  return undefined;
}

function readFirstString(record: Record<string, unknown> | null, fields: string[]): string | undefined {
  if (!record) {
    return undefined;
  }
  for (const field of fields) {
    const value = readString(record[field]);
    if (value) {
      return value;
    }
  }
  return undefined;
}

function readString(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isDisplayableValue(value: unknown): boolean {
  if (Array.isArray(value)) {
    return value.every(
      (item) =>
        typeof item === "string" ||
        typeof item === "number" ||
        typeof item === "boolean",
    );
  }
  return typeof value === "string" || typeof value === "number" || typeof value === "boolean";
}

function isProblemStatus(status: string | undefined): boolean {
  return Boolean(status && !["ok", "pass", "passed", "healthy", "success"].includes(status));
}

function valueIndicatesProblem(value: unknown): boolean {
  if (typeof value === "boolean") {
    return value;
  }
  if (typeof value === "number") {
    return Number.isFinite(value) && value > 0;
  }
  if (Array.isArray(value)) {
    return value.length > 0;
  }
  return false;
}

function extractTickerList(value: unknown): string[] {
  if (Array.isArray(value)) {
    return normalizeTickerList(value);
  }
  if (!isRecord(value)) {
    return [];
  }

  const tickers: string[] = [];
  for (const field of TICKER_FIELDS) {
    const ticker = readString(value[field]);
    if (ticker) {
      tickers.push(ticker);
    }
  }
  for (const field of TICKER_LIST_FIELDS) {
    tickers.push(...normalizeTickerList(value[field]));
  }
  for (const field of ISSUE_COLLECTION_FIELDS) {
    tickers.push(...extractTickerList(value[field]));
  }

  return Array.from(new Set(tickers.map((ticker) => ticker.toUpperCase())));
}

function normalizeTickerList(value: unknown): string[] {
  if (typeof value === "string") {
    return value
      .split(/[,\s]+/)
      .map((ticker) => ticker.trim().toUpperCase())
      .filter(Boolean);
  }
  if (!Array.isArray(value)) {
    return [];
  }
  return value.flatMap((item) => {
    if (typeof item === "string") {
      return normalizeTickerList(item);
    }
    if (isRecord(item)) {
      return extractTickerList(item);
    }
    return [];
  });
}

function formatUnknownValue(value: unknown): string | undefined {
  if (Array.isArray(value)) {
    if (value.length === 0) {
      return "0";
    }
    const formattedItems = value
      .map((item) => formatUnknownValue(item))
      .filter((item): item is string => Boolean(item));
    if (formattedItems.length === 0) {
      return undefined;
    }
    const visibleItems = formattedItems.slice(0, 3).join(", ");
    return formattedItems.length > 3
      ? `${visibleItems} +${formattedItems.length - 3}`
      : visibleItems;
  }
  if (typeof value === "number") {
    return Number.isFinite(value) ? value.toLocaleString("en-US") : undefined;
  }
  if (typeof value === "boolean") {
    return value ? "yes" : "no";
  }
  if (typeof value === "string") {
    return value.trim() || undefined;
  }
  return undefined;
}

function slugify(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");
}
