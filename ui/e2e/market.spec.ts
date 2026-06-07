import { expect, test } from "@playwright/test";

const statusPayload = {
  status: "ok",
  price_history_files: 13,
  cached_tickers: ["AAPL", "BSX"],
  latest_as_of: "2026-06-05",
  stale_count: 0,
  stale_tickers: [],
  snapshots: 0,
  snapshot_tickers: [],
  entries: [],
  groups: {
    "Mega Cap": ["AAPL"],
    Medtech: ["BSX"],
  },
  data_quality: {
    status: "ok",
    issue_count: 1,
    summary: "2 cached snapshots passed required checks.",
  },
  data_quality_report: {
    status: "partial",
    summary: "2 cached snapshots passed required checks.",
    checks: {
      stale: {
        status: "ok",
        message: "latest as of 2026-06-05",
        count: 0,
      },
      short_history: {
        label: "short history",
        status: "warning",
        message: "BSX has partial history",
        tickers: ["BSX"],
        count: 1,
      },
      missing_price: {
        status: "ok",
        count: 0,
      },
      missing_volume: {
        status: "warning",
        message: "AAPL is missing volume on one cached row",
        tickers: ["AAPL"],
        count: 1,
      },
      invalid_values: {
        status: "ok",
        count: 0,
      },
    },
  },
};

const aaplSnapshot = {
  ticker: "AAPL",
  as_of: "2026-06-05",
  currency: "USD",
  price: 307.3,
  ma20: 304.2,
  ma50: 281.1,
  ma200: 264.9,
  distance_from_ma20: 0.0102,
  distance_from_ma50: 0.0932,
  distance_from_ma200: 0.1598,
  rsi14: 58.3,
  atr14: 5.73,
  return_1m: 0.07,
  return_3m: 0.19,
  return_6m: 0.08,
  return_ytd: 0.13,
  week52_high: 316.9,
  week52_low: 196.2,
  week52_position: 0.921,
  volatility_20d: 0.214,
  volatility_60d: 0.287,
  beta_vs_spy: 1.08,
  max_drawdown_6m: -0.112,
  max_drawdown_1y: -0.184,
  distance_from_52w_high: -0.031,
  distance_from_52w_low: 0.566,
  latest_gap_pct: 0.012,
  liquidity_score: 76.4,
  trend_score: 82.5,
  support_levels: [305.0, 267.0],
  resistance_levels: [316.9],
  trend: "bullish",
  breakout_status: "near_support",
  relative_strength_vs_spy: {
    benchmark: "SPY",
    status: "underperforming",
    periods: {
      "3m": {
        return: 0.19,
        benchmark_return: 0.0969,
        spread: 0.0931,
      },
    },
  },
  volume_signal: {
    status: "normal",
    latest_volume: 20256000,
    avg_20d: 22696815,
    ratio: 0.89,
  },
  data_quality: {
    status: "ok",
    warnings: [],
  },
};

const bsxSnapshot = {
  ...aaplSnapshot,
  ticker: "BSX",
  price: 48.55,
  trend: "bearish",
  volatility_20d: undefined,
  volatility_60d: undefined,
  beta_vs_spy: undefined,
  max_drawdown_6m: undefined,
  max_drawdown_1y: undefined,
  distance_from_52w_high: undefined,
  distance_from_52w_low: undefined,
  latest_gap_pct: undefined,
  liquidity_score: undefined,
  trend_score: undefined,
  support_levels: [47.17],
  resistance_levels: [58.18],
  data_quality: {
    status: "partial",
    warnings: ["History is shorter than the preferred lookback window."],
  },
};

const chartPayload = {
  ticker: "AAPL",
  as_of: "2026-06-05",
  currency: "USD",
  has_image: true,
  points: [
    { date: "2026-06-03", open: 302, high: 309, low: 300, close: 304.1, volume: 1000 },
    { date: "2026-06-04", open: 304, high: 310, low: 303, close: 306.2, volume: 1200 },
    { date: "2026-06-05", open: 306, high: 312, low: 305, close: 307.3, volume: 1500 },
  ],
  ma20: [
    { date: "2026-06-03", value: 303.1 },
    { date: "2026-06-04", value: 303.7 },
    { date: "2026-06-05", value: 304.2 },
  ],
  ma50: [],
  ma200: [],
  support_levels: [305.0],
  resistance_levels: [316.9],
  data_quality: {
    status: "ok",
    warnings: [],
  },
};

