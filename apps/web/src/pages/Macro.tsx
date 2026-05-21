import { useState } from "react";

import { PanelHead } from "@/components/primitives/PanelHead";
import { Pill } from "@/components/primitives/Pill";
import { Toolbar } from "@/components/Toolbar";
import { useMacro, useMacroExplain, useMacroTimeline, useMeta } from "@/api/hooks";
import { MacroTimeline, type MacroMetric } from "@/charts/MacroTimeline";

import { EmptyState, ErrorState, ExplainReportView, MACRO_INDICATORS, NumberCell, PageState, addDays, getMaxDate } from "./_shared";

export function Macro() {
  const meta = useMeta();
  const latestDate = getMaxDate(meta.data, "gold_macro_features");
  const [tradeDate, setTradeDate] = useState("");
  const [indicatorId, setIndicatorId] = useState("CPI_US_ALL_ITEMS_SA");
  const [metric, setMetric] = useState<MacroMetric>("selected_value");
  const activeDate = tradeDate || latestDate;
  const start = addDays(activeDate, -120);
  const macro = useMacro(activeDate, indicatorId);
  const timeline = useMacroTimeline(indicatorId, start, activeDate);
  const explain = useMacroExplain(activeDate);

  return (
    <>
      <Toolbar tradeDate={activeDate} view="regime" onTradeDate={setTradeDate} onRefresh={() => macro.refetch()} />
      <div className="panel control-row">
        <label>
          <span className="t-label">indicator_id</span>
          <select className="control-select" value={indicatorId} onChange={(event) => setIndicatorId(event.target.value)}>
            {MACRO_INDICATORS.map((item) => (
              <option key={item.id} value={item.id}>{item.id} · {item.label}</option>
            ))}
          </select>
        </label>
        <label>
          <span className="t-label">metric</span>
          <select className="control-select" value={metric} onChange={(event) => setMetric(event.target.value as MacroMetric)}>
            <option value="selected_value">관측값</option>
            <option value="delta_3m">3개월 변화</option>
            <option value="zscore_12m">12개월 표준화점수</option>
          </select>
        </label>
      </div>
      <div className="grid-2">
        <div className="panel">
          <PanelHead title="거시지표 관측값" sub={`GET /api/v1/macro?trade_date=${activeDate}&indicator_id=${indicatorId}`} right={<Pill variant="gold">GOLD</Pill>} />
          {macro.isLoading ? <PageState title="불러오는 중" detail="거시지표 row를 조회하고 있습니다." /> : null}
          {macro.error ? <ErrorState error={macro.error} /> : null}
          {macro.data ? (
            <table className="tbl">
              <tbody>
                {Object.entries(macro.data.data).map(([key, value]) => (
                  <tr key={key}>
                    <td>{key}</td>
                    <td>{typeof value === "number" ? <NumberCell value={value} digits={4} /> : String(value ?? "UNKNOWN")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
        </div>
        <div className="panel">
          <PanelHead title="거시지표 timeline" sub={`GET /api/v1/macro/timeline?indicator_id=${indicatorId}&start=${start}&end=${activeDate}`} right={<Pill variant="gold">CHART</Pill>} />
          {timeline.isLoading ? <PageState title="불러오는 중" detail="거시지표 timeline을 조회하고 있습니다." /> : null}
          {timeline.error ? <ErrorState error={timeline.error} /> : null}
          {timeline.data?.data.length ? (
            <MacroTimeline data={timeline.data.data} indicatorId={indicatorId} metric={metric} />
          ) : timeline.data ? (
            <EmptyState />
          ) : null}
        </div>
      </div>
      <div className="panel">
        <PanelHead title="거시 설명" sub={`GET /api/v1/macro/explain?trade_date=${activeDate}`} right={<Pill variant="info">CACHE</Pill>} />
        {explain.isLoading ? <PageState title="불러오는 중" detail="설명 cache를 조회하고 있습니다." /> : null}
        {explain.error ? <ErrorState error={explain.error} /> : null}
        {explain.data ? <ExplainReportView response={explain.data} /> : null}
      </div>
    </>
  );
}
