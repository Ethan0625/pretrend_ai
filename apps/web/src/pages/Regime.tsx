import { useMemo, useState } from "react";

import { PanelHead } from "@/components/primitives/PanelHead";
import { Pill } from "@/components/primitives/Pill";
import { Toolbar } from "@/components/Toolbar";
import { useMeta, useRegime, useRegimeExplain } from "@/api/hooks";
import { RegimeTimeline, buildRegimeTimelinePlaceholder } from "@/charts/RegimeTimeline";

import { Disclaimer, ErrorState, ExplainReportView, PageState, getMaxDate } from "./_shared";

export function Regime() {
  const meta = useMeta();
  const latestDate = getMaxDate(meta.data, "gold_market_state_similarity_feature");
  const [tradeDate, setTradeDate] = useState("");
  const activeDate = tradeDate || latestDate;
  const regime = useRegime(activeDate);
  const explain = useRegimeExplain(activeDate);

  const featureRows = useMemo(() => Object.entries(regime.data?.feature ?? {}), [regime.data]);
  const timelineRows = useMemo(
    () => buildRegimeTimelinePlaceholder(activeDate, regime.data?.feature),
    [activeDate, regime.data],
  );

  return (
    <>
      <Toolbar tradeDate={activeDate} view="regime" onTradeDate={setTradeDate} onRefresh={() => regime.refetch()} />
      <div className="grid-2">
        <div className="panel">
          <PanelHead title="시장 국면 feature" sub={`GET /api/v1/regime?trade_date=${activeDate}`} right={<Pill variant="gold">GOLD</Pill>} />
          {regime.isLoading ? <PageState title="불러오는 중" detail="시장 국면 feature를 조회하고 있습니다." /> : null}
          {regime.error ? <ErrorState error={regime.error} /> : null}
          {regime.data ? (
            <>
              <RegimeTimeline data={timelineRows} />
              <Disclaimer>
                최근 20일 국면 timeline은 placeholder입니다. 국면 시계열 API가 확정되면 실제 관측 row로 교체합니다.
              </Disclaimer>
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
          {explain.error ? <ErrorState error={explain.error} /> : null}
          {explain.data ? <ExplainReportView response={explain.data} /> : null}
        </div>
      </div>
    </>
  );
}