const screenPayload = {
  generated_at: "2026-06-06T12:00:00Z",
  views: {
    breakout_watch: {
      label: "Breakout Watch",
      summary: "Momentum names close to resistance.",
      rows: [aaplSnapshot],
    },
    near_support: {
      label: "Near Support",
      rows: [bsxSnapshot],
    },
    relative_strength_leaders: {
      label: "Relative Strength Leaders",
      rows: [aaplSnapshot],
    },
    oversold_watch: {
      label: "Oversold Watch",
      rows: [bsxSnapshot],
    },
  },
};

const runsPayload = {
  runs: [
    {
      id: "run-2026-06-06",
      status: "partial",
      started_at: "2026-06-06T09:00:00Z",
      finished_at: "2026-06-06T09:05:00Z",
      period: "5y",
      universe: "all",
      total: 3,
      succeeded: 2,
      failed_count: 1,
      stale_count: 1,
      summary: "2 refreshed, 1 failed, 1 stale cache preserved.",
      failures: [{ ticker: "BSX", message: "provider timeout", status: "failed" }],
      stale_tickers: [{ ticker: "AAPL", message: "latest cache kept", as_of: "2026-06-05" }],
    },
    {
      id: "run-2026-06-05",
      status: "ok",
      started_at: "2026-06-05T09:00:00Z",
      total: 2,
      succeeded: 2,
      failed_count: 0,
      stale_count: 0,
      summary: "All configured tickers refreshed.",
    },
  ],
};

test("shows market matrix without chart and opens ticker detail chart", async ({ page }) => {
  let batchRequests = 0;
  let tickerSnapshotRequests = 0;
  let chartRequests = 0;
  await page.route("**/api/status", (route) => route.fulfill({ json: statusPayload }));
  await page.route("**/api/snapshots**", (route) => {
    batchRequests += 1;
    const url = new URL(route.request().url());
    expect(url.searchParams.get("tickers")).toBe("AAPL,BSX");
    expect(url.searchParams.get("limit")).toBe("80");
    return route.fulfill({ json: { snapshots: [aaplSnapshot, bsxSnapshot] } });
  });
  await page.route("**/api/snapshot/**", (route) => {
    tickerSnapshotRequests += 1;
    return route.fulfill({
      json: route.request().url().includes("/BSX") ? bsxSnapshot : aaplSnapshot,
    });
  });
  await page.route("**/api/chart/**", (route) => {
    chartRequests += 1;
    return route.fulfill({
      json: route.request().url().includes("/BSX")
        ? { ...chartPayload, ticker: "BSX" }
        : chartPayload,
    });
  });

  await page.goto("/");
  await expect(page).toHaveURL(/\/market$/);
  await expect(page.getByRole("heading", { name: "Technical snapshots from local market history" })).toBeVisible();
  await expect(page.getByText("2 of 2 loaded")).toBeVisible();
  await expect(page.getByTestId("market-quality-panel")).toBeVisible();
  await expect(page.getByText("Snapshot checks")).toBeVisible();
  await expect(page.getByText("5 checks")).toBeVisible();
  await expect(page.getByText("latest as of 2026-06-05")).toBeVisible();
  const qualityPanel = page.getByTestId("market-quality-panel");
  await expect(qualityPanel.getByText("short history").first()).toBeVisible();
  await expect(qualityPanel.getByText("missing price")).toBeVisible();
  await expect(page.getByTestId("quality-problem-list")).toBeVisible();
  await expect(page.getByTestId("quality-problem-list").getByRole("link", { name: "BSX" })).toBeVisible();
  await page.getByLabel("Issue type").selectOption("missing-volume");
  await expect(page.getByTestId("quality-problem-list").getByRole("link", { name: "AAPL" })).toBeVisible();
  await expect(page.getByTestId("quality-problem-list").getByRole("link", { name: "BSX" })).toHaveCount(0);
  await expect(page.getByText("Selected chart")).toHaveCount(0);
  await expect(page.getByTestId("ticker-chart")).toHaveCount(0);
  await expect(page.locator("canvas")).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Market Matrix" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Screener" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Universes" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Runs" })).toBeVisible();
  expect(batchRequests).toBe(1);
  expect(tickerSnapshotRequests).toBe(0);
  expect(chartRequests).toBe(0);
  const aaplRow = page.getByTestId("market-row-AAPL");
  await expect(aaplRow).toBeVisible();
  await expect(page.getByRole("cell", { name: "$307.3" })).toBeVisible();
  await expect(aaplRow.getByText("bullish")).toBeVisible();
  await expect(aaplRow.getByText("Score 82.5")).toBeVisible();
  await expect(aaplRow.getByText("20D 21.4%")).toBeVisible();
  await expect(aaplRow.getByText("Beta 1.08")).toBeVisible();
  await expect(aaplRow.getByText("6M -11.2%")).toBeVisible();
  await expect(aaplRow.getByText("High -3.1%")).toBeVisible();
  await expect(aaplRow.getByText("Low 56.6%")).toBeVisible();
  await expect(aaplRow.getByText("Score 76.4")).toBeVisible();
  await expect(aaplRow.getByText("Gap 1.2%")).toBeVisible();
  await expect(aaplRow.getByText("$305.0")).toBeVisible();

  await aaplRow.getByText("AAPL").click();
  await expect(page).toHaveURL(/\/market\/AAPL$/);
  await expect(page.getByText("Selected chart")).toBeVisible();
  await expect(page.getByRole("heading", { name: "AAPL" }).first()).toBeVisible();
  await expect(page.getByTestId("ticker-chart")).toBeVisible();
  const metricsSection = page.getByTestId("detail-metrics-section");
  await expect(page.getByText("Deterministic metrics", { exact: true })).toBeVisible();
  await expect(metricsSection.getByText("Trend score")).toBeVisible();
  await expect(metricsSection.getByText("82.5")).toBeVisible();
  await expect(metricsSection.getByText("20D volatility")).toBeVisible();
  await expect(metricsSection.getByText("21.4%")).toBeVisible();
  await expect(metricsSection.getByText("Beta vs SPY")).toBeVisible();
  await expect(metricsSection.getByText("1.08")).toBeVisible();
  await expect(metricsSection.getByText("Latest gap")).toBeVisible();
  await expect(metricsSection.getByText("1.2%", { exact: true })).toBeVisible();
  await expect(page.getByText("Relative strength", { exact: true })).toBeVisible();
  await expect(page.getByText("Volume", { exact: true })).toBeVisible();
  await expect(page.getByText("Quality warnings", { exact: true })).toBeVisible();
  expect(tickerSnapshotRequests).toBeGreaterThan(0);
  expect(chartRequests).toBe(1);
});

