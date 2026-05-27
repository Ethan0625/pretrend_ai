import { useMemo, useState } from "react";

import { PanelHead } from "@/components/primitives/PanelHead";
import { Pill } from "@/components/primitives/Pill";
import { Toolbar } from "@/components/Toolbar";
import { useMeta, useRegime, useRegimeExplain, useRegimeTimeline } from "@/api/hooks";
import type { RegimeFeature } from "@/api/types";
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
              <RegimeSnapshot feature={regime.data.feature} />
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
    mid_regime_code: featureNumber(row.feature.mid_regime_code),
    short_signal_code: featureNumber(row.feature.short_signal_code),
    sojourn_prob_10d: featureNumber(row.feature.sojourn_prob_10d),
    transition_hazard_10d: featureNumber(row.feature.transition_hazard_10d),
  }));
}

function featureNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function RegimeSnapshot({ feature }: { feature: RegimeFeature }) {
  const midRegime = featureNumber(feature.mid_regime_code);
  const shortSignal = featureNumber(feature.short_signal_code);
  const transitionHazard = featureNumber(feature.transition_hazard_10d);
  const sojournProb = featureNumber(feature.sojourn_prob_10d);
  const riskGate = featureNumber(feature.risk_gate_flag);
  const runUniverse = featureNumber(feature.run_universe_flag);

  return (
    <div className="metric-strip">
      <SnapshotMetric
        label="중기 국면"
        sub={`mid_regime_code=${formatCode(midRegime)}`}
        tone={stateTone(midRegime)}
        value={stateLabel(midRegime, "mid")}
      />
      <SnapshotMetric
        label="단기 신호"
        sub={`short_signal_code=${formatCode(shortSignal)}`}
        tone={stateTone(shortSignal)}
        value={stateLabel(shortSignal, "short")}
      />
      <SnapshotMetric
        label="10일 전환 위험"
        sub={`sojourn_prob_10d=${formatProbability(sojournProb)}`}
        value={formatProbability(transitionHazard)}
      />
      <SnapshotMetric
        label="리스크 게이트"
        sub={`run_universe_flag=${flagLabel(runUniverse)}`}
        tone={riskGate === 1 ? "negative" : ""}
        value={flagLabel(riskGate)}
      />
    </div>
  );
}

function SnapshotMetric({
  label,
  sub,
  tone = "",
  value,
}: {
  label: string;
  sub: string;
  tone?: string;
  value: string;
}) {
  return (
    <div className="metric-cell">
      <div className="metric-label">{label}</div>
      <div className={`metric-value ${tone}`}>{value}</div>
      <div className="metric-sub">{sub}</div>
    </div>
  );
}

function stateLabel(value: number | null, kind: "mid" | "short"): string {
  if (value === null) {
    return "UNKNOWN";
  }
  if (kind === "mid") {
    if (value > 0) {
      return "RISK_ON";
    }
    if (value < 0) {
      return "RISK_OFF";
    }
    return "NEUTRAL";
  }
  if (value > 0) {
    return "RELIEF";
  }
  if (value < 0) {
    return "PANIC";
  }
  return "STABLE";
}

function stateTone(value: number | null): string {
  if (value === null || value === 0) {
    return "";
  }
  return value > 0 ? "positive" : "negative";
}

function flagLabel(value: number | null): string {
  if (value === null) {
    return "UNKNOWN";
  }
  return value === 1 ? "ON" : "OFF";
}

function formatCode(value: number | null): string {
  return value === null ? "UNKNOWN" : value.toFixed(0);
}

function formatProbability(value: number | null): string {
  if (value === null) {
    return "UNKNOWN";
  }
  return `${(value * 100).toLocaleString("ko-KR", {
    maximumFractionDigits: 1,
    minimumFractionDigits: 1,
  })}%`;
}
