import { PanelHead } from "./PanelHead";
import { Pill } from "./Pill";

const nodes = [
  {
    variant: "bronze" as const,
    label: "BRONZE",
    name: "원천 (Bronze)",
    meta: "raw ingest · preserved",
  },
  {
    variant: "silver" as const,
    label: "SILVER",
    name: "정규화 (Silver)",
    meta: "normalize · dedup",
  },
  {
    variant: "gold" as const,
    label: "GOLD",
    name: "PIT-safe (Gold)",
    meta: "parquet · partitioned",
    emphasis: true,
  },
  {
    variant: "info" as const,
    label: "SERVING",
    name: "서빙",
    meta: "postgres · FastAPI",
  },
];

export function LineageStrip() {
  return (
    <div className="panel">
      <PanelHead
        title="데이터 흐름"
        sub="data/bronze -> data/silver -> data/gold -> postgres (serving mirror)"
        right={<Pill variant="pit-safe">PIT-SAFE</Pill>}
      />
      <div className="lineage-rail">
        {nodes.map((node, index) => (
          <FragmentNode key={node.label} showArrow={index < nodes.length - 1} {...node} />
        ))}
      </div>
      <div className="lineage-foot">
        <span className="t-mono">run_id_gold = latest · ingestion_ts_gold = latest</span>
        <span className="t-mono">gold_postgres_sync_dag · 0 11 * * * KST</span>
      </div>
    </div>
  );
}

interface FragmentNodeProps {
  variant: "bronze" | "silver" | "gold" | "info";
  label: string;
  name: string;
  meta: string;
  emphasis?: boolean;
  showArrow: boolean;
}

function FragmentNode({ variant, label, name, meta, emphasis = false, showArrow }: FragmentNodeProps) {
  return (
    <>
      <div className={`lineage-node ${emphasis ? "gold" : ""}`}>
        <Pill variant={variant} dot={false} style={{ height: 18, fontSize: 10 }}>
          {label}
        </Pill>
        <span className="lineage-name">{name}</span>
        <span className="lineage-meta">{meta}</span>
      </div>
      {showArrow ? <span className="lineage-arrow">-&gt;</span> : null}
    </>
  );
}
