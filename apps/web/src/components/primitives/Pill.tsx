import type { CSSProperties, ReactNode } from "react";

export type PillVariant =
  | "bronze"
  | "silver"
  | "gold"
  | "pit-safe"
  | "warn"
  | "danger"
  | "unknown"
  | "info";

export interface PillProps {
  children: ReactNode;
  variant?: PillVariant;
  dot?: boolean;
  style?: CSSProperties;
}

export function Pill({ children, variant = "info", dot = true, style }: PillProps) {
  return (
    <span className={`pill pill-${variant}`} style={style}>
      {dot ? <span className="dot" /> : null}
      {children}
    </span>
  );
}
