import { useState } from "react";

import { ApiError } from "@/api/client";
import { PanelHead } from "@/components/primitives/PanelHead";
import { Pill } from "@/components/primitives/Pill";
import { Toolbar } from "@/components/Toolbar";
import { useMeta, useSimilarity, useSimilarityEvents, useSimilarityEventsExplain, useSimilarityReplay } from "@/api/hooks";
import type { ReplayTrajectory } from "@/api/types";
import { ReplayOverlayTimeline, ReplayTimeline } from "@/charts/ReplayTimeline";
import { SimilarityScoreChart } from "@/charts/SimilarityScoreChart";
import type { SimilarityView } from "@/types/screen";

import { EOD_SYMBOL_UNIVERSE, ErrorState, ExplainReportView, NumberCell, PageState, getMaxDate } from "./_shared";

type SimilarityPageTab = "dates" | "events" | "replay";

const REPLAY_TOP_N = 5;
const REPLAY_COMPARE_DAYS = 60;
const REPLAY_FORWARD_DAYS = 30;
const REPLAY_TOP_ASSETS = 5;
const REPLAY_RANKING_SYMBOLS = EOD_SYMBOL_UNIVERSE.map((asset) => asset.symbol);

export function Similarity() {
  const meta = useMeta();
  const [queryDate, setQueryDate] = useState("");
  const [view, setView] = useState<SimilarityView>("regime");
  const [replayView, setReplayView] = useState<"events" | SimilarityView>("events");
  const [replaySymbol, setReplaySymbol] = useState("SPY");
  const [pageTab, setPageTab] = useState<SimilarityPageTab>("dates");
  const [topN, setTopN] = useState(10);
  const latestDate = getMaxDate(
    meta.data,
    pageTab === "events"
      ? "gold_market_state_similarity_feature"
      : pageTab === "replay"
        ? replayView === "events"
          ? "gold_market_state_similarity_feature"
          : replayView === "regime"
            ? "similarity_regime"
            : "similarity_gold"
        : view === "regime"
          ? "similarity_regime"
          : "similarity_gold",
  );
  const activeDate = queryDate || latestDate;
  const similarity = useSimilarity(activeDate, pageTab === "dates" ? view : null, topN);
  const events = useSimilarityEvents(activeDate, pageTab === "events");
  const replay = useSimilarityReplay(
    activeDate,
    replayView,
    replaySymbol,
    pageTab === "replay",
    REPLAY_TOP_N,
    REPLAY_COMPARE_DAYS,
    REPLAY_FORWARD_DAYS,
    REPLAY_TOP_ASSETS,
    REPLAY_RANKING_SYMBOLS,
  );
  const explain = useSimilarityEventsExplain(activeDate, pageTab !== "replay" && hasValue(activeDate));

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
          } else if (pageTab === "replay") {
            replay.refetch();
          } else {
            similarity.refetch();
          }
          if (pageTab !== "replay") {
            explain.refetch();
          }
        }}
        showViewSelector={pageTab === "dates"}
        metaText={
          pageTab === "events"
            ? "events · regime features"
            : pageTab === "replay"
              ? `${replayView} replay · ${assetLabel(replaySymbol)} · D-${REPLAY_COMPARE_DAYS}/D+${REPLAY_FORWARD_DAYS}`
              : `view=${view} · top_n=${topN}`
        }
      />
      <div className="panel control-row">
        <div className="seg" aria-label="유사도 기준">
          <button className={pageTab === "dates" ? "on" : ""} type="button" onClick={() => setPageTab("dates")}>
            날짜 기준
          </button>
          <button className={pageTab === "events" ? "on" : ""} type="button" onClick={() => setPageTab("events")}>
            이벤트 기준
          </button>
          <button className={pageTab === "replay" ? "on" : ""} type="button" onClick={() => setPageTab("replay")}>
            유사 구간 궤적
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
        {pageTab === "replay" ? (
          <>
            <label>
              <span className="t-label">Replay 기준</span>
              <select className="control-select" value={replayView} onChange={(event) => setReplayView(event.target.value as "events" | SimilarityView)}>
                <option value="events">역사 이벤트</option>
                <option value="regime">날짜 · regime</option>
                <option value="gold">날짜 · gold</option>
              </select>
            </label>
            <label>
              <span className="t-label">Asset Name</span>
              <select className="control-select" value={replaySymbol} onChange={(event) => setReplaySymbol(event.target.value)}>
                {EOD_SYMBOL_UNIVERSE.map((asset) => (
                  <option key={asset.symbol} value={asset.symbol}>{asset.label} ({asset.symbol})</option>
                ))}
              </select>
            </label>
          </>
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
      ) : pageTab === "replay" ? (
        <ReplayPanel
          activeDate={activeDate}
          onSelectAsset={setReplaySymbol}
          replay={replay}
          replaySymbol={replaySymbol}
          replayView={replayView}
        />
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

function ReplayPanel({
  activeDate,
  onSelectAsset,
  replay,
  replayView,
  replaySymbol,
}: {
  activeDate: string;
  onSelectAsset: (symbol: string) => void;
  replay: ReturnType<typeof useSimilarityReplay>;
  replayView: "events" | SimilarityView;
  replaySymbol: string;
}) {
  const endpoint = `/api/v1/similarity/replay?query_date=${activeDate}&view=${replayView}&top_n=${REPLAY_TOP_N}&compare_days=${REPLAY_COMPARE_DAYS}&forward_days=${REPLAY_FORWARD_DAYS}&top_assets=${REPLAY_TOP_ASSETS}&symbol=${replaySymbol}`;

  if (replay.isLoading) {
    return <PageState title="불러오는 중" detail="유사 구간 궤적을 조회하고 있습니다." endpoint={endpoint} />;
  }

  if (replay.error) {
    if (replay.error instanceof ApiError && replay.error.status === 404) {
      const latest = replay.error.payload?.latest_available;
      return (
        <PageState
          title="궤적 데이터 없음"
          detail={latest ? `요청 날짜의 replay가 없습니다. 최신 사용 가능일: ${latest}` : "요청 날짜의 replay가 없습니다."}
          endpoint={endpoint}
        />
      );
    }
    return <ErrorState error={replay.error} endpoint={endpoint} />;
  }

  const trajectories = replay.data?.trajectories ?? [];
  if (!trajectories.length) {
    return <PageState title="데이터가 없습니다" detail="요청한 조건에 해당하는 유사 구간 궤적이 없습니다." endpoint={endpoint} />;
  }

  return (
    <div className="grid-2">
      {trajectories.map((trajectory) => (
        <ReplayCard
          key={`${trajectory.rank}-${trajectory.anchor_date}`}
          onSelectAsset={onSelectAsset}
          selectedSymbol={replaySymbol}
          trajectory={trajectory}
        />
      ))}
    </div>
  );
}

function ReplayCard({
  onSelectAsset,
  selectedSymbol,
  trajectory,
}: {
  onSelectAsset: (symbol: string) => void;
  selectedSymbol: string;
  trajectory: ReplayTrajectory;
}) {
  const ranking = trajectory.asset_rankings.slice(0, 5);

  return (
    <div className="panel">
      <PanelHead
        title={`#${trajectory.rank} · ${trajectory.label}`}
        sub={`${trajectory.compare_start} ~ ${trajectory.compare_end} · forward=${trajectory.window_end}`}
        right={<Pill variant="gold">EOD</Pill>}
      />
      <div className="explain-meta">
        <span>anchor={trajectory.actual_date}</span>
        <span>state_score=<NumberCell value={trajectory.state_similarity_score} digits={4} /></span>
        <span>trajectory_score=<NumberCell value={trajectory.trajectory_similarity_score} digits={4} /></span>
        <span>asset={trajectory.current_path.asset_name} ({trajectory.current_path.symbol})</span>
      </div>
      <ReplayOverlayTimeline assets={trajectory.overlay_assets} />
      <div className="explain-meta">
        <span>detail_asset={trajectory.current_path.asset_name}</span>
        <span>current_base={trajectory.current_path.base_date}</span>
        <span>historical_base={trajectory.historical_path.base_date}</span>
      </div>
      <ReplayTimeline
        currentPath={trajectory.current_path}
        historicalPath={trajectory.historical_path}
        historicalLabel={trajectory.label}
      />
      {ranking.length ? (
        <table className="tbl">
          <thead>
            <tr>
              <th>asset_name</th>
              <th>symbol</th>
              <th>trajectory_score</th>
            </tr>
          </thead>
          <tbody>
            {ranking.map((asset) => (
              <tr key={asset.symbol}>
                <td>
                  <button
                    className="inline-action"
                    disabled={asset.symbol === selectedSymbol}
                    onClick={() => onSelectAsset(asset.symbol)}
                    type="button"
                  >
                    {asset.asset_name}
                  </button>
                </td>
                <td>{asset.symbol}</td>
                <td><NumberCell value={asset.trajectory_similarity_score} digits={4} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
    </div>
  );
}

function assetLabel(symbol: string): string {
  const item = EOD_SYMBOL_UNIVERSE.find((asset) => asset.symbol === symbol);
  return item ? `${item.label} (${item.symbol})` : symbol;
}
