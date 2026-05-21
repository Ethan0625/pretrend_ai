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

import type { MacroFeature } from "@/api/types";

import { axisTick, chartColors, finiteNumber, formatDate, formatNumber, tooltipStyle } from "./common";

export type MacroMetric = "selected_value" | "delta_3m" | "zscore_12m";

const METRIC_LABEL: Record<MacroMetric, string> = {
  selected_value: "관측값",
  delta_3m: "3개월 변화",
  zscore_12m: "12개월 표준화점수",
};

export function MacroTimeline({
  data,
  indicatorId,
  metric = "selected_value",
  height = 280,
}: {
  data: MacroFeature[];
  indicatorId: string;
  metric?: MacroMetric;
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
          <YAxis tick={axisTick} tickFormatter={(value) => formatNumber(Number(value), 2)} width={64} />
          <Tooltip
            contentStyle={tooltipStyle}
            labelFormatter={(value) => `trade_date=${formatDate(String(value))}`}
            formatter={(value) => [formatNumber(Number(value), 4), label]}
          />
          <Legend
            formatter={() => `${indicatorId} · ${label}`}
            wrapperStyle={{ color: "var(--fg-muted)", fontSize: 11 }}
          />
          <Line
            dataKey="value"
            dot={false}
            isAnimationActive={false}
            name={label}
            stroke={chartColors.gold}
            strokeWidth={2}
            type="monotone"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
