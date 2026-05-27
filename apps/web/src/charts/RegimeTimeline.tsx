import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { axisTick, chartColors, formatDate, formatNumber, tooltipStyle } from "./common";

export interface RegimeTimelinePoint {
  trade_date: string;
  mid_regime_code: number | null;
  short_signal_code: number | null;
  sojourn_prob_10d: number | null;
  transition_hazard_10d: number | null;
}

export function RegimeTimeline({ data, height = 220 }: { data: RegimeTimelinePoint[]; height?: number }) {
  if (!data.length) {
    return <div className="chart-empty">차트로 표시할 국면 관측값이 없습니다.</div>;
  }

  return (
    <div className="chart-stack">
      <div className="chart-frame" style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 18, bottom: 0, left: 4 }}>
            <CartesianGrid stroke={chartColors.grid} strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="trade_date" tick={axisTick} tickFormatter={formatDate} minTickGap={24} />
            <YAxis domain={[-1, 1]} tick={axisTick} tickFormatter={(value) => formatStateCode(Number(value))} width={74} />
            <Tooltip
              contentStyle={tooltipStyle}
              labelFormatter={(value) => `trade_date=${formatDate(String(value))}`}
              formatter={(value, name) => [
                formatStateTooltip(value),
                name === "mid_regime_code" ? "중기 국면" : "단기 신호",
              ]}
            />
            <Legend
              formatter={(value) => (value === "mid_regime_code" ? "중기 국면" : "단기 신호")}
              wrapperStyle={{ color: "var(--fg-muted)", fontSize: 11 }}
            />
            <ReferenceLine y={0} stroke={chartColors.grid} />
            <Line
              connectNulls
              dataKey="mid_regime_code"
              dot={false}
              isAnimationActive={false}
              stroke={chartColors.pitSafe}
              strokeWidth={2}
              type="stepAfter"
            />
            <Line
              connectNulls
              dataKey="short_signal_code"
              dot={false}
              isAnimationActive={false}
              stroke={chartColors.info}
              strokeWidth={2}
              type="stepAfter"
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="chart-frame" style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 18, bottom: 0, left: 4 }}>
            <CartesianGrid stroke={chartColors.grid} strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="trade_date" tick={axisTick} tickFormatter={formatDate} minTickGap={24} />
            <YAxis domain={[0, 1]} tick={axisTick} tickFormatter={(value) => formatProbability(Number(value), 0)} width={74} />
            <Tooltip
              contentStyle={tooltipStyle}
              labelFormatter={(value) => `trade_date=${formatDate(String(value))}`}
              formatter={(value, name) => [
                formatProbabilityTooltip(value),
                name === "transition_hazard_10d" ? "10일 전환 위험" : "10일 유지 확률",
              ]}
            />
            <Legend
              formatter={(value) => (value === "transition_hazard_10d" ? "10일 전환 위험" : "10일 유지 확률")}
              wrapperStyle={{ color: "var(--fg-muted)", fontSize: 11 }}
            />
            <Line
              connectNulls
              dataKey="transition_hazard_10d"
              dot={false}
              isAnimationActive={false}
              stroke={chartColors.warn}
              strokeWidth={2}
              type="monotone"
            />
            <Line
              connectNulls
              dataKey="sojourn_prob_10d"
              dot={false}
              isAnimationActive={false}
              stroke={chartColors.silver}
              strokeWidth={2}
              type="monotone"
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function finiteValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function formatStateTooltip(value: unknown): string {
  const numericValue = finiteValue(value);
  if (numericValue === null) {
    return "UNKNOWN";
  }
  return `${formatStateCode(numericValue)} (${formatNumber(numericValue, 0)})`;
}

function formatProbabilityTooltip(value: unknown): string {
  return formatProbability(finiteValue(value), 2);
}

function formatStateCode(value: number | null): string {
  if (value === null || !Number.isFinite(value)) {
    return "UNKNOWN";
  }
  if (value > 0) {
    return "+1";
  }
  if (value < 0) {
    return "-1";
  }
  return "0";
}

function formatProbability(value: number | null, digits: number): string {
  if (value === null || !Number.isFinite(value)) {
    return "UNKNOWN";
  }
  return `${(value * 100).toLocaleString("ko-KR", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  })}%`;
}
