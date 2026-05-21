import type { ReactNode } from "react";

export interface PanelHeadProps {
  title: string;
  sub?: string;
  right?: ReactNode;
}

export function PanelHead({ title, sub, right }: PanelHeadProps) {
  return (
    <div className="panel-head">
      <div className="panel-head-copy">
        <div className="panel-title">{title}</div>
        {sub ? <div className="panel-sub">{sub}</div> : null}
      </div>
      {right ? <div className="panel-head-right">{right}</div> : null}
    </div>
  );
}
