import { describe, expect, it } from "vitest";

import {
  formatLevelList,
  formatPercent,
  formatPrice,
  formatScore,
  normalizeLabel,
  qualityClass,
  trendClass,
} from "./formatters";

describe("market formatters", () => {
  it("formats price and percent values", () => {
    expect(formatPrice(48.55, "USD")).toBe("$48.55");
    expect(formatPercent(-0.0764)).toBe("-7.6%");
    expect(formatScore(82)).toBe("82");
    expect(formatScore(82.44)).toBe("82.4");
    expect(formatScore(undefined)).toBe("N/A");
  });

  it("formats support and resistance levels", () => {
    expect(formatLevelList([47.17, 58.18], "USD")).toBe("$47.17 / $58.18");
    expect(formatLevelList([], "USD")).toBe("N/A");
  });

  it("normalizes labels and visual classes", () => {
    expect(normalizeLabel("near_support")).toBe("near support");
    expect(qualityClass("ok")).toBe("is-positive");
    expect(trendClass("bearish")).toBe("is-negative");
  });
});
