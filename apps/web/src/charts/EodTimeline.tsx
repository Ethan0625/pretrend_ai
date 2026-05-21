import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { EodFeature } from "@/api/types";

import { axisTick, chartColors, finiteNumber, formatDate, formatNumber, formatPercent, tooltipStyle } from "./common";

export type EodMetric = "close" | "ret_20d" | "vol_60d";

const METRIC_LABEL: Record<EodMetric, string> = {
  close: "종가",
  ret_20d: "20일 수익률",
  vol_60d: "60일 변동성",
};

function formatMetric(metric: EodMetric, value: number): string {
  if (metric === "ret_20d" || metric === "vol_60d") {
    return formatPercent(value, 2);
  }
  return formatNumber(value, 2);
}

export function EodTimeline({
  data,
  symbol,
  metric = "close",
  height = 280,
}: {
  data: EodFeature[];
  symbol: string;
  metric?: EodMetric;
  height?: number;
}) {
  const rows = data
    .map((row) => ({
      trade_date: row.trade_date,
      value: finiteNumber(row[metric]),
    }))
    .filter((row): row is { trade_date: string; value: number } => row.value !== null);

  if (!rows.length) {
    return <div className="chart-empty">차트로 표시할 관측값이 없습니다.</div>;
  }

  const label = METRIC_LABEL[metric];

  return (
    <div className="chart-frame" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={rows} margin={{ top: 8, right: 18, bottom: 0, left: 4 }}>
          <CartesianGrid stroke={chartColors.grid} strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="trade_date" tick={axisTick} tickFormatter={formatDate} minTickGap={24} />
          <YAxis tick={axisTick} tickFormatter={(value) => formatMetric(metric, Number(value))} width={72} />
          <Tooltip
            contentStyle={tooltipStyle}
            labelFormatter={(value) => `trade_date=${formatDate(String(value))}`}
            formatter={(value) => [formatMetric(metric, Number(value)), label]}
          />
          <Legend
            formatter={() => `${symbol} · ${label}`}
            wrapperStyle={{ color: "var(--fg-muted)", fontSize: 11 }}
          />
          <Line
            dataKey="value"
            dot={false}
            isAnimationActive={false}
            name={label}
            stroke={chartColors.pitSafe}
            strokeWidth={2}
            type="monotone"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