test("filters and sorts market matrix without requesting charts", async ({ page }) => {
  let batchRequests = 0;
  let tickerSnapshotRequests = 0;
  let chartRequests = 0;
  await page.route("**/api/status", (route) => route.fulfill({ json: statusPayload }));
  await page.route("**/api/snapshots**", (route) => {
    batchRequests += 1;
    const url = new URL(route.request().url());
    expect(url.searchParams.get("tickers")).toBe("AAPL,BSX");
    expect(url.searchParams.get("limit")).toBe("80");
    return route.fulfill({ json: { snapshots: [aaplSnapshot, bsxSnapshot] } });
  });
  await page.route("**/api/snapshot/**", (route) => {
    tickerSnapshotRequests += 1;
    return route.fulfill({
      json: route.request().url().includes("/BSX") ? bsxSnapshot : aaplSnapshot,
    });
  });
  await page.route("**/api/chart/**", (route) => {
    chartRequests += 1;
    return route.fulfill({ json: chartPayload });
  });

  await page.goto("/market");
  const tickers = page.locator('[data-testid^="market-row-"] .ticker-cell');
  await expect(tickers).toHaveText(["AAPL", "BSX"]);
  expect(batchRequests).toBe(1);
  expect(tickerSnapshotRequests).toBe(0);

  await page.getByLabel("Sort by").selectOption("price");
  await expect(tickers).toHaveText(["BSX", "AAPL"]);
  await page.getByRole("button", { name: "Sort ascending" }).click();
  await expect(tickers).toHaveText(["AAPL", "BSX"]);
  await page.getByLabel("Sort by").selectOption("trend_score");
  await expect(tickers).toHaveText(["AAPL", "BSX"]);

  await page.getByLabel("Search tickers").fill("BSX");
  await expect(page.getByTestId("market-row-AAPL")).toHaveCount(0);
  await expect(page.getByTestId("market-row-BSX")).toBeVisible();

  await page.getByRole("button", { name: "Reset" }).click();
  await page.getByLabel("Trend").selectOption("bullish");
  await expect(page.getByTestId("market-row-AAPL")).toBeVisible();
  await expect(page.getByTestId("market-row-BSX")).toHaveCount(0);

  await page.getByRole("button", { name: "Reset" }).click();
  await page.getByLabel("Data quality").selectOption("partial");
  await expect(page.getByTestId("market-row-AAPL")).toHaveCount(0);
  await expect(page.getByTestId("market-row-BSX")).toBeVisible();

  await page.getByRole("button", { name: "Reset" }).click();
  await page.getByLabel("Universe").selectOption("groups:medtech");
  await expect(page.getByTestId("market-row-AAPL")).toHaveCount(0);
  await expect(page.getByTestId("market-row-BSX")).toBeVisible();
  await expect(page.getByTestId("ticker-chart")).toHaveCount(0);
  expect(batchRequests).toBe(1);
  expect(tickerSnapshotRequests).toBe(0);
  expect(chartRequests).toBe(0);
});

