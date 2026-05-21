import type { ReactNode } from "react";

import { CodeBlock } from "@/components/primitives/CodeBlock";
import { PanelHead } from "@/components/primitives/PanelHead";
import { Pill, type PillVariant } from "@/components/primitives/Pill";
import type { ExplainResponse, JsonValue, MetaResponse } from "@/api/types";

export const MACRO_INDICATORS = [
  { id: "CPI_US_ALL_ITEMS_SA", label: "CPI 헤드라인" },
  { id: "CPI_US_CORE_SA", label: "CPI 코어" },
  { id: "US_UNEMPLOYMENT_RATE", label: "실업률" },
  { id: "US_FED_FUNDS_RATE", label: "연방기금금리" },
  { id: "US_TREASURY_10Y_YIELD", label: "미국 10년 국채금리" },
] as const;

export const EOD_SYMBOL_UNIVERSE = [
  { symbol: "SPY", group: "INDEX", label: "SP500" },
  { symbol: "VOO", group: "INDEX", label: "SP500" },
  { symbol: "QQQ", group: "INDEX", label: "NASDAQ100" },
  { symbol: "DIA", group: "INDEX", label: "DOW30" },
  { symbol: "SCHD", group: "INDEX", label: "US_DIVIDEND" },
  { symbol: "IWM", group: "INDEX", label: "RUSSELL2000" },
  { symbol: "DVY", group: "INDEX", label: "US_DIVIDEND_SELECT" },
  { symbol: "VIG", group: "INDEX", label: "US_DIVIDEND_APPRECIATION" },
  { symbol: "EWY", group: "COUNTRY", label: "SOUTH_KOREA" },
  { symbol: "ASHR", group: "COUNTRY", label: "CHINA_A_SHARES" },
  { symbol: "CQQQ", group: "COUNTRY", label: "CHINA_TECH" },
  { symbol: "EWJ", group: "COUNTRY", label: "JAPAN" },
  { symbol: "INDA", group: "COUNTRY", label: "INDIA" },
  { symbol: "IAU", group: "COMMODITY", label: "GOLD" },
  { symbol: "GDX", group: "COMMODITY", label: "GOLD_MINERS" },
  { symbol: "SLV", group: "COMMODITY", label: "SILVER" },
  { symbol: "USO", group: "COMMODITY", label: "CRUDE_OIL" },
  { symbol: "XOP", group: "COMMODITY", label: "OIL_PRODUCERS" },
  { symbol: "UNG", group: "COMMODITY", label: "NATURAL_GAS" },
  { symbol: "DBA", group: "COMMODITY", label: "AGRICULTURE" },
  { symbol: "TLT", group: "BOND", label: "US_TREASURY_20Y" },
  { symbol: "HYG", group: "BOND", label: "US_HIGH_YIELD" },
  { symbol: "LQD", group: "BOND", label: "US_INVESTMENT_GRADE" },
  { symbol: "SHY", group: "BOND", label: "US_TREASURY_1_3Y" },
  { symbol: "TIP", group: "BOND", label: "US_TIPS" },
  { symbol: "XLV", group: "SECTOR", label: "HEALTH_CARE" },
  { symbol: "XLE", group: "SECTOR", label: "ENERGY" },
  { symbol: "SOXX", group: "SECTOR", label: "SEMICONDUCTOR" },
  { symbol: "XLF", group: "SECTOR", label: "FINANCIALS" },
  { symbol: "KRE", group: "SECTOR", label: "REGIONAL_BANKS" },
  { symbol: "NLR", group: "SECTOR", label: "NUCLEAR" },
  { symbol: "XLK", group: "SECTOR", label: "INFORMATION_TECH" },
  { symbol: "XLB", group: "SECTOR", label: "MATERIALS" },
  { symbol: "XLY", group: "SECTOR", label: "CONSUMER_DISCRETIONARY" },
  { symbol: "XLP", group: "SECTOR", label: "CONSUMER_STAPLES" },
  { symbol: "XLC", group: "SECTOR", label: "COMMUNICATION_SERVICES" },
  { symbol: "XLRE", group: "SECTOR", label: "REAL_ESTATE" },
  { symbol: "XLU", group: "SECTOR", label: "UTILITIES" },
  { symbol: "XLI", group: "SECTOR", label: "INDUSTRIALS" },
  { symbol: "^VIX", group: "VOLATILITY_INDEX", label: "CBOE_VOLATILITY_INDEX" },
  { symbol: "^SKEW", group: "VOLATILITY_INDEX", label: "CBOE_SKEW_INDEX" },
] as const;

