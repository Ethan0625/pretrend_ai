import { LineageStrip } from "@/components/primitives/LineageStrip";
import { PanelHead } from "@/components/primitives/PanelHead";
import { Pill } from "@/components/primitives/Pill";
import { StatCard } from "@/components/primitives/StatCard";
import { useEod, useMacro, useMeta, useRegime, useSimilarity } from "@/api/hooks";
import type { EodFeature, MacroFeature } from "@/api/types";

import {
  Disclaimer,
  EmptyState,
  ErrorState,
  IntCell,
  MiniStrip,
  NumberCell,
  PageState,
  getMaxDate,
} from "./_shared";

export function Overview() {
  const meta = useMeta();
  const latestRegimeDate = getMaxDate(meta.data, "gold_market_state_similarity_feature");
  const latestSimilarityDate = getMaxDate(meta.data, "similarity_regime") || latestRegimeDate;
  const latestMacroDate = getMaxDate(meta.data, "gold_macro_features");
  const latestEodDate = getMaxDate(meta.data, "gold_eod_features");

  const regime = useRegime(latestRegimeDate);
  const similarity = useSimilarity(latestSimilarityDate, "regime", 5);
  const macroCpi = useMacro(latestMacroDate, "CPI_US_ALL_ITEMS_SA");
  const macroUnrate = useMacro(latestMacroDate, "US_UNEMPLOYMENT_RATE");
  const macroDgs10 = useMacro(latestMacroDate, "US_TREASURY_10Y_YIELD");
  const eodSpy = useEod("SPY", latestEodDate);
  const eodQqq = useEod("QQQ", latestEodDate);
  const eodIwm = useEod("IWM", latestEodDate);
  const eodTlt = useEod("TLT", latestEodDate);

  if (meta.isLoading) {
    return <PageState title="불러오는 중" detail="serving table freshness를 확인하고 있습니다." endpoint="/api/v1/meta" />;
  }
  if (meta.error) {
    return <ErrorState error={meta.error} endpoint="/api/v1/meta" />;
  }
  if (!meta.data) {
    return <EmptyState endpoint="/api/v1/meta" />;
  }

  const macroRows = [macroCpi.data?.data, macroUnrate.data?.data, macroDgs10.data?.data].filter(
    Boolean,
  ) as MacroFeature[];
  const eodRows = [eodSpy.data?.data, eodQqq.data?.data, eodIwm.data?.data, eodTlt.data?.data].filter(
    Boolean,
  ) as EodFeature[];
  const explainRows = Object.values(meta.data.explainability_use_cases).reduce((acc, count) => acc + count, 0);

  return (
    <>
      <div className="grid-4">
        <StatCard
          eyebrow="gold_macro_features"
          value={<IntCell value={meta.data.tables.gold_macro_features?.row_count} />}
          sub={`max_trade_date · ${meta.data.tables.gold_macro_features?.max_trade_date ?? "UNKNOWN"}`}
        />
        <StatCard
          eyebrow="gold_eod_features"
          value={<IntCell value={meta.data.tables.gold_eod_features?.row_count} />}
          sub={`max_trade_date · ${meta.data.tables.gold_eod_features?.max_trade_date ?? "UNKNOWN"}`}
        />
        <StatCard
          eyebrow="similarity_regime"
          value={<IntCell value={meta.data.tables.similarity_regime?.row_count} />}
          sub={`max_query_date · ${meta.data.tables.similarity_regime?.max_query_date ?? "UNKNOWN"}`}
        />
        <StatCard eyebrow="explainability_cache" value={<IntCell value={explainRows} />} sub="cached reports by use_case" />
      </div>

      <LineageStrip />

      <div className="grid-2">
        <div className="panel">
          <PanelHead title="시장 국면 미리보기" sub={`GET /api/v1/regime?trade_date=${latestRegimeDate}`} right={<Pill variant="gold">GOLD</Pill>} />
          {regime.isLoading ? <PageState title="불러오는 중" detail="국면 feature를 조회하고 있습니다." /> : null}
          {regime.error ? <ErrorState error={regime.error} /> : null}
          {regime.data ? (
            <>
              <MiniStrip />
              <FeatureTable feature={regime.data.feature} />
            </>
          ) : null}
        </div>

        <div className="panel">
          <PanelHead title="유사 시기 미리보기" sub={`GET /api/v1/similarity?query_date=${latestSimilarityDate}&view=regime&top_n=5`} right={<Pill variant="silver">REGIME</Pill>} />
          {similarity.isLoading ? <PageState title="불러오는 중" detail="과거 유사 시기를 조회하고 있습니다." /> : null}
          {similarity.error ? <ErrorState error={similarity.error} /> : null}
          {similarity.data ? <SimilarityTable rows={similarity.data.neighbors} /> : null}
        </div>
      </div>

      <MacroPreview rows={macroRows} loading={macroCpi.isLoading || macroUnrate.isLoading || macroDgs10.isLoading} />
      <EodPreview rows={eodRows} loading={eodSpy.isLoading || eodQqq.isLoading || eodIwm.isLoading || eodTlt.isLoading} />

      <Disclaimer>
        Pretrend는 관측 전용입니다. 매수/매도 권고 또는 목표 수익률을 제시하지 않습니다. 화면의 값은 Gold/Serving layer의 현재 관측값입니다.
      </Disclaimer>
    </>
  );
}

