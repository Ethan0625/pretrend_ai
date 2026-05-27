import { useState } from "react";

import { PanelHead } from "@/components/primitives/PanelHead";
import { Pill } from "@/components/primitives/Pill";
import { Toolbar } from "@/components/Toolbar";
import { useMeta, useSimilarity, useSimilarityEvents, useSimilarityEventsExplain } from "@/api/hooks";
import { SimilarityScoreChart } from "@/charts/SimilarityScoreChart";
import type { SimilarityView } from "@/types/screen";

import { ErrorState, ExplainReportView, NumberCell, PageState, getMaxDate } from "./_shared";

type SimilarityPageTab = "dates" | "events";

export function Similarity() {
  const meta = useMeta();
  const [queryDate, setQueryDate] = useState("");
  const [view, setView] = useState<SimilarityView>("regime");
  const [pageTab, setPageTab] = useState<SimilarityPageTab>("dates");
  const [topN, setTopN] = useState(10);
  const latestDate = getMaxDate(
    meta.data,
    pageTab === "events" ? "gold_market_state_similarity_feature" : view === "regime" ? "similarity_regime" : "similarity_gold",
  );
  const activeDate = queryDate || latestDate;
  const similarity = useSimilarity(activeDate, pageTab === "dates" ? view : null, topN);
  const events = useSimilarityEvents(activeDate, pageTab === "events");
  const explain = useSimilarityEventsExplain(activeDate, hasValue(activeDate));

  return (
    <>
      <Toolbar
        tradeDate={activeDate}
        view={view}
        onTradeDate={setQueryDate}
        onView={setView}
        onRefresh={() => {
          if (pageTab === "events") {
            events.refetch();
          } else {
            similarity.refetch();
          }
          explain.refetch();
        }}
        showViewSelector={pageTab === "dates"}
        metaText={pageTab === "events" ? "events · regime features" : `view=${view} · top_n=${topN}`}
      />
      <div className="panel control-row">
        <div className="seg" aria-label="유사도 기준">
          <button className={pageTab === "dates" ? "on" : ""} type="button" onClick={() => setPageTab("dates")}>
            날짜 기준
          </button>
          <button className={pageTab === "events" ? "on" : ""} type="button" onClick={() => setPageTab("events")}>
            이벤트 기준
          </button>
        </div>
        {pageTab === "dates" ? (
        <label>
          <span className="t-label">Top-N</span>
          <select className="control-select" value={topN} onChange={(event) => setTopN(Number(event.target.value))}>
            {[5, 10, 20, 50].map((value) => (
              <option key={value} value={value}>{value}</option>
            ))}
          </select>
        </label>
        ) : null}
      </div>
      {pageTab === "events" ? (
        <div className="grid-2">
          <div className="panel">
            <PanelHead title="역사 이벤트 유사도" sub={`GET /api/v1/similarity/events?query_date=${activeDate}`} right={<Pill variant="silver">REGIME</Pill>} />
            {events.isLoading ? <PageState title="불러오는 중" detail="역사 이벤트 유사도를 조회하고 있습니다." /> : null}
            {events.error ? <ErrorState error={events.error} /> : null}
            {events.data ? (
              <table className="tbl">
                <thead>
                  <tr>
                    <th>event_name</th>
                    <th>anchor_date</th>
                    <th>actual_date</th>
                    <th>similarity_score</th>
                  </tr>
                </thead>
                <tbody>
                  {events.data.data.map((row) => (
                    <tr key={`${row.event_name}-${row.anchor_date}`} style={row.similarity_score === null ? { opacity: 0.55 } : undefined}>
                      <td>{row.event_name}</td>
                      <td>{row.anchor_date}</td>
                      <td>{row.actual_date ?? <span className="muted">NO ROW</span>}</td>
                      <td>
                        {row.similarity_score === null ? (
                          <span className="num-tab muted">-</span>
                        ) : (
                          <NumberCell value={row.similarity_score} digits={4} />
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : null}
          </div>
          <div className="panel">
            <PanelHead title="이벤트 유사도 설명" sub={`GET /api/v1/similarity/events/explain?query_date=${activeDate}`} right={<Pill variant="info">CACHE</Pill>} />
            {explain.isLoading ? <PageState title="불러오는 중" detail="설명 cache를 조회하고 있습니다." /> : null}
            {explain.error ? <ErrorState error={explain.error} explain /> : null}
            {explain.data ? <ExplainReportView response={explain.data} /> : null}
          </div>
        </div>
      ) : (
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
          <PanelHead title="이벤트 유사도 설명" sub={`GET /api/v1/similarity/events/explain?query_date=${activeDate}`} right={<Pill variant="info">CACHE</Pill>} />
          {explain.isLoading ? <PageState title="불러오는 중" detail="설명 cache를 조회하고 있습니다." /> : null}
          {explain.error ? <ErrorState error={explain.error} explain /> : null}
          {explain.data ? <ExplainReportView response={explain.data} /> : null}
        </div>
      </div>
      )}
    </>
  );
}

function hasValue(value: string): boolean {
  return value !== "";
}
