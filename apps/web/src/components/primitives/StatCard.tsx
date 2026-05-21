import type { ReactNode } from "react";

import { Eyebrow } from "./Eyebrow";

export interface StatCardProps {
  eyebrow: string;
  value: ReactNode;
  sub: string;
  accent?: string;
}

export function StatCard({ eyebrow, value, sub, accent }: StatCardProps) {
  return (
    <div className="panel">
      <Eyebrow style={{ color: "var(--fg-faint)" }}>{eyebrow}</Eyebrow>
      <div className="t-h2 num-tab stat-value" style={{ color: accent ?? "var(--fg-strong)" }}>
        {value}
      </div>
      <div className="t-small stat-sub">{sub}</div>
    </div>
  );
}
