export type QualityStatus = "ok" | "partial" | "unavailable" | "stale" | string;

export interface CacheEntry {
  ticker: string;
  rows: number;
  as_of: string | null;
  status: QualityStatus;
  stale_days?: number | null;
  warning?: string;
}

export interface MarketStatus {
  [key: string]: unknown;
  status: QualityStatus;
  cache_status?: QualityStatus;
  price_history_files: number;
  cached_tickers: string[];
  cached_ticker_count?: number;
  latest_as_of: string | null;
  last_refresh?: string | null;
  stale_count: number;
  stale_tickers: string[];
  unavailable_count?: number;
  snapshots: number;
  snapshot_count?: number;
  snapshot_tickers: string[];
  price_history_dir?: string;
  snapshot_dir?: string;
  entries: CacheEntry[];
  quality?: unknown;
  data_quality?: unknown;
  data_quality_report?: DataQualityReport;
  error?: string;
  groups?: unknown;
  universes?: unknown;
  ticker_groups?: unknown;
  cached_groups?: unknown;
}

export interface DataQuality {
  status: QualityStatus;
  warnings?: string[];
  source?: string;
  rows?: number;
  as_of?: string | null;
  generated_at?: string;
  summary?: string;
  checks?: unknown;
  stale?: unknown;
  short_history?: unknown;
  missing_price?: unknown;
  missing_volume?: unknown;
  invalid_values?: unknown;
}

export interface DataQualityReport {
  [key: string]: unknown;
  status?: QualityStatus;
  checks?: unknown;
  generated_at?: string;
  warnings?: string[];
  summary?: string;
  stale?: unknown;
  short_history?: unknown;
  missing_price?: unknown;
  missing_volume?: unknown;
  invalid_values?: unknown;
}

export interface RelativeStrengthPeriod {
  return: number | null;
  benchmark_return: number | null;
  spread: number | null;
}

export interface RelativeStrength {
  benchmark?: string;
  status?: string;
  periods?: Record<string, RelativeStrengthPeriod>;
}

export interface VolumeSignal {
  status?: string;
  latest_volume?: number | null;
  avg_20d?: number | null;
  ratio?: number | null;
}

export interface TechnicalSnapshot {
  ticker: string;
  as_of: string | null;
  currency: string;
  price: number | null;
  ma20: number | null;
  ma50: number | null;
  ma200: number | null;
  distance_from_ma20: number | null;
  distance_from_ma50: number | null;
  distance_from_ma200: number | null;
  rsi14: number | null;
  atr14: number | null;
  return_1m: number | null;
  return_3m: number | null;
  return_6m: number | null;
  return_ytd: number | null;
  week52_high: number | null;
  week52_low: number | null;
  week52_position: number | null;
  volatility_20d?: number | null;
  volatility_60d?: number | null;
  beta_vs_spy?: number | null;
  max_drawdown_6m?: number | null;
  max_drawdown_1y?: number | null;
  distance_from_52w_high?: number | null;
  distance_from_52w_low?: number | null;
  latest_gap_pct?: number | null;
  liquidity_score?: number | null;
  trend_score?: number | null;
  support_levels: number[];
  resistance_levels: number[];
  trend: string;
  breakout_status: string;
  relative_strength_vs_spy?: RelativeStrength;
  volume_signal?: VolumeSignal;
  data_quality: DataQuality;
}

export interface SnapshotBatchResponse {
  [key: string]: unknown;
  snapshots?: TechnicalSnapshot[] | Record<string, TechnicalSnapshot>;
  data?: TechnicalSnapshot[] | Record<string, TechnicalSnapshot>;
  results?: TechnicalSnapshot[] | Record<string, TechnicalSnapshot>;
  items?: TechnicalSnapshot[] | Record<string, TechnicalSnapshot>;
}

export type ScreenResult = Partial<TechnicalSnapshot> & {
  ticker: string;
  as_of?: string | null;
  currency?: string;
  data_quality?: Partial<DataQuality>;
};

export interface ScreenView {
  id: string;
  label: string;
  description?: string;
  summary?: string;
  generated_at?: string;
  as_of?: string | null;
  rows: ScreenResult[];
}

export interface UniverseGroup {
  id: string;
  name: string;
  tickers: string[];
  description?: string;
  updated_at?: string | null;
  source?: string;
}

export interface UniverseResponse {
  groups: UniverseGroup[];
  editable: boolean;
  managed_by?: string;
  message?: string;
}

export interface RunIssue {
  id: string;
  ticker?: string;
  status?: string;
  message?: string;
  as_of?: string | null;
}

export interface RefreshRun {
  id: string;
  status: QualityStatus;
  started_at?: string | null;
  finished_at?: string | null;
  latest_as_of?: string | null;
  period?: string;
  universe?: string;
  total?: number | null;
  succeeded?: number | null;
  failed?: number | null;
  stale?: number | null;
  summary?: string;
  failures: RunIssue[];
  stale_tickers: RunIssue[];
}

export interface ChartPoint {
  date: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
}

export interface ChartSeriesPoint {
  date: string;
  value: number | null;
}

export interface TechnicalChart {
  ticker: string;
  as_of: string | null;
  currency: string;
  has_image: boolean;
  points: ChartPoint[];
  ma20: ChartSeriesPoint[];
  ma50: ChartSeriesPoint[];
  ma200: ChartSeriesPoint[];
  support_levels: number[];
  resistance_levels: number[];
  data_quality: DataQuality;
}

export interface DashboardData {
  status: MarketStatus;
  snapshots: TechnicalSnapshot[];
}
