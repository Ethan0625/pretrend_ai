import { LineageStrip } from "@/components/primitives/LineageStrip";
import { PanelHead } from "@/components/primitives/PanelHead";
import { Pill } from "@/components/primitives/Pill";
import { useMeta } from "@/api/hooks";

import { EmptyState, ErrorState, IntCell, PageState } from "./_shared";

export function Lineage() {
  const meta = useMeta();

  if (meta.isLoading) {
    return <PageState title="불러오는 중" detail="serving freshness를 확인하고 있습니다." endpoint="/api/v1/meta" />;
  }
  if (meta.error) {
    return <ErrorState error={meta.error} endpoint="/api/v1/meta" />;
  }
  if (!meta.data) {
    return <EmptyState endpoint="/api/v1/meta" />;
  }

  return (
    <>
      <LineageStrip />
      <div className="panel">
        <PanelHead title="Serving freshness" sub="GET /api/v1/meta" right={<Pill variant="pit-safe">READ-ONLY</Pill>} />
        <table className="tbl">
          <thead>
            <tr>
              <th>table</th>
              <th>row_count</th>
              <th>max_trade_date</th>
              <th>max_query_date</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(meta.data.tables).map(([table, info]) => (
              <tr key={table}>
                <td>{table}</td>
                <td><IntCell value={info.row_count} /></td>
                <td>{info.max_trade_date ?? "-"}</td>
                <td>{info.max_query_date ?? "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
