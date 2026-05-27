export interface IncidentSummary {
  id: string;
  date: string;
  area: string;
  severity: "Critical" | "High" | "Medium" | "Low";
  status: "Draft" | "Investigating" | "Resolved" | "Monitoring" | "Deferred";
  symptom: string;
  rootCause: string;
  guard: string;
  detailPath: string;
}

export const INCIDENTS: IncidentSummary[] = [
  {
    id: "P-101",
    date: "2026-05-20",
    area: "Docker Runtime",
    severity: "Medium",
    status: "Resolved",
    symptom: "Public image pull이 credential helper 오류로 실패",
    rootCause: "Windows Docker Desktop credential helper가 현재 로그인 세션에서 응답하지 않음",
    guard: "credential helper troubleshooting을 운영 가이드와 RUN_LOG에 고정",
    detailPath: "https://github.com/Ethan0625/pretrend_ai/blob/main/docs/operation/incidents/P-101-docker-credential-helper.md",
  },
  {
    id: "P-102",
    date: "2026-05-27",
    area: "Postgres / API",
    severity: "High",
    status: "Monitoring",
    symptom: "/health는 200이지만 DB 의존 API가 500 또는 timeout",
    rootCause: "Postgres crash recovery 중 API healthcheck가 DB readiness를 대표하지 못함",
    guard: "/api/v1/meta freshness check와 Postgres recovery runbook을 운영 가이드에 고정",
    detailPath: "https://github.com/Ethan0625/pretrend_ai/blob/main/docs/operation/incidents/P-102-postgres-crash-recovery.md",
  },
  {
    id: "P-103",
    date: "2026-05-27",
    area: "EOD Pipeline",
    severity: "High",
    status: "Resolved",
    symptom: "짧은 증분 backfill이 전체 backfill처럼 오래 실행됨",
    rootCause: "EOD Silver가 Bronze 전체를 rglob로 읽은 뒤 날짜 필터링",
    guard: "날짜 window 기반 partition pruning과 old corrupt partition 방어 테스트 추가",
    detailPath: "https://github.com/Ethan0625/pretrend_ai/blob/main/docs/operation/incidents/P-103-eod-silver-window-scan.md",
  },
  {
    id: "P-104",
    date: "2026-05-27",
    area: "Regime Similarity",
    severity: "Medium",
    status: "Deferred",
    symptom: "Gold/EOD freshness는 최신인데 similarity_regime만 과거 날짜에 머묾",
    rootCause: "regime similarity source가 legacy strategy_job snapshot에 의존",
    guard: "P33 이후 Observability regime runtime snapshot 독립화 task로 분리",
    detailPath: "https://github.com/Ethan0625/pretrend_ai/blob/main/docs/operation/incidents/P-104-regime-snapshot-dependency.md",
  },
];