function FeatureTable({ feature }: { feature: Record<string, string | number | null> }) {
  return (
    <table className="tbl">
      <tbody>
        {Object.entries(feature).slice(0, 8).map(([key, value]) => (
          <tr key={key}>
            <td>{key}</td>
            <td>{value === null ? <span className="muted">UNKNOWN</span> : String(value)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function SimilarityTable({ rows }: { rows: Array<{ rank: number; neighbor_date: string; score: number; gap_days: number }> }) {
  return (
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
        {rows.map((row) => (
          <tr key={row.rank}>
            <td>{row.rank}</td>
            <td>{row.neighbor_date}</td>
            <td><NumberCell value={row.score} digits={4} /></td>
            <td>{row.gap_days}d</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function MacroPreview({ rows, loading }: { rows: MacroFeature[]; loading: boolean }) {
  return (
    <div className="panel">
      <PanelHead title="거시지표 미리보기" sub="GET /api/v1/macro" right={<Pill variant="gold">GOLD</Pill>} />
      {loading ? <PageState title="불러오는 중" detail="거시지표 row를 조회하고 있습니다." /> : null}
      <table className="tbl">
        <thead>
          <tr>
            <th>indicator_id</th>
            <th>selected_value</th>
            <th>delta_1m</th>
            <th>delta_6m</th>
            <th>zscore_12m</th>
            <th>regime</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.indicator_id}>
              <td>{row.indicator_id}</td>
              <td><NumberCell value={row.selected_value} digits={3} /></td>
              <td><NumberCell value={row.delta_1m} digits={4} signed /></td>
              <td><NumberCell value={row.delta_6m} digits={4} signed /></td>
              <td><NumberCell value={row.zscore_12m} digits={3} signed /></td>
              <td>{row.regime ?? <span className="muted">UNKNOWN</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function EodPreview({ rows, loading }: { rows: EodFeature[]; loading: boolean }) {
  return (
    <div className="panel">
      <PanelHead title="ETF 미리보기" sub="GET /api/v1/eod" right={<Pill variant="gold">GOLD</Pill>} />
      {loading ? <PageState title="불러오는 중" detail="ETF row를 조회하고 있습니다." /> : null}
      <table className="tbl">
        <thead>
          <tr>
            <th>symbol</th>
            <th>asset_group</th>
            <th>asset_name</th>
            <th>close</th>
            <th>ret_20d</th>
            <th>vol_60d</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.symbol}>
              <td>{row.symbol}</td>
              <td>{row.asset_group}</td>
              <td>{row.asset_name}</td>
              <td><NumberCell value={row.close} digits={2} /></td>
              <td><NumberCell value={row.ret_20d} digits={4} signed /></td>
              <td><NumberCell value={row.vol_60d} digits={4} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
