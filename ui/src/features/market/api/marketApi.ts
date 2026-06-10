import { unavailableSnapshot, unavailableStatus } from "../model/mappers";
import type {
  DashboardData,
  MarketStatus,
  RefreshRun,
  RunIssue,
  ScreenResult,
  ScreenView,
  SnapshotBatchResponse,
  TechnicalChart,
  TechnicalSnapshot,
  UniverseGroup,
  UniverseResponse,
} from "../model/types";

const DEFAULT_SCREEN_DEFINITIONS = [
  {
    id: "breakout_watch",
    label: "Breakout Watch",
    description: "Tickers pressing into resistance with constructive trend signals.",
  },
  {
    id: "near_support",
    label: "Near Support",
    description: "Setups trading close to nearby support levels.",
  },
  {
    id: "relative_strength_leaders",
    label: "Relative Strength Leaders",
    description: "Names outperforming SPY across recent lookback windows.",
  },
  {
    id: "oversold_watch",
    label: "Oversold Watch",
    description: "Tickers with stretched downside or low RSI readings.",
  },
] satisfies Array<Pick<ScreenView, "id" | "label" | "description">>;

const SCREEN_VIEW_FIELDS = ["views", "screens", "screen_views", "default_views"];
const SCREEN_ROW_FIELDS = ["rows", "results", "snapshots", "items", "data", "tickers"];
const UNIVERSE_GROUP_FIELDS = ["groups", "universes", "ticker_groups"];
const TICKER_LIST_FIELDS = ["tickers", "symbols", "members", "constituents"];
const RUN_LIST_FIELDS = ["runs", "items", "data", "results", "refresh_runs"];
const RUN_FAILURE_FIELDS = ["failures", "failed", "errors", "error_tickers"];
const RUN_STALE_FIELDS = ["stale", "stale_tickers"];
const API_BASE_URL = (import.meta.env.VITE_MARKET_DATA_API_BASE_URL || "").replace(/\/$/, "");

