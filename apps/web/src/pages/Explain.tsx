import { useState } from "react";

import { PanelHead } from "@/components/primitives/PanelHead";
import { Pill } from "@/components/primitives/Pill";
import { Toolbar } from "@/components/Toolbar";
import { useMacroExplain, useMeta, useRegimeExplain, useSimilarityEventsExplain } from "@/api/hooks";
import type { SimilarityView } from "@/types/screen";

import { Disclaimer, ErrorState, ExplainReportView, PageState, getMaxDate } from "./_shared";

export function Explain() {
  const meta = useMeta();
  const latestDate = getMaxDate(meta.data, "gold_market_state_similarity_feature");
  const [tradeDate, setTradeDate] = useState("");
  const view: SimilarityView = "regime";
  const activeDate = tradeDate || latestDate;
  const regime = useRegimeExplain(activeDate);
  const similarity = useSimilarityEventsExplain(activeDate);
  const macro = useMacroExplain(activeDate);

  return (
    <>
      <Toolbar tradeDate={activeDate} view={view} onTradeDate={setTradeDate} onRefresh={() => {
        regime.refetch();
        similarity.refetch();
        macro.refetch();
      }} showViewSelector={false} metaText="events · regime features" />
      <div className="grid-3">
        <ExplainCard title="국면 설명" endpoint={`/api/v1/regime/explain?trade_date=${activeDate}`} result={regime} />
        <ExplainCard title="이벤트 유사도 설명" endpoint={`/api/v1/similarity/events/explain?query_date=${activeDate}`} result={similarity} />
        <ExplainCard title="거시 설명" endpoint={`/api/v1/macro/explain?trade_date=${activeDate}`} result={macro} />
      </div>
      <Disclaimer>
        본 설명은 관측 결과의 자연어 요약입니다. 예측이나 매매 권고가 아니며, Gold feature와 cache row를 사람이 읽기 쉽게 정리한 화면입니다.
      </Disclaimer>
    </>
  );
}

function ExplainCard({
  title,
  endpoint,
  result,
}: {
  title: string;
  endpoint: string;
  result: ReturnType<typeof useRegimeExplain>;
}) {
  return (
    <div className="panel">
      <PanelHead title={title} sub={endpoint} right={<Pill variant="info">CACHE</Pill>} />
      {result.isLoading ? <PageState title="불러오는 중" detail="설명 cache를 조회하고 있습니다." /> : null}
      {result.error ? <ErrorState error={result.error} explain /> : null}
      {result.data ? <ExplainReportView response={result.data} /> : null}
    </div>
  );
}