export function PageState({
  title,
  detail,
  endpoint,
}: {
  title: string;
  detail: string;
  endpoint?: string;
}) {
  return (
    <div className="panel state-panel">
      <PanelHead title={title} sub={endpoint} />
      <p>{detail}</p>
    </div>
  );
}

export function ErrorState({ error, endpoint }: { error: unknown; endpoint?: string }) {
  return (
    <PageState
      title="API 오류"
      detail={error instanceof Error ? error.message : "알 수 없는 오류가 발생했습니다."}
      endpoint={endpoint}
    />
  );
}

export function EmptyState({ endpoint }: { endpoint?: string }) {
  return <PageState title="데이터가 없습니다" detail="요청한 조건에 해당하는 관측 row가 없습니다." endpoint={endpoint} />;
}

export function Disclaimer({ children }: { children: ReactNode }) {
  return <div className="footnote">{children}</div>;
}

export function JsonBlock({ value }: { value: JsonValue | Record<string, unknown> }) {
  return <CodeBlock>{JSON.stringify(value, null, 2)}</CodeBlock>;
}

export function ExplainReportView({ response }: { response: ExplainResponse }) {
  const report = response.report;
  const isMock = response.model_id === "mock";

  return (
    <div className="explain-report">
      <div className="explain-meta">
        <span>model_id={response.model_id}</span>
        <span>prompt_version={response.prompt_version}</span>
        <span>built_at={response.built_at}</span>
      </div>
      {isMock ? (
        <div className="explain-warning">
          현재 cache는 mock provider로 생성된 placeholder입니다. 실제 설명 cache가 생성되면 이 영역은 관측 근거 요약으로 대체됩니다.
        </div>
      ) : null}
      {renderExplainBody(response)}
    </div>
  );
}

export function NumberCell({
  value,
  digits = 2,
  signed = false,
}: {
  value?: number | null;
  digits?: number;
  signed?: boolean;
}) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return <span className="num-tab muted">UNKNOWN</span>;
  }
  const sign = signed && value > 0 ? "+" : "";
  const tone = signed && value < 0 ? "negative" : signed && value > 0 ? "positive" : "";
  return <span className={`num-tab ${tone}`}>{sign}{value.toFixed(digits)}</span>;
}

export function IntCell({ value }: { value?: number | null }) {
  if (value === null || value === undefined) {
    return <span className="num-tab muted">UNKNOWN</span>;
  }
  return <span className="num-tab">{value.toLocaleString("ko-KR")}</span>;
}

export function StatusPill({ state }: { state: "SUCCESS" | "PAUSED" }) {
  return (
    <Pill variant={state === "SUCCESS" ? "pit-safe" : "unknown"} dot={false} style={{ height: 18, fontSize: 10 }}>
      {state}
    </Pill>
  );
}

