export function formatPrice(value: number | null | undefined, currency = "USD"): string {
  if (value == null || !Number.isFinite(value)) {
    return "N/A";
  }
  const symbol = currency === "USD" ? "$" : "";
  return `${symbol}${value.toLocaleString("en-US", {
    maximumFractionDigits: value >= 100 ? 1 : 2,
    minimumFractionDigits: value >= 100 ? 1 : 2,
  })}`;
}

export function formatNumber(value: number | null | undefined, digits = 2): string {
  if (value == null || !Number.isFinite(value)) {
    return "N/A";
  }
  return value.toLocaleString("en-US", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  });
}

export function formatPercent(value: number | null | undefined, digits = 1): string {
  if (value == null || !Number.isFinite(value)) {
    return "N/A";
  }
  return `${(value * 100).toLocaleString("en-US", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  })}%`;
}

export function formatCompactPercent(value: number | null | undefined): string {
  return formatPercent(value, 0);
}

export function formatScore(value: number | null | undefined, digits = 1): string {
  if (value == null || !Number.isFinite(value)) {
    return "N/A";
  }
  return value.toLocaleString("en-US", {
    maximumFractionDigits: digits,
    minimumFractionDigits: Number.isInteger(value) ? 0 : digits,
  });
}

export function formatLevelList(levels: number[] | undefined, currency = "USD"): string {
  if (!levels || levels.length === 0) {
    return "N/A";
  }
  return levels.slice(0, 3).map((level) => formatPrice(level, currency)).join(" / ");
}

export function qualityClass(status: string | undefined): string {
  if (status === "ok") {
    return "is-positive";
  }
  if (status === "partial" || status === "stale") {
    return "is-warning";
  }
  if (status === "unavailable") {
    return "is-negative";
  }
  return "is-muted";
}

export function trendClass(trend: string | undefined): string {
  if (trend === "bullish" || trend === "constructive") {
    return "is-positive";
  }
  if (trend === "bearish") {
    return "is-negative";
  }
  return "is-muted";
}

export function normalizeLabel(value: string | null | undefined): string {
  if (!value) {
    return "N/A";
  }
  return value.replaceAll("_", " ");
}
