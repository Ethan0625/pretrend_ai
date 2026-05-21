import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { SimilarityNeighbor, SimilarityView } from "@/api/types";

import { axisTick, chartColors, formatDate, formatNumber, tooltipStyle } from "./common";

export function SimilarityScoreChart({
  neighbors,
  view,
  height = 280,
}: {
  neighbors: SimilarityNeighbor[];
  view: SimilarityView;
  height?: number;
}) {
  const rows = neighbors.slice(0, 10).map((row) => ({
    ...row,
    label: `#${row.rank} ${formatDate(row.neighbor_date)}`,
  }));

  if (!rows.length) {
    return <div className="chart-empty">차트로 표시할 유사 구간이 없습니다.</div>;
  }

  return (
    <div className="chart-frame" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} layout="vertical" margin={{ top: 8, right: 18, bottom: 0, left: 44 }}>
          <CartesianGrid stroke={chartColors.grid} strokeDasharray="3 3" horizontal={false} />
          <XAxis
            dataKey="score"
            domain={[0, "dataMax"]}
            tick={axisTick}
            tickFormatter={(value) => formatNumber(Number(value), 2)}
            type="number"
          />
          <YAxis dataKey="label" tick={axisTick} type="category" width={118} />
          <Tooltip
            contentStyle={tooltipStyle}
            formatter={(value) => [formatNumber(Number(value), 4), `${view} score`]}
            labelFormatter={(_, payload) => {
              const row = payload?.[0]?.payload as SimilarityNeighbor | undefined;
              return row ? `neighbor_date=${formatDate(row.neighbor_date)} · gap_days=${row.gap_days}` : "neighbor";
            }}
          />
          <Bar dataKey="score" fill={view === "gold" ? chartColors.gold : chartColors.silver} radius={[0, 6, 6, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