test("shows screener views and opens result rows on ticker detail", async ({ page }) => {
  let screenRequests = 0;
  let chartRequests = 0;
  await page.route("**/api/screen", (route) => {
    screenRequests += 1;
    return route.fulfill({ json: screenPayload });
  });
  await page.route("**/api/status", (route) => route.fulfill({ json: statusPayload }));
  await page.route("**/api/snapshot/**", (route) =>
    route.fulfill({
      json: route.request().url().includes("/BSX") ? bsxSnapshot : aaplSnapshot,
    }),
  );
  await page.route("**/api/chart/**", (route) => {
    chartRequests += 1;
    return route.fulfill({ json: chartPayload });
  });

  await page.goto("/screen");
  await expect(page.getByRole("heading", { name: "Default technical watchlists" })).toBeVisible();
  await expect(page.getByRole("tab", { name: /Breakout Watch/ })).toBeVisible();
  await expect(page.getByRole("tab", { name: /Near Support/ })).toBeVisible();
  await expect(page.getByRole("tab", { name: /Relative Strength Leaders/ })).toBeVisible();
  await expect(page.getByRole("tab", { name: /Oversold Watch/ })).toBeVisible();
  await expect(page.getByTestId("screen-row-AAPL")).toBeVisible();
  await expect(page.getByText("Momentum names close to resistance.")).toBeVisible();
  expect(screenRequests).toBe(1);
  expect(chartRequests).toBe(0);

  await page.getByRole("tab", { name: /Near Support/ }).click();
  await expect(page.getByTestId("screen-row-BSX")).toBeVisible();
  await page.getByLabel("Search screen results").fill("AAPL");
  await expect(page.getByText("No screen results match the current search.")).toBeVisible();
  await page.getByLabel("Search screen results").fill("");

  await page.getByTestId("screen-row-BSX").getByText("BSX").click();
  await expect(page).toHaveURL(/\/market\/BSX$/);
  await expect(page.getByText("Selected chart")).toBeVisible();
  await expect(page.getByTestId("ticker-chart")).toBeVisible();
  expect(chartRequests).toBe(1);
});

