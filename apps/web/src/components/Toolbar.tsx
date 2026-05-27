import type { SimilarityView } from "@/types/screen";

import { Pill } from "./primitives/Pill";

export interface ToolbarProps {
  tradeDate: string;
  view: SimilarityView;
  onTradeDate?: (tradeDate: string) => void;
  onView?: (view: SimilarityView) => void;
  onRefresh?: () => void;
  onViewJson?: () => void;
  showViewSelector?: boolean;
  metaText?: string;
}

export function Toolbar({
  tradeDate,
  view,
  onTradeDate,
  onView,
  onRefresh,
  onViewJson,
  showViewSelector = true,
  metaText,
}: ToolbarProps) {
  return (
    <div className="toolbar">
      <span className="t-label">날짜 선택</span>
      <input
        aria-label="거래일"
        className="date date-input"
        type="date"
        value={tradeDate}
        onChange={(event) => onTradeDate?.(event.target.value)}
      />
      {showViewSelector ? (
        <div className="seg" aria-label="유사도 뷰">
          <button className={view === "regime" ? "on" : ""} type="button" onClick={() => onView?.("regime")}>
            regime
          </button>
          <button className={view === "gold" ? "on" : ""} type="button" onClick={() => onView?.("gold")}>
            gold
          </button>
        </div>
      ) : null}
      <span className="t-mono toolbar-meta">{metaText ?? `view=${view} · top_n=10`}</span>
      <div className="spacer" />
      <Pill variant="pit-safe">PIT-SAFE</Pill>
      <button className="btn btn-secondary btn-sm" type="button" onClick={onRefresh}>
        <span aria-hidden="true">↻</span>
        새로 고침
      </button>
      <button className="btn btn-secondary btn-sm" type="button" onClick={onViewJson}>
        JSON
      </button>
    </div>
  );
}