function renderExplainBody(response: ExplainResponse) {
  if (response.use_case === "regime") {
    return (
      <>
        <ExplainSection title="축별 상태" value={textValue(response.report.ahs_summary)} />
        <ExplainSection title="시장 위치" value={textValue(response.report.market_position)} />
        <ExplainSection title="전환 관측" value={textValue(response.report.transition)} />
        <ExplainSection title="주의" value={textValue(response.report.disclaimer)} muted />
      </>
    );
  }

  if (response.use_case === "similarity_regime" || response.use_case === "similarity_gold") {
    const neighbors = Array.isArray(response.report.neighbors) ? response.report.neighbors : [];
    return (
      <>
        <ExplainSection title="요약" value={textValue(response.report.summary)} />
        <div className="explain-section">
          <div className="explain-section-title">유사 구간 근거</div>
          {neighbors.length ? (
            <div className="explain-list">
              {neighbors.map((neighbor, index) => (
                <div className="explain-list-item" key={index}>
                  {renderNeighbor(neighbor)}
                </div>
              ))}
            </div>
          ) : (
            <p className="muted">cache에 유사 구간 근거가 포함되지 않았습니다.</p>
          )}
        </div>
        <ExplainSection title="주의" value={textValue(response.report.disclaimer)} muted />
      </>
    );
  }

  const indicators = Array.isArray(response.report.indicators) ? response.report.indicators : [];
  return (
    <>
      <div className="explain-section">
        <div className="explain-section-title">거시 지표 해석</div>
        {indicators.length ? (
          <div className="explain-list">
            {indicators.map((indicator, index) => (
              <div className="explain-list-item" key={index}>
                {renderIndicator(indicator)}
              </div>
            ))}
          </div>
        ) : (
          <p className="muted">cache에 지표별 해석이 포함되지 않았습니다.</p>
        )}
      </div>
      <ExplainSection title="주의" value={textValue(response.report.disclaimer)} muted />
    </>
  );
}

function ExplainSection({ title, value, muted = false }: { title: string; value: string; muted?: boolean }) {
  return (
    <div className="explain-section">
      <div className="explain-section-title">{title}</div>
      <p className={muted ? "muted" : ""}>{value || "설명 cache에 값이 없습니다."}</p>
    </div>
  );
}

function renderNeighbor(value: JsonValue) {
  const row = objectValue(value);
  const reasons = Array.isArray(row.match_reasons) ? row.match_reasons.map(textValue).filter(Boolean) : [];
  return (
    <>
      <div className="explain-list-head">
        <span>{textValue(row.neighbor_date) || "UNKNOWN"}</span>
        <span>rank={textValue(row.rank) || "UNKNOWN"} · score={textValue(row.score) || "UNKNOWN"}</span>
      </div>
      <p>{reasons.length ? reasons.join(" ") : "근거 문장이 cache에 포함되지 않았습니다."}</p>
    </>
  );
}

function renderIndicator(value: JsonValue) {
  const row = objectValue(value);
  return (
    <>
      <div className="explain-list-head">
        <span>{textValue(row.indicator_id) || "UNKNOWN"}</span>
        <span>value={textValue(row.current_value) || "UNKNOWN"} · regime={textValue(row.regime) || "UNKNOWN"}</span>
      </div>
      <p>{textValue(row.narrative) || "지표 해석 문장이 cache에 포함되지 않았습니다."}</p>
    </>
  );
}

function objectValue(value: JsonValue): Record<string, JsonValue> {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value;
  }
  return {};
}

function textValue(value: JsonValue | undefined): string {
  if (value === null || value === undefined) {
    return "";
  }
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return "";
}

export function MiniStrip() {
  const variants: PillVariant[] = [
    "warn",
    "warn",
    "unknown",
    "silver",
    "silver",
    "silver",
    "pit-safe",
    "pit-safe",
    "gold",
    "gold",
    "silver",
    "pit-safe",
    "gold",
    "gold",
    "pit-safe",
    "pit-safe",
    "gold",
    "gold",
  ];
  return (
    <div className="strip" aria-label="최근 관측 strip">
      {variants.map((variant, index) => (
        <div
          className="seg"
          key={`${variant}-${index}`}
          style={{ background: `var(--${variant})`, opacity: variant === "unknown" ? 0.35 : 1 }}
        />
      ))}
    </div>
  );
}

export function getMaxDate(meta: MetaResponse | undefined, table: string): string {
  const item = meta?.tables[table];
  return item?.max_trade_date ?? item?.max_query_date ?? "";
}

export function addDays(dateText: string, days: number): string {
  if (!dateText) {
    return "";
  }
  const date = new Date(`${dateText}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

export function selectValueClass(value?: number | null): string {
  if (value === null || value === undefined) {
    return "muted";
  }
  if (value > 0) {
    return "positive";
  }
  if (value < 0) {
    return "negative";
  }
  return "";
}