test("manages universes without triggering refresh", async ({ page, context }) => {
  let universes = [
    {
      id: "Mega Cap",
      name: "Mega Cap",
      tickers: ["AAPL"],
      description: "Liquid large-cap watchlist.",
    },
    {
      id: "Medtech",
      name: "Medtech",
      tickers: ["BSX"],
    },
  ];
  let addRequests = 0;
  let deleteRequests = 0;
  let refreshRequests = 0;

  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.route("**/api/refresh**", (route) => {
    refreshRequests += 1;
    return route.abort();
  });
  await page.route("**/api/snapshots/refresh**", (route) => {
    refreshRequests += 1;
    return route.abort();
  });
  await page.route("**/api/universes", (route) => route.fulfill({ json: { groups: universes } }));
  await page.route("**/api/universes/**", async (route) => {
    const url = new URL(route.request().url());
    const method = route.request().method();
    const addMatch = url.pathname.match(/\/api\/universes\/(.+)\/tickers$/);
    const deleteMatch = url.pathname.match(/\/api\/universes\/(.+)\/tickers\/([^/]+)$/);

    if (method === "POST" && addMatch) {
      addRequests += 1;
      const groupId = decodeURIComponent(addMatch[1]);
      const body = route.request().postDataJSON() as { tickers: string[] };
      const tickers = (body.tickers || []).map((ticker) => ticker.toUpperCase());
      universes = universes.map((group) =>
        group.id === groupId
          ? { ...group, tickers: Array.from(new Set([...group.tickers, ...tickers])) }
          : group,
      );
      return route.fulfill({ json: { ok: true } });
    }

    if (method === "DELETE" && deleteMatch) {
      deleteRequests += 1;
      const groupId = decodeURIComponent(deleteMatch[1]);
      const ticker = decodeURIComponent(deleteMatch[2]);
      universes = universes.map((group) =>
        group.id === groupId
          ? { ...group, tickers: group.tickers.filter((item) => item !== ticker) }
          : group,
      );
      return route.fulfill({ json: { ok: true } });
    }

    return route.fallback();
  });

  await page.goto("/universes");
  await expect(page.getByRole("heading", { name: "Configured ticker groups" })).toBeVisible();
  await expect(page.getByRole("link", { name: "AAPL" })).toBeVisible();
  await expect(page.getByRole("link", { name: "BSX" })).toBeVisible();

  await page.getByRole("button", { name: "Copy Mega Cap tickers" }).click();
  await expect(page.getByText("Mega Cap ticker list copied.")).toBeVisible();

  await page.getByLabel("Universe group").selectOption("Mega Cap");
  await page.getByLabel("Ticker to add").fill("msft");
  await page.getByRole("button", { name: "Add ticker" }).click();
  await expect(page.getByText("MSFT added to Mega Cap.")).toBeVisible();
  await expect(page.getByRole("link", { name: "MSFT" })).toBeVisible();

  await page.getByRole("button", { name: "Delete AAPL from Mega Cap" }).click();
  await expect(page.getByText("AAPL removed from Mega Cap.")).toBeVisible();
  await expect(page.getByRole("link", { name: "AAPL" })).toHaveCount(0);

  expect(addRequests).toBe(1);
  expect(deleteRequests).toBe(1);
  expect(refreshRequests).toBe(0);
});

test("lists recent refresh runs with failures and stale ticker links", async ({ page }) => {
  await page.route("**/api/runs/refresh", (route) => route.fulfill({ json: runsPayload }));

  await page.goto("/runs");
  await expect(page.getByRole("heading", { name: "Recent refresh runs" })).toBeVisible();
  await expect(page.getByText("2 refreshed, 1 failed, 1 stale cache preserved.")).toBeVisible();
  await expect(page.getByTestId("run-row-run-2026-06-06")).toBeVisible();
  await expect(page.getByText("provider timeout")).toBeVisible();
  await expect(page.getByText("latest cache kept")).toBeVisible();
  await expect(page.getByRole("link", { name: "BSX" })).toBeVisible();
  await expect(page.getByRole("link", { name: "AAPL" })).toBeVisible();
  await expect(page.getByText("All configured tickers refreshed.")).toBeVisible();
});

test("opens a non-default ticker detail", async ({ page }) => {
  await page.route("**/api/status", (route) => route.fulfill({ json: statusPayload }));
  await page.route("**/api/snapshot/AAPL", (route) => route.fulfill({ json: aaplSnapshot }));
  await page.route("**/api/snapshot/BSX", (route) => route.fulfill({ json: bsxSnapshot }));
  await page.route("**/api/chart/**", (route) => route.fulfill({
    json: { ...chartPayload, ticker: "BSX" },
  }));

  await page.goto("/market/BSX");
  await expect(page.getByText("BSX").first()).toBeVisible();
  await expect(page.getByText("$48.55").first()).toBeVisible();
  await expect(page.getByText("bearish").first()).toBeVisible();
  await expect(page.getByText("$47.17").first()).toBeVisible();
  await expect(page.getByText("Deterministic metrics", { exact: true })).toBeVisible();
  await expect(page.getByTestId("detail-metrics-section").getByText("N/A").first()).toBeVisible();
  await expect(page.getByText("History is shorter than the preferred lookback window.")).toBeVisible();
  await expect(page.getByText("Technical Matrix")).toHaveCount(0);
});

test("shows backend unavailable state without a blank screen", async ({ page }) => {
  await page.route("**/api/status", (route) => route.abort());
  await page.goto("/market");
  await expect(page.getByText("Backend unavailable")).toBeVisible();
  await expect(page.getByText("No cached tickers found")).toBeVisible();
});
