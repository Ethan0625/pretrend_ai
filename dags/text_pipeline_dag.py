from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List

import pendulum
from airflow.decorators import dag, task

from pretrend.pipeline.text.bronze_ingest import run_text_bronze_ingest
from pretrend.pipeline.text.config import TextPipelineConfig
from pretrend.pipeline.text.gold_build import run_text_gold_build
from pretrend.pipeline.text.gold_llm_build import run_text_gold_llm_build
from pretrend.pipeline.text.silver_build import run_text_silver_build


DEFAULT_ARGS: Dict[str, Any] = {
    "owner": "pretrend",
    "retries": 2,
    "retry_delay": timedelta(minutes=15),
    "depends_on_past": False,
}


def _build_text_cfg() -> TextPipelineConfig:
    data_root = Path(os.getenv("PRETREND_DATA_ROOT", "data"))
    cfg = TextPipelineConfig.default()
    cfg.data_root = data_root
    cfg.bronze_root = data_root / "bronze" / "text"
    cfg.silver_root = data_root / "silver" / "text"
    cfg.gold_root = data_root / "gold" / "text"
    cfg.gold_llm_root = data_root / "gold" / "text"
    return cfg


@dag(
    dag_id="text_pipeline_dag",
    description="Text Pipeline Bronze(SEC+Fed)→Silver→Gold→Gold LLM E2E",
    default_args=DEFAULT_ARGS,
    start_date=pendulum.datetime(2026, 1, 1, tz="Asia/Seoul"),
    schedule_interval="30 9 * * *",
    catchup=False,
    max_active_runs=1,
    tags=["pretrend", "text", "bronze", "silver", "gold", "llm"],
)
def text_pipeline():
    @task(task_id="run_text_bronze_ingest")
    def run_text_bronze_ingest_task(**context: Any) -> Dict[str, Any]:
        data_interval_start = context["data_interval_start"]
        target_date: date = data_interval_start.date()
        cfg = _build_text_cfg()

        results = run_text_bronze_ingest(
            sources=["sec", "fed"],
            start_date=target_date,
            end_date=target_date,
            cfg=cfg,
            ingest_date=target_date,
        )
        summary_results: List[Dict[str, Any]] = []
        for r in results:
            summary_results.append(
                {
                    "source": r.source,
                    "success": r.success,
                    "docs_fetched": int(r.docs_fetched),
                    "docs_written": int(r.docs_written),
                    "docs_skipped_duplicate": int(r.docs_skipped_duplicate),
                    "error": r.error,
                }
            )
        return {
            "sources": "sec,fed",
            "start_date": target_date.isoformat(),
            "end_date": target_date.isoformat(),
            "results": summary_results,
        }

    @task(task_id="run_text_silver_build")
    def run_text_silver_build_task(bronze_summary: Dict[str, Any]) -> Dict[str, Any]:
        start_dt = date.fromisoformat(str(bronze_summary["start_date"]))
        end_dt = date.fromisoformat(str(bronze_summary["end_date"]))
        cfg = _build_text_cfg()
        result = run_text_silver_build(start_date=start_dt, end_date=end_dt, cfg=cfg)
        return {
            "start_date": start_dt.isoformat(),
            "end_date": end_dt.isoformat(),
            "docs_input": int(result.docs_input),
            "docs_output": int(result.docs_output),
            "docs_deduped": int(result.docs_deduped),
            "event_dates": list(result.event_dates),
            "error": result.error,
        }

    @task(task_id="run_text_gold_build")
    def run_text_gold_build_task(silver_summary: Dict[str, Any]) -> Dict[str, Any]:
        start_dt = date.fromisoformat(str(silver_summary["start_date"]))
        end_dt = date.fromisoformat(str(silver_summary["end_date"]))
        cfg = _build_text_cfg()
        result = run_text_gold_build(start_date=start_dt, end_date=end_dt, cfg=cfg)
        return {
            "start_date": start_dt.isoformat(),
            "end_date": end_dt.isoformat(),
            "feature_rows": int(result.feature_rows),
            "trade_dates": list(result.trade_dates),
            "error": result.error,
        }

    @task(task_id="run_text_gold_llm_build")
    def run_text_gold_llm_build_task(gold_summary: Dict[str, Any]) -> Dict[str, Any]:
        """Gold LLM annotation (observer-only, fail-open)."""
        start_dt = date.fromisoformat(str(gold_summary["start_date"]))
        end_dt = date.fromisoformat(str(gold_summary["end_date"]))
        cfg = _build_text_cfg()
        result = run_text_gold_llm_build(start_date=start_dt, end_date=end_dt, cfg=cfg)
        return {
            "start_date": start_dt.isoformat(),
            "end_date": end_dt.isoformat(),
            "docs_input": int(result.docs_input),
            "docs_processed": int(result.docs_processed),
            "docs_skipped": int(result.docs_skipped),
            "feature_rows": int(result.feature_rows),
            "coverage_ratio": float(result.coverage_ratio),
            "error": result.error,
        }

    bronze = run_text_bronze_ingest_task()
    silver = run_text_silver_build_task(bronze)
    gold = run_text_gold_build_task(silver)
    run_text_gold_llm_build_task(gold)


text_pipeline_dag = text_pipeline()
