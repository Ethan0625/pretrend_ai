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

import type { ReplayAssetOverlay, ReplayAssetPath } from "@/api/types";

import { axisTick, chartColors, formatPercent, tooltipStyle } from "./common";

const SERIES_COLORS = [
  chartColors.pitSafe,
  chartColors.info,
  chartColors.gold,
  chartColors.warn,
  chartColors.silver,
  chartColors.danger,
];

export function ReplayOverlayTimeline({
  assets,
  height = 260,
}: {
  assets: ReplayAssetOverlay[];
  height?: number;
}) {
  const rows = toOverlayRows(assets);

  if (!rows.length || !assets.length) {
    return <div className="chart-empty">차트로 표시할 Top Asset 궤적이 없습니다.</div>;
  }

  return (
    <div className="chart-frame" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={rows} margin={{ top: 8, right: 18, bottom: 0, left: 4 }}>
          <CartesianGrid stroke={chartColors.grid} strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="day_offset" tick={axisTick} tickFormatter={formatOffset} minTickGap={18} />
          <YAxis tick={axisTick} tickFormatter={(value) => formatPercent(Number(value), 1)} width={72} />
          <Tooltip
            contentStyle={tooltipStyle}
            labelFormatter={(value) => `offset=${formatOffset(Number(value))}`}
            formatter={(value, name) => [formatPercent(Number(value), 2), String(name)]}
          />
          <Legend wrapperStyle={{ color: "var(--fg-muted)", fontSize: 11 }} />
          <ReferenceLine
            x={0}
            stroke={chartColors.silver}
            strokeDasharray="4 4"
            label={{ value: "D", fill: chartColors.text, fontSize: 10, position: "insideTopRight" }}
          />
          {assets.map((asset, index) => (
            <Line
              connectNulls
              dataKey={asset.symbol}
              dot={false}
              isAnimationActive={false}
              key={asset.symbol}
              name={`${asset.asset_name} · ${asset.symbol}`}
              stroke={SERIES_COLORS[index % SERIES_COLORS.length]}
              strokeWidth={2}
              type="monotone"
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function ReplayTimeline({
  currentPath,
  historicalPath,
  historicalLabel,
  height = 220,
}: {
  currentPath: ReplayAssetPath;
  historicalPath: ReplayAssetPath;
  historicalLabel: string;
  height?: number;
}) {
  const rows = toAlignedRows(currentPath, historicalPath);

  if (!rows.length) {
    return <div className="chart-empty">차트로 표시할 EOD 궤적이 없습니다.</div>;
  }

  return (
    <div className="chart-frame" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={rows} margin={{ top: 8, right: 18, bottom: 0, left: 4 }}>
          <CartesianGrid stroke={chartColors.grid} strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="day_offset" tick={axisTick} tickFormatter={formatOffset} minTickGap={18} />
          <YAxis tick={axisTick} tickFormatter={(value) => formatPercent(Number(value), 1)} width={72} />
          <Tooltip
            contentStyle={tooltipStyle}
            labelFormatter={(value) => `offset=${formatOffset(Number(value))}`}
            formatter={(value, name) => [formatPercent(Number(value), 2), String(name)]}
          />
          <Legend wrapperStyle={{ color: "var(--fg-muted)", fontSize: 11 }} />
          <ReferenceLine
            x={0}
            stroke={chartColors.silver}
            strokeDasharray="4 4"
            label={{ value: "anchor", fill: chartColors.text, fontSize: 10, position: "insideTopRight" }}
          />
          <Line
            connectNulls
            dataKey="current"
            dot={false}
            isAnimationActive={false}
            name={`현재 · ${currentPath.asset_name}`}
            stroke={chartColors.pitSafe}
            strokeWidth={2}
            type="monotone"
          />
          <Line
            connectNulls
            dataKey="historical"
            dot={false}
            isAnimationActive={false}
            name={`과거 · ${historicalLabel}`}
            stroke={chartColors.gold}
            strokeWidth={2}
            type="monotone"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function toOverlayRows(assets: ReplayAssetOverlay[]): Array<Record<string, number | string | null>> {
  const byOffset = new Map<number, Record<string, number | string | null>>();
  assets.forEach((asset) => {
    asset.historical_path.points.forEach((point) => {
      const row = byOffset.get(point.day_offset) ?? { day_offset: point.day_offset };
      row[asset.symbol] = point.normalized_return;
      byOffset.set(point.day_offset, row);
    });
  });
  return Array.from(byOffset.values()).sort((a, b) =>
    Number(a.day_offset) - Number(b.day_offset),
  );
}

function toAlignedRows(
  currentPath: ReplayAssetPath,
  historicalPath: ReplayAssetPath,
): Array<Record<string, number | string | null>> {
  const byOffset = new Map<number, Record<string, number | string | null>>();
  currentPath.points.forEach((point) => {
    const row = byOffset.get(point.day_offset) ?? { day_offset: point.day_offset };
    row.current = point.normalized_return;
    row.current_date = point.trade_date;
    byOffset.set(point.day_offset, row);
  });
  historicalPath.points.forEach((point) => {
    const row = byOffset.get(point.day_offset) ?? { day_offset: point.day_offset };
    row.historical = point.normalized_return;
    row.historical_date = point.trade_date;
    byOffset.set(point.day_offset, row);
  });
  return Array.from(byOffset.values()).sort((a, b) =>
    Number(a.day_offset) - Number(b.day_offset),
  );
}

function formatOffset(value: number): string {
  if (value === 0) {
    return "D";
  }
  return value > 0 ? `D+${value}` : `D${value}`;
}
