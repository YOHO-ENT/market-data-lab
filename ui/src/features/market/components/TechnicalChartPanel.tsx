import ReactECharts from "echarts-for-react";
import { useMemo } from "react";

import {
  formatLevelList,
  formatPrice,
  normalizeLabel,
} from "../model/formatters";
import type { TechnicalChart, TechnicalSnapshot } from "../model/types";

interface TechnicalChartPanelProps {
  chart: TechnicalChart | null;
  snapshot: TechnicalSnapshot | null;
  loading: boolean;
}

export function TechnicalChartPanel({
  chart,
  snapshot,
  loading,
}: TechnicalChartPanelProps) {
  const option = useMemo(() => {
    if (!chart?.has_image || chart.points.length === 0) {
      return null;
    }

    const dates = chart.points.map((point) => point.date);
    const closes = chart.points.map((point) => point.close);
    const volumes = chart.points.map((point) => point.volume);
    const byDate = new Map(chart.points.map((point, index) => [point.date, index]));
    const maSeries = (series: { date: string; value: number | null }[]) => {
      const values = Array<number | null>(dates.length).fill(null);
      for (const point of series) {
        const index = byDate.get(point.date);
        if (index != null) {
          values[index] = point.value;
        }
      }
      return values;
    };

    const markLines = [
      ...chart.support_levels.slice(0, 3).map((level) => ({
        name: "Support",
        yAxis: level,
        lineStyle: { color: "rgba(0, 212, 170, 0.45)", type: "dashed" },
        label: { color: "#7B8FA8", formatter: "S" },
      })),
      ...chart.resistance_levels.slice(0, 3).map((level) => ({
        name: "Resistance",
        yAxis: level,
        lineStyle: { color: "rgba(91, 163, 245, 0.45)", type: "dashed" },
        label: { color: "#7B8FA8", formatter: "R" },
      })),
    ];

    return {
      backgroundColor: "transparent",
      animation: false,
      color: ["#00D4AA", "#5BA3F5", "#A78BFA", "#E8A330"],
      tooltip: {
        trigger: "axis",
        backgroundColor: "#131B2E",
        borderColor: "#1E2D42",
        textStyle: { color: "#E2EBF5", fontFamily: "monospace" },
        axisPointer: { lineStyle: { color: "#5BA3F5", opacity: 0.45 } },
      },
      legend: {
        top: 0,
        right: 0,
        textStyle: { color: "#7B8FA8" },
        itemWidth: 16,
        itemHeight: 8,
      },
      grid: [
        { left: 48, right: 18, top: 42, height: 210 },
        { left: 48, right: 18, top: 286, height: 64 },
      ],
      xAxis: [
        {
          type: "category",
          data: dates,
          boundaryGap: false,
          axisLine: { lineStyle: { color: "#1E2D42" } },
          axisLabel: { color: "#7B8FA8", hideOverlap: true },
          splitLine: { show: false },
        },
        {
          type: "category",
          data: dates,
          gridIndex: 1,
          boundaryGap: true,
          axisLine: { lineStyle: { color: "#1E2D42" } },
          axisLabel: { color: "#7B8FA8", hideOverlap: true },
          splitLine: { show: false },
        },
      ],
      yAxis: [
        {
          type: "value",
          scale: true,
          axisLine: { show: false },
          axisLabel: { color: "#7B8FA8" },
          splitLine: { lineStyle: { color: "rgba(30, 45, 66, 0.72)" } },
        },
        {
          type: "value",
          gridIndex: 1,
          axisLine: { show: false },
          axisLabel: { color: "#7B8FA8" },
          splitLine: { show: false },
        },
      ],
      series: [
        {
          name: "Close",
          type: "line",
          data: closes,
          smooth: true,
          symbol: "none",
          lineStyle: { width: 2, color: "#00D4AA" },
          areaStyle: { color: "rgba(0, 212, 170, 0.08)" },
          markLine: {
            symbol: ["none", "none"],
            data: markLines,
            silent: true,
          },
        },
        {
          name: "MA20",
          type: "line",
          data: maSeries(chart.ma20),
          symbol: "none",
          lineStyle: { width: 1.4, color: "#5BA3F5" },
        },
        {
          name: "MA50",
          type: "line",
          data: maSeries(chart.ma50),
          symbol: "none",
          lineStyle: { width: 1.4, color: "#A78BFA" },
        },
        {
          name: "MA200",
          type: "line",
          data: maSeries(chart.ma200),
          symbol: "none",
          lineStyle: { width: 1.4, color: "#E8A330" },
        },
        {
          name: "Volume",
          type: "bar",
          xAxisIndex: 1,
          yAxisIndex: 1,
          data: volumes,
          itemStyle: { color: "rgba(91, 163, 245, 0.42)" },
        },
      ],
    };
  }, [chart]);

  const warnings = chart?.data_quality.warnings || snapshot?.data_quality.warnings || [];

  return (
    <aside className="chart-panel section-card">
      <div className="chart-panel-header">
        <div>
          <div className="eyebrow">Selected chart</div>
          <h2 className="ticker-heading">{snapshot?.ticker || chart?.ticker || "No ticker"}</h2>
        </div>
        <div className="price-chip">
          <div className="price-chip-value">
            {formatPrice(snapshot?.price, snapshot?.currency)}
          </div>
          <div className="price-chip-label">
            as of {snapshot?.as_of || chart?.as_of || "N/A"}
          </div>
        </div>
      </div>

      <div className="chart-metrics">
        <ChartMetric label="Trend" value={normalizeLabel(snapshot?.trend)} />
        <ChartMetric label="Breakout" value={normalizeLabel(snapshot?.breakout_status)} />
        <ChartMetric
          label="Support"
          value={formatLevelList(snapshot?.support_levels, snapshot?.currency)}
        />
        <ChartMetric
          label="Resistance"
          value={formatLevelList(snapshot?.resistance_levels, snapshot?.currency)}
        />
      </div>

      {loading ? (
        <div className="chart-empty">Loading chart...</div>
      ) : option ? (
        <div className="chart-canvas" data-testid="ticker-chart">
          <ReactECharts option={option} style={{ height: "100%", width: "100%" }} />
        </div>
      ) : (
        <div className="chart-empty">Chart data is unavailable for this ticker.</div>
      )}

      {warnings.length > 0 && (
        <div className="warning-note">{warnings.slice(0, 2).join(" ")}</div>
      )}
    </aside>
  );
}

function ChartMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="chart-metric">
      <div className="chart-metric-label">{label}</div>
      <div className="chart-metric-value" title={value}>
        {value}
      </div>
    </div>
  );
}