function apiUrl(path: string): string {
  if (!API_BASE_URL) {
    return path;
  }
  const normalizedPath = path.startsWith("/api/")
    ? path.slice("/api".length)
    : path.startsWith("/")
      ? path
      : `/${path}`;
  return `${API_BASE_URL}${normalizedPath}`;
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");
  if (init?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(apiUrl(path), {
    ...init,
    headers: {
      ...Object.fromEntries(headers.entries()),
    },
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

let inFlightDashboardSnapshots:
  | { limit: number; promise: Promise<DashboardData> }
  | null = null;
let inFlightScreenViews: Promise<ScreenView[]> | null = null;

export async function getMarketStatus(): Promise<MarketStatus> {
  try {
    return await requestJson<MarketStatus>("/api/status");
  } catch (error) {
    return unavailableStatus(error instanceof Error ? error.message : String(error));
  }
}

export async function getTickerSnapshot(ticker: string): Promise<TechnicalSnapshot> {
  const normalized = ticker.trim().toUpperCase();
  try {
    return await requestJson<TechnicalSnapshot>(
      `/api/snapshot/${encodeURIComponent(normalized)}`,
    );
  } catch (error) {
    return unavailableSnapshot(
      normalized,
      error instanceof Error ? error.message : String(error),
    );
  }
}

export async function getTickerSnapshots(
  tickers: string[],
  limit = tickers.length,
): Promise<TechnicalSnapshot[]> {
  const normalizedTickers = normalizeTickers(tickers).slice(0, limit);
  if (normalizedTickers.length === 0) {
    return [];
  }

  const params = new URLSearchParams({
    tickers: normalizedTickers.join(","),
    limit: String(limit),
  });

  try {
    const payload = await requestJson<SnapshotBatchResponse | TechnicalSnapshot[]>(
      `/api/snapshots?${params.toString()}`,
    );
    return alignSnapshotsToTickers(readSnapshotList(payload), normalizedTickers);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return normalizedTickers.map((ticker) => unavailableSnapshot(ticker, message));
  }
}

export async function getTickerChart(
  ticker: string,
  range = "1y",
): Promise<TechnicalChart | null> {
  const normalized = ticker.trim().toUpperCase();
  try {
    return await requestJson<TechnicalChart>(
      `/api/chart/${encodeURIComponent(normalized)}?range=${encodeURIComponent(range)}`,
    );
  } catch {
    return null;
  }
}

export async function getDashboardSnapshots(limit = 200): Promise<DashboardData> {
  if (inFlightDashboardSnapshots?.limit === limit) {
    return inFlightDashboardSnapshots.promise;
  }

  const promise = loadDashboardSnapshots(limit);
  inFlightDashboardSnapshots = { limit, promise };
  try {
    return await promise;
  } finally {
    if (inFlightDashboardSnapshots?.promise === promise) {
      inFlightDashboardSnapshots = null;
    }
  }
}

export async function getScreenViews(): Promise<ScreenView[]> {
  if (inFlightScreenViews) {
    return inFlightScreenViews;
  }

  const promise = requestJson<unknown>("/api/screen").then(normalizeScreenViews);
  inFlightScreenViews = promise;
  try {
    return await promise;
  } finally {
    if (inFlightScreenViews === promise) {
      inFlightScreenViews = null;
    }
  }
}

export async function getUniverses(): Promise<UniverseGroup[]> {
  const response = await getUniverseConfig();
  return response.groups;
}

export async function getUniverseConfig(): Promise<UniverseResponse> {
  const payload = await requestJson<unknown>("/api/universes");
  const record = isRecord(payload) ? payload : null;
  return {
    groups: normalizeUniverseGroups(payload),
    editable: readBoolean(record, "editable", false),
    managed_by: readFirstString(record, ["managed_by", "source"]),
    message: readFirstString(record, ["message", "summary", "description"]),
  };
}

export async function addUniverseTicker(
  groupId: string,
  ticker: string,
): Promise<void> {
  await requestJson<unknown>(
    `/api/universes/${encodeURIComponent(groupId)}/tickers`,
    {
      method: "POST",
      body: JSON.stringify({ tickers: [ticker.trim().toUpperCase()] }),
    },
  );
}

export async function replaceUniverseGroup(
  groupId: string,
  tickers: string[] = [],
): Promise<void> {
  await requestJson<unknown>(
    `/api/universes/${encodeURIComponent(groupId)}`,
    {
      method: "PUT",
      body: JSON.stringify({
        tickers: tickers.map((item) => item.trim().toUpperCase()).filter(Boolean),
      }),
    },
  );
}

export async function deleteUniverseTicker(
  groupId: string,
  ticker: string,
): Promise<void> {
  await requestJson<unknown>(
    `/api/universes/${encodeURIComponent(groupId)}/tickers/${encodeURIComponent(
      ticker.trim().toUpperCase(),
    )}`,
    { method: "DELETE" },
  );
}

export async function deleteUniverseGroup(groupId: string): Promise<void> {
  await requestJson<unknown>(
    `/api/universes/${encodeURIComponent(groupId)}`,
    { method: "DELETE" },
  );
}

export async function getRefreshRuns(): Promise<RefreshRun[]> {
  const payload = await requestJson<unknown>("/api/runs/refresh");
  return normalizeRefreshRuns(payload);
}

async function loadDashboardSnapshots(limit: number): Promise<DashboardData> {
  const status = await getMarketStatus();
  const tickers = (status.cached_tickers || []).slice(0, limit);
  if (tickers.length === 0) {
    return { status, snapshots: [] };
  }
  const snapshots = await getTickerSnapshots(tickers, limit);
  return { status, snapshots };
}

function normalizeTickers(tickers: string[]): string[] {
  return Array.from(
    new Set(
      tickers
        .map((ticker) => ticker.trim().toUpperCase())
        .filter(Boolean),
    ),
  );
}

function readSnapshotList(
  payload: SnapshotBatchResponse | TechnicalSnapshot[],
): TechnicalSnapshot[] {
  if (Array.isArray(payload)) {
    return payload.filter(isTechnicalSnapshot);
  }

  const candidates = [payload.snapshots, payload.data, payload.results, payload.items];
  for (const candidate of candidates) {
    const snapshots = readSnapshotCollection(candidate);
    if (snapshots.length > 0) {
      return snapshots;
    }
  }

  return readSnapshotCollection(payload);
}

function readSnapshotCollection(value: unknown): TechnicalSnapshot[] {
  if (Array.isArray(value)) {
    return value.filter(isTechnicalSnapshot);
  }
  if (isRecord(value)) {
    return Object.values(value).filter(isTechnicalSnapshot);
  }
  return [];
}

function alignSnapshotsToTickers(
  snapshots: TechnicalSnapshot[],
  tickers: string[],
): TechnicalSnapshot[] {
  const byTicker = new Map(
    snapshots.map((snapshot) => [snapshot.ticker.trim().toUpperCase(), snapshot]),
  );
  return tickers.map((ticker) => byTicker.get(ticker) || unavailableSnapshot(ticker));
}

function isTechnicalSnapshot(value: unknown): value is TechnicalSnapshot {
  return isRecord(value) && typeof value.ticker === "string";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function normalizeScreenViews(payload: unknown): ScreenView[] {
  const views = new Map<string, ScreenView>(
    DEFAULT_SCREEN_DEFINITIONS.map((definition) => [
      definition.id,
      { ...definition, rows: [] as ScreenResult[] },
    ]),
  );

  for (const view of readScreenViews(payload)) {
    const normalizedId = view.id || slugify(view.label);
    const defaultView = DEFAULT_SCREEN_DEFINITIONS.find(
      (definition) =>
        definition.id === normalizedId ||
        slugify(definition.label) === normalizedId ||
        screenKeyMatches(definition.id, normalizedId),
    );
    const id = defaultView?.id || normalizedId;
    views.set(id, {
      id,
      label: view.label || defaultView?.label || startCase(id),
      description: view.description || defaultView?.description,
      summary: view.summary,
      generated_at: view.generated_at,
      as_of: view.as_of,
      rows: view.rows,
    });
  }

  return [
    ...DEFAULT_SCREEN_DEFINITIONS.map((definition) => views.get(definition.id)!),
    ...Array.from(views.values()).filter(
      (view) =>
        !DEFAULT_SCREEN_DEFINITIONS.some((definition) => definition.id === view.id),
    ),
  ];
}

function readScreenViews(payload: unknown): ScreenView[] {
  if (Array.isArray(payload)) {
    const rows = normalizeScreenRows(payload);
    return rows.length > 0
      ? [{ ...DEFAULT_SCREEN_DEFINITIONS[0], rows }]
      : payload.flatMap((item, index) => {
          const view = normalizeScreenView(item, `view-${index + 1}`);
          return view ? [view] : [];
        });
  }

  if (!isRecord(payload)) {
    return [];
  }

  for (const field of SCREEN_VIEW_FIELDS) {
    const value = payload[field];
    if (Array.isArray(value)) {
      return value.flatMap((item, index) => {
        const view = normalizeScreenView(item, `view-${index + 1}`);
        return view ? [view] : [];
      });
    }
    if (isRecord(value)) {
      return normalizeScreenViewMap(value);
    }
  }

  if (isRecord(payload.results) && normalizeScreenViewMap(payload.results).length > 0) {
    return normalizeScreenViewMap(payload.results);
  }

  const mappedViews = normalizeScreenViewMap(payload);
  if (mappedViews.length > 0) {
    return mappedViews;
  }

  const rows = normalizeScreenRows(payload);
  return rows.length > 0 ? [{ ...DEFAULT_SCREEN_DEFINITIONS[0], rows }] : [];
}

function normalizeScreenViewMap(record: Record<string, unknown>): ScreenView[] {
  return Object.entries(record).flatMap(([key, value]) => {
    if (isScreenMetadataField(key)) {
      return [];
    }
    const view = normalizeScreenView(value, key);
    return view ? [view] : [];
  });
}

function normalizeScreenView(value: unknown, fallbackId: string): ScreenView | null {
  if (isRecord(value)) {
    const rows = normalizeScreenRows(value);
    if (rows.length === 0 && !hasAnyField(value, SCREEN_ROW_FIELDS)) {
      return null;
    }
    const label = readFirstString(value, ["label", "name", "title"]) || startCase(fallbackId);
    return {
      id: slugify(readFirstString(value, ["id", "key", "slug"]) || fallbackId),
      label,
      description: readFirstString(value, ["description", "criteria"]),
      summary: readFirstString(value, ["summary", "message"]),
      generated_at: readFirstString(value, ["generated_at", "created_at"]),
      as_of: readFirstString(value, ["as_of", "latest_as_of"]) || null,
      rows,
    };
  }

  const rows = normalizeScreenRows(value);
  return rows.length > 0
    ? {
        id: slugify(fallbackId),
        label: startCase(fallbackId),
        rows,
      }
    : null;
}

function normalizeScreenRows(value: unknown): ScreenResult[] {
  if (Array.isArray(value)) {
    return value.flatMap((item) => normalizeScreenResult(item));
  }

  if (!isRecord(value)) {
    return [];
  }

  for (const field of SCREEN_ROW_FIELDS) {
    const rows = normalizeScreenRows(value[field]);
    if (rows.length > 0) {
      return rows;
    }
  }

  return Object.entries(value).flatMap(([key, item]) => {
    if (isScreenMetadataField(key)) {
      return [];
    }
    if (isRecord(item)) {
      return normalizeScreenResult({ ticker: key, ...item });
    }
    if (typeof item === "string") {
      return normalizeScreenResult(item);
    }
    return [];
  });
}

function normalizeScreenResult(value: unknown): ScreenResult[] {
  if (typeof value === "string" && value.trim()) {
    return [{ ticker: value.trim().toUpperCase() }];
  }
  if (!isRecord(value)) {
    return [];
  }
  const ticker = readFirstString(value, ["ticker", "symbol"]);
  return ticker ? [{ ...value, ticker: ticker.toUpperCase() } as ScreenResult] : [];
}

function normalizeUniverseGroups(payload: unknown): UniverseGroup[] {
  if (Array.isArray(payload)) {
    return payload.flatMap((item, index) => normalizeUniverseGroup(item, `group-${index + 1}`));
  }

  if (!isRecord(payload)) {
    return [];
  }

  const groupedValue = readFirstRecord(payload, UNIVERSE_GROUP_FIELDS);
  if (groupedValue) {
    const meta = isRecord(payload.group_meta) ? payload.group_meta : {};
    return Object.entries(groupedValue)
      .flatMap(([key, value]) => normalizeUniverseGroup(value, key, meta[key]));
  }

  return Object.entries(payload)
    .flatMap(([key, value]) => normalizeUniverseGroup(value, key));
}

function normalizeUniverseGroup(
  value: unknown,
  fallbackId: string,
  metaValue?: unknown,
): UniverseGroup[] {
  const meta = isRecord(metaValue) ? metaValue : {};
  if (Array.isArray(value)) {
    const tickers = normalizeTickerList(value);
    return [
      {
        id: fallbackId,
        name: readFirstString(meta, ["name", "label", "title"]) || startCase(fallbackId),
        tickers,
        description: readFirstString(meta, ["description", "summary"]),
      },
    ];
  }

  if (!isRecord(value)) {
    return [];
  }

  const tickers = readTickerListFromRecord(value);
  const id = readFirstString(value, ["id", "key", "slug", "name", "label"]) || fallbackId;
  const name =
    readFirstString(value, ["name", "label", "title"]) ||
    readFirstString(meta, ["name", "label", "title"]) ||
    startCase(fallbackId);
  return [
    {
      id,
      name,
      tickers,
      description:
        readFirstString(value, ["description", "summary"]) ||
        readFirstString(meta, ["description", "summary"]),
      updated_at: readFirstString(value, ["updated_at", "modified_at"]) || null,
      source: readFirstString(value, ["source"]),
    },
  ];
}

function normalizeRefreshRuns(payload: unknown): RefreshRun[] {
  const source = readFirstList(payload, RUN_LIST_FIELDS);
  if (!source) {
    return [];
  }
  return source
    .map((item, index) => normalizeRefreshRun(item, index))
    .filter((run): run is RefreshRun => Boolean(run));
}

function normalizeRefreshRun(value: unknown, index: number): RefreshRun | null {
  if (!isRecord(value)) {
    return null;
  }

  const id =
    readFirstString(value, ["id", "run_id", "key"]) ||
    readFirstString(value, ["started_at", "created_at"]) ||
    `run-${index + 1}`;
  const resultIssues = readRunResultIssues(value.results);
  const failures = [
    ...readRunIssuesFromFields(value, RUN_FAILURE_FIELDS, "failed"),
    ...resultIssues.filter((issue) =>
      ["failed", "error", "unavailable"].includes((issue.status || "").toLowerCase()),
    ),
  ];
  const staleTickers = [
    ...readRunIssuesFromFields(value, RUN_STALE_FIELDS, "stale"),
    ...resultIssues.filter((issue) => (issue.status || "").toLowerCase() === "stale"),
  ];

  return {
    id,
    status:
      normalizeStatus(readFirstString(value, ["status", "state", "result"])) ||
      (failures.length > 0 ? "partial" : "ok"),
    started_at: readFirstString(value, ["started_at", "started", "created_at"]) || null,
    finished_at: readFirstString(value, ["finished_at", "completed_at", "ended_at"]) || null,
    latest_as_of: readFirstString(value, ["latest_as_of", "as_of"]) || null,
    period: readFirstString(value, ["period", "range"]),
    universe: readFirstString(value, ["universe", "group"]),
    total: readFirstNumber(value, ["total", "ticker_count", "requested"]),
    succeeded: readFirstNumber(value, ["succeeded", "success", "ok"]),
    failed: readFirstNumber(value, ["failed_count", "failed", "errors"]),
    stale: readFirstNumber(value, ["stale_count", "stale"]),
    summary: readFirstString(value, ["summary", "message", "description"]),
    failures: dedupeIssues(failures),
    stale_tickers: dedupeIssues(staleTickers),
  };
}

function readRunResultIssues(value: unknown): RunIssue[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.flatMap((item, index) => {
    if (!isRecord(item)) {
      return [];
    }
    const status = normalizeStatus(readFirstString(item, ["status", "state", "result"]));
    if (!status || status === "ok") {
      return [];
    }
    const ticker = readFirstString(item, ["ticker", "symbol"]);
    return [
      {
        id: `${index}-${ticker || status}`,
        ticker: ticker?.toUpperCase(),
        status,
        message: readFirstString(item, ["error", "message", "warning", "reason"]),
        as_of: readFirstString(item, ["as_of", "latest_as_of"]) || null,
      },
    ];
  });
}

function readRunIssuesFromFields(
  record: Record<string, unknown>,
  fields: string[],
  fallbackStatus: string,
): RunIssue[] {
  for (const field of fields) {
    const issues = normalizeRunIssues(record[field], fallbackStatus);
    if (issues.length > 0) {
      return issues;
    }
  }
  return [];
}

function normalizeRunIssues(value: unknown, fallbackStatus: string): RunIssue[] {
  if (Array.isArray(value)) {
    return value.flatMap((item, index) => normalizeRunIssue(item, fallbackStatus, index));
  }
  if (typeof value === "string") {
    return normalizeRunIssue(value, fallbackStatus, 0);
  }
  if (isRecord(value)) {
    return Object.entries(value).flatMap(([key, item], index) =>
      normalizeRunIssue(
        isRecord(item) ? { ticker: key, ...item } : { ticker: key, message: item },
        fallbackStatus,
        index,
      ),
    );
  }
  return [];
}

function normalizeRunIssue(
  value: unknown,
  fallbackStatus: string,
  index: number,
): RunIssue[] {
  if (typeof value === "string" && value.trim()) {
    return [{ id: `${index}-${value}`, ticker: value.trim().toUpperCase(), status: fallbackStatus }];
  }
  if (!isRecord(value)) {
    return [];
  }
  const ticker = readFirstString(value, ["ticker", "symbol"]);
  return [
    {
      id: `${index}-${ticker || fallbackStatus}`,
      ticker: ticker?.toUpperCase(),
      status: normalizeStatus(readFirstString(value, ["status", "state"])) || fallbackStatus,
      message: readFirstString(value, ["message", "error", "warning", "reason"]),
      as_of: readFirstString(value, ["as_of", "latest_as_of"]) || null,
    },
  ];
}

function dedupeIssues(issues: RunIssue[]): RunIssue[] {
  const seen = new Set<string>();
  return issues.filter((issue) => {
    const key = `${issue.ticker || issue.id}:${issue.status || ""}:${issue.message || ""}`;
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

function readFirstList(record: unknown, fields: string[]): unknown[] | null {
  if (Array.isArray(record)) {
    return record;
  }
  if (!isRecord(record)) {
    return null;
  }
  for (const field of fields) {
    if (Array.isArray(record[field])) {
      return record[field];
    }
  }
  return null;
}

function readFirstRecord(
  record: Record<string, unknown>,
  fields: string[],
): Record<string, unknown> | null {
  for (const field of fields) {
    const value = record[field];
    if (isRecord(value)) {
      return value;
    }
  }
  return null;
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

function readFirstString(record: Record<string, unknown> | null, fields: string[]): string | undefined {
  if (!record) {
    return undefined;
  }
  for (const field of fields) {
    const value = record[field];
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }
  }
  return undefined;
}

function readBoolean(
  record: Record<string, unknown> | null,
  field: string,
  fallback: boolean,
): boolean {
  if (!record) {
    return fallback;
  }
  const value = record[field];
  if (typeof value === "boolean") {
    return value;
  }
  if (typeof value === "string") {
    return ["1", "true", "yes", "on"].includes(value.trim().toLowerCase());
  }
  return fallback;
}

function readFirstNumber(
  record: Record<string, unknown>,
  fields: string[],
): number | null {
  for (const field of fields) {
    const value = record[field];
    if (typeof value === "number" && Number.isFinite(value)) {
      return value;
    }
  }
  return null;
}

function normalizeStatus(status: string | undefined): string | undefined {
  if (!status) {
    return undefined;
  }
  const normalized = status.toLowerCase();
  if (["pass", "passed", "healthy", "success", "complete", "completed"].includes(normalized)) {
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
            const ticker = readFirstString(item, ["ticker", "symbol"]);
            return ticker ? [ticker] : [];
          }
          return [];
        })
        .map((ticker) => ticker.trim().toUpperCase())
        .filter(Boolean),
    ),
  );
}

function hasAnyField(record: Record<string, unknown>, fields: string[]): boolean {
  return fields.some((field) => record[field] !== undefined);
}

function isScreenMetadataField(key: string): boolean {
  return [
    "status",
    "summary",
    "message",
    "generated_at",
    "as_of",
    "latest_as_of",
    "count",
  ].includes(key);
}

function screenKeyMatches(defaultId: string, value: string): boolean {
  const compactDefault = defaultId.replace(/_/g, "");
  const compactValue = value.replace(/-/g, "").replace(/_/g, "");
  return compactDefault === compactValue;
}

function slugify(value: string): string {
  return value.trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
}

function startCase(value: string): string {
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}
