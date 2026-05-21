export type DagState = "SUCCESS" | "PAUSED";

export interface DagFixture {
  dag: string;
  schedule: string;
  state: DagState;
  track: string;
  lastRun: string;
}

export const DAGS_FIXTURE: DagFixture[] = [
  {
    dag: "eod_pipeline_dag",
    schedule: "0 8 * * *",
    state: "SUCCESS",
    track: "Infrastructure",
    lastRun: "latest scheduled run",
  },
  {
    dag: "macro_pipeline_dag",
    schedule: "0 9 * * *",
    state: "SUCCESS",
    track: "Infrastructure",
    lastRun: "latest scheduled run",
  },
  {
    dag: "gold_postgres_sync_dag",
    schedule: "0 11 * * *",
    state: "SUCCESS",
    track: "Observability",
    lastRun: "latest scheduled run",
  },
  {
    dag: "similarity_build_dag",
    schedule: "0 12 * * *",
    state: "SUCCESS",
    track: "Observability",
    lastRun: "latest scheduled run",
  },
  {
    dag: "explainability_build_dag",
    schedule: "0 13 * * *",
    state: "SUCCESS",
    track: "Observability",
    lastRun: "latest scheduled run",
  },
  {
    dag: "strategy_engine_dag",
    schedule: "0 10 * * *",
    state: "PAUSED",
    track: "Personal (Frozen)",
    lastRun: "-",
  },
];
