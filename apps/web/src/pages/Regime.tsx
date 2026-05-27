import { useMemo, useState } from "react";

import { PanelHead } from "@/components/primitives/PanelHead";
import { Pill } from "@/components/primitives/Pill";
import { Toolbar } from "@/components/Toolbar";
import { useMeta, useRegime, useRegimeExplain, useRegimeTimeline } from "@/api/hooks";
import { RegimeTimeline, type RegimeTimelinePoint } from "@/charts/RegimeTimeline";

import { ErrorState, ExplainReportView, PageState, addDays, getMaxDate } from "./_shared";

export function Regime() {
  const meta = useMeta();
  const latestDate = getMaxDate(meta.data, "gold_market_state_similarity_feature");
  const [tradeDate, setTradeDate] = useState("");
  const activeDate = tradeDate || latestDate;
  const timelineStart = addDays(activeDate, -28);
  const regime = useRegime(activeDate);
  const timeline = useRegimeTimeline(timelineStart, activeDate);
  const explain = useRegimeExplain(activeDate);

  const featureRows = useMemo(() => Object.entries(regime.data?.feature ?? {}), [regime.data]);
  const timelineRows = useMemo(() => toRegimeTimelinePoints(timeline.data?.data ?? []), [timeline.data]);

  return (
    <>
      <Toolbar
        tradeDate={activeDate}
        view="regime"
        onTradeDate={setTradeDate}
        onRefresh={() => {
          regime.refetch();
          timeline.refetch();
          explain.refetch();
        }}
      />
      <div className="grid-2">
        <div className="panel">
          <PanelHead title="시장 국면 feature" sub={`GET /api/v1/regime?trade_date=${activeDate}`} right={<Pill variant="gold">GOLD</Pill>} />
          {regime.isLoading || timeline.isLoading ? <PageState title="불러오는 중" detail="시장 국면 feature를 조회하고 있습니다." /> : null}
          {regime.error ? <ErrorState error={regime.error} /> : null}
          {timeline.error ? <ErrorState error={timeline.error} /> : null}
          {regime.data ? (
            <>
              <RegimeTimeline data={timelineRows} />
              <table className="tbl">
                <thead>
                  <tr>
                    <th>field</th>
                    <th>value</th>
                  </tr>
                </thead>
                <tbody>
                  {featureRows.map(([key, value]) => (
                    <tr key={key}>
                      <td>{key}</td>
                      <td>{value === null ? <span className="muted">UNKNOWN</span> : String(value)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          ) : null}
        </div>
        <div className="panel">
          <PanelHead title="국면 설명" sub={`GET /api/v1/regime/explain?trade_date=${activeDate}`} right={<Pill variant="info">CACHE</Pill>} />
          {explain.isLoading ? <PageState title="불러오는 중" detail="설명 cache를 조회하고 있습니다." /> : null}
          {explain.error ? <ErrorState error={explain.error} explain /> : null}
          {explain.data ? <ExplainReportView response={explain.data} /> : null}
        </div>
      </div>
    </>
  );
}

function toRegimeTimelinePoints(rows: Array<{ trade_date: string; feature: Record<string, unknown> }>): RegimeTimelinePoint[] {
  return rows.map((row) => ({
    trade_date: row.trade_date,
    short_signal_code: featureNumber(row.feature.short_signal_code),
    transition_hazard_10d: featureNumber(row.feature.transition_hazard_10d),
  }));
}

function featureNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}
