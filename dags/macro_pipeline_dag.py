from __future__ import annotations

from datetime import timedelta, date, datetime
from typing import Any, Dict

import pendulum
from airflow.decorators import dag, task

# pretrend_ai는 pyproject + pip install -e . 로 설치되어 있다고 가정
from pretrend.pipeline.macro_job import MacroJobConfig, MacroJobRunner


# Airflow 기본 인자
DEFAULT_ARGS: Dict[str, Any] = {
    "owner": "pretrend",
    "retries": 3,
    "retry_delay": timedelta(minutes=10),
    "depends_on_past": False,
}


@dag(
    dag_id="macro_pipeline_dag",
    description="FRED Macro Bronze→Silver E2E 파이프라인 (월별)",
    default_args=DEFAULT_ARGS,
    # 매월 1일 06:00 Asia/Seoul
    start_date=datetime(2010, 1, 1),
    schedule_interval="0 9 * * *",  # 매일 09:00 KST
    catchup=False,          # 과거 월들도 필요하면 backfill 가능
    max_active_runs=1,     # 한 번에 하나만 실행
    tags=["pretrend", "macro", "bronze", "silver"],
)
def macro_pipeline():
    """
    Macro Bronze→Silver 전체를 한 번에 수행하는 Airflow DAG.

    Airflow 2.4+의 data interval 개념을 사용:
      - data_interval_start: 해당 월의 시작일 (inclusive)
      - data_interval_end:   다음 월의 시작일 (exclusive)

    실제 macro_job 실행 구간:
      start_date = data_interval_start
      end_date   = data_interval_end - 1일
    예)
      2025-11-01 실행 → [2025-10-01, 2025-10-31] 구간 처리
    """

    @task(task_id="run_macro_job")
    def run_macro_job_task(**context: Any) -> Dict[str, Any]:
        # Airflow에서 넘겨주는 logical data interval
        data_interval_start = context.get("data_interval_start")
        data_interval_end = context.get("data_interval_end")

        if data_interval_start is None or data_interval_end is None:
            raise ValueError("data_interval_start / data_interval_end is required")

        # pendulum.DateTime → date 로 변환
        start_dt: date = data_interval_start.date()
        end_dt: date = (data_interval_end - timedelta(days=1)).date()

        # MacroJobConfig.from_env() 안에서 PRETREND_DATA_ROOT 등 읽도록 구현되어 있다고 가정
        config = MacroJobConfig.from_env()
        runner = MacroJobRunner(config=config)

        # 실제 Bronze → Silver → 메타로그까지 한 번에 실행
        result = runner.run(start_date=start_dt, end_date=end_dt)

        # XCom으로 요약 정보만 반환 (UI에서 확인용)
        summary: Dict[str, Any] = {
            "run_id": result.run_id,
            "run_mode": result.run_mode.value,
            "start_date": str(result.start_date),
            "end_date": str(result.end_date),
            "bronze_row_count": result.bronze_result.row_count,
            "silver_row_count": result.silver_result.row_count,
        }

        return summary

    run_macro_job_task()
    
macro_pipeline_dag = macro_pipeline()