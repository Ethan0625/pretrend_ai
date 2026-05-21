export const chartColors = {
  gold: "var(--gold)",
  pitSafe: "var(--pit-safe)",
  danger: "var(--danger)",
  silver: "var(--silver)",
  info: "var(--info)",
  warn: "var(--warn)",
  grid: "var(--border-subtle)",
  text: "var(--fg-muted)",
} as const;

export const axisTick = {
  fill: chartColors.text,
  fontFamily: "var(--font-mono)",
  fontSize: 11,
};

export const tooltipStyle = {
  background: "var(--bg-surface)",
  border: "1px solid var(--border-subtle)",
  borderRadius: "8px",
  color: "var(--fg-default)",
  fontFamily: "var(--font-sans)",
  fontSize: "12px",
};

export function formatDate(value: string): string {
  return value.slice(0, 10);
}

export function formatNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "UNKNOWN";
  }
  return value.toLocaleString("ko-KR", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  });
}

export function formatPercent(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "UNKNOWN";
  }
  const scaled = value * 100;
  const sign = scaled > 0 ? "+" : "";
  return `${sign}${scaled.toLocaleString("ko-KR", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  })}%`;
}

export function finiteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function addUtcDays(dateText: string, days: number): string {
  const date = new Date(`${dateText}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}
