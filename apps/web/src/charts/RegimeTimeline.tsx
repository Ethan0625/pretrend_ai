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

import { axisTick, chartColors, formatDate, formatNumber, tooltipStyle } from "./common";

export interface RegimeTimelinePoint {
  trade_date: string;
  short_signal_code: number | null;
  transition_hazard_10d: number | null;
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
              name === "short_signal_code" ? "단기 신호" : "10일 전환 위험",
            ]}
          />
          <Legend
            formatter={(value) => (value === "short_signal_code" ? "단기 신호" : "10일 전환 위험")}
            wrapperStyle={{ color: "var(--fg-muted)", fontSize: 11 }}
          />
          <Line
            dataKey="short_signal_code"
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
