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

import type { RegimeFeature } from "@/api/types";

import { addUtcDays, axisTick, chartColors, finiteNumber, formatDate, formatNumber, tooltipStyle } from "./common";

export interface RegimeTimelinePoint {
  trade_date: string;
  bias_20d: number;
  transition_hazard_10d: number;
}

export function buildRegimeTimelinePlaceholder(
  endDate: string,
  feature: RegimeFeature | undefined,
): RegimeTimelinePoint[] {
  if (!endDate) {
    return [];
  }

  const baseBias = pickFeatureNumber(feature, ["bias_20d", "market_bias_20d", "bias_score"], 0.08);
  const baseHazard = pickFeatureNumber(
    feature,
    ["transition_hazard_10d", "transition_hazard", "hazard_10d"],
    0.22,
  );

  return Array.from({ length: 20 }, (_, index) => {
    const step = index - 19;
    return {
      trade_date: addUtcDays(endDate, step),
      bias_20d: clamp(baseBias + Math.sin(index / 3) * 0.08 + step * 0.002, -1, 1),
      transition_hazard_10d: clamp(baseHazard + Math.cos(index / 4) * 0.05, 0, 1),
    };
  });
}

export function RegimeTimeline({ data, height = 280 }: { data: RegimeTimelinePoint[]; height?: number }) {
  if (!data.length) {
    return <div className="chart-empty">차트로 표시할 국면 관측값이 없습니다.</div>;
  }

  return (
    <div className="chart-frame" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 18, bottom: 0, left: 4 }}>
          <CartesianGrid stroke={chartColors.grid} strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="trade_date" tick={axisTick} tickFormatter={formatDate} minTickGap={24} />
          <YAxis domain={[-1, 1]} tick={axisTick} tickFormatter={(value) => formatNumber(Number(value), 2)} width={62} />
          <Tooltip
            contentStyle={tooltipStyle}
            labelFormatter={(value) => `trade_date=${formatDate(String(value))}`}
            formatter={(value, name) => [
              formatNumber(Number(value), 4),
              name === "bias_20d" ? "20일 편향" : "10일 전환 위험",
            ]}
          />
          <Legend
            formatter={(value) => (value === "bias_20d" ? "20일 편향" : "10일 전환 위험")}
            wrapperStyle={{ color: "var(--fg-muted)", fontSize: 11 }}
          />
          <Line
            dataKey="bias_20d"
            dot={false}
            isAnimationActive={false}
            stroke={chartColors.info}
            strokeWidth={2}
            type="monotone"
          />
          <Line
            dataKey="transition_hazard_10d"
            dot={false}
            isAnimationActive={false}
            stroke={chartColors.warn}
            strokeWidth={2}
            type="monotone"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function pickFeatureNumber(feature: RegimeFeature | undefined, keys: string[], fallback: number): number {
  if (!feature) {
    return fallback;
  }
  for (const key of keys) {
    const value = finiteNumber(feature[key]);
    if (value !== null) {
      return value;
    }
  }
  return fallback;
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}
