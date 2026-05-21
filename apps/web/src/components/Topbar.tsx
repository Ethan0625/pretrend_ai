import { Pill } from "./primitives/Pill";

export interface TopbarProps {
  env?: string;
  alembic?: string;
  apiLatencyMs?: number | null;
  onRefresh?: () => void;
}

export function Topbar({ env = "local", alembic = "unknown", apiLatencyMs, onRefresh }: TopbarProps) {
  const envLabel = env.toLowerCase() === "local" ? "로컬" : env;
  const latencyLabel = apiLatencyMs == null ? "/health" : `/health · ${apiLatencyMs}ms`;

  return (
    <header className="topbar">
      <div className="topbar-left">
        <div className="wordmark">
          Pretrend<span className="accent" />
        </div>
        <span className="env-chip">환경 · {envLabel}</span>
        <span className="t-mono topbar-meta">
          alembic <span className="topbar-meta-strong">{alembic}</span>
        </span>
      </div>
      <div className="topbar-right">
        <Pill variant="pit-safe">정상</Pill>
        <span className="t-mono topbar-meta">{latencyLabel}</span>
        <button className="btn btn-secondary btn-sm" type="button" onClick={onRefresh}>
          <span aria-hidden="true">↻</span>
          새로 고침
        </button>
      </div>
    </header>
  );
}
