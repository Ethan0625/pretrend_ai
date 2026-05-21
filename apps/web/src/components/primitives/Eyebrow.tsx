import type { CSSProperties, ReactNode } from "react";

export interface EyebrowProps {
  children: ReactNode;
  style?: CSSProperties;
}

export function Eyebrow({ children, style }: EyebrowProps) {
  return (
    <div className="t-label" style={style}>
      {children}
    </div>
  );
}
