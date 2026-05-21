import { useState } from "react";

import { PanelHead } from "@/components/primitives/PanelHead";
import { Pill } from "@/components/primitives/Pill";
import { Toolbar } from "@/components/Toolbar";
import { useEod, useEodTimeline, useMeta } from "@/api/hooks";
import { EodTimeline, type EodMetric } from "@/charts/EodTimeline";

import { EOD_SYMBOL_UNIVERSE, EmptyState, ErrorState, NumberCell, PageState, addDays, getMaxDate } from "./_shared";

export function Eod() {
  const meta = useMeta();
  const latestDate = getMaxDate(meta.data, "gold_eod_features");
  const [tradeDate, setTradeDate] = useState("");
  const [symbol, setSymbol] = useState("SPY");
  const [metric, setMetric] = useState<EodMetric>("close");
  const activeDate = tradeDate || latestDate;
  const start = addDays(activeDate, -120);
  const eod = useEod(symbol, activeDate);
  const timeline = useEodTimeline(symbol, start, activeDate);

  return (
    <>
      <Toolbar tradeDate={activeDate} view="gold" onTradeDate={setTradeDate} onRefresh={() => eod.refetch()} />
      <div className="panel control-row">
        <label>
          <span className="t-label">symbol</span>
          <select className="control-select" value={symbol} onChange={(event) => setSymbol(event.target.value)}>
            {EOD_SYMBOL_UNIVERSE.map((item) => (
              <option key={item.symbol} value={item.symbol}>
                {item.symbol} · {item.label} · {item.group}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className="t-label">metric</span>
          <select className="control-select" value={metric} onChange={(event) => setMetric(event.target.value as EodMetric)}>
            <option value="close">종가</option>
            <option value="ret_20d">20일 수익률</option>
            <option value="vol_60d">60일 변동성</option>
          </select>
        </label>
      </div>
      <div className="grid-2">
        <div className="panel">
          <PanelHead title="EOD 관측값" sub={`GET /api/v1/eod?symbol=${symbol}&trade_date=${activeDate}`} right={<Pill variant="gold">GOLD</Pill>} />
          {eod.isLoading ? <PageState title="불러오는 중" detail="EOD row를 조회하고 있습니다." /> : null}
          {eod.error ? <ErrorState error={eod.error} /> : null}
          {eod.data ? (
            <table className="tbl">
              <tbody>
                {Object.entries(eod.data.data).map(([key, value]) => (
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
          <PanelHead title="EOD timeline" sub={`GET /api/v1/eod/timeline?symbol=${symbol}&start=${start}&end=${activeDate}`} right={<Pill variant="gold">CHART</Pill>} />
          {timeline.isLoading ? <PageState title="불러오는 중" detail="EOD timeline을 조회하고 있습니다." /> : null}
          {timeline.error ? <ErrorState error={timeline.error} /> : null}
          {timeline.data?.data.length ? (
            <EodTimeline data={timeline.data.data} symbol={symbol} metric={metric} />
          ) : timeline.data ? (
            <EmptyState />
          ) : null}
        </div>
      </div>
    </>
  );
}
