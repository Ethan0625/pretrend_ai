import { useState } from "react";

import { PanelHead } from "@/components/primitives/PanelHead";
import { Pill } from "@/components/primitives/Pill";
import { Toolbar } from "@/components/Toolbar";
import { useMeta, useSimilarity, useSimilarityExplain } from "@/api/hooks";
import { SimilarityScoreChart } from "@/charts/SimilarityScoreChart";
import type { SimilarityView } from "@/types/screen";

import { ErrorState, ExplainReportView, NumberCell, PageState, getMaxDate } from "./_shared";

export function Similarity() {
  const meta = useMeta();
  const [queryDate, setQueryDate] = useState("");
  const [view, setView] = useState<SimilarityView>("regime");
  const [topN, setTopN] = useState(10);
  const latestDate = getMaxDate(meta.data, view === "regime" ? "similarity_regime" : "similarity_gold");
  const activeDate = queryDate || latestDate;
  const similarity = useSimilarity(activeDate, view, topN);
  const explain = useSimilarityExplain(activeDate, view);

  return (
    <>
      <Toolbar tradeDate={activeDate} view={view} onTradeDate={setQueryDate} onView={setView} onRefresh={() => similarity.refetch()} />
      <div className="panel control-row">
        <label>
          <span className="t-label">Top-N</span>
          <select className="control-select" value={topN} onChange={(event) => setTopN(Number(event.target.value))}>
            {[5, 10, 20, 50].map((value) => (
              <option key={value} value={value}>{value}</option>
            ))}
          </select>
        </label>
      </div>
      <div className="grid-2">
        <div className="panel">
          <PanelHead title="과거 유사 시기" sub={`GET /api/v1/similarity?query_date=${activeDate}&view=${view}&top_n=${topN}`} right={<Pill variant={view === "gold" ? "gold" : "silver"}>{view.toUpperCase()}</Pill>} />
          {similarity.isLoading ? <PageState title="불러오는 중" detail="유사 시기를 조회하고 있습니다." /> : null}
          {similarity.error ? <ErrorState error={similarity.error} /> : null}
          {similarity.data ? (
            <>
              <SimilarityScoreChart neighbors={similarity.data.neighbors} view={view} />
              <table className="tbl">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>neighbor_date</th>
                    <th>score</th>
                    <th>gap_days</th>
                  </tr>
                </thead>
                <tbody>
                  {similarity.data.neighbors.map((row) => (
                    <tr key={row.rank}>
                      <td>{row.rank}</td>
                      <td>{row.neighbor_date}</td>
                      <td><NumberCell value={row.score} digits={4} /></td>
                      <td>{row.gap_days}d</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          ) : null}
        </div>
        <div className="panel">
          <PanelHead title="유사도 설명" sub={`GET /api/v1/similarity/explain?query_date=${activeDate}&view=${view}`} right={<Pill variant="info">CACHE</Pill>} />
          {explain.isLoading ? <PageState title="불러오는 중" detail="설명 cache를 조회하고 있습니다." /> : null}
          {explain.error ? <ErrorState error={explain.error} /> : null}
          {explain.data ? <ExplainReportView response={explain.data} /> : null}
        </div>
      </div>
    </>
  );
}
