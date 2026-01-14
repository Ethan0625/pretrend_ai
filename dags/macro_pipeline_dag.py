from __future__ import annotations

from datetime import timedelta, date, datetime
from typing import Any, Dict

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
    description="FRED Macro Bronze→Silver E2E 파이프라인 (매일, 누락 대비 롤링 재수집)",
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
    운영 목표:
      - DAG는 매일 트리거되지만, 실행이 누락될 수 있음을 전제로 한다.
      - 따라서 매 실행마다 일정 기간(롤링 윈도우)을 재수집/재처리하여 누락을 보완한다.
      - 출력은 파티션 overwrite 기반 멱등성을 전제로 한다.

    기준일(anchor_date):
      - Airflow의 data_interval_start.date()를 사용(매일 스케줄에서 '실행 논리일').

    처리 구간(예시: 월 기반 + 버퍼):
      - start_date: anchor_date가 속한 월의 1일에서 1개월을 더 뺀 날짜(= 직전월 1일)
      - end_date:   anchor_date - 1일(= 어제)
    """

    @task(task_id="run_macro_job")
    def run_macro_job_task(**context: Any) -> Dict[str, Any]:
        # Airflow에서 넘겨주는 logical data interval
        data_interval_start = context.get("data_interval_start")
        data_interval_end = context.get("data_interval_end")

        if data_interval_start is None or data_interval_end is None:
            raise ValueError("data_interval_start / data_interval_end is required")

        anchor_date: date = data_interval_start.date()
        end_dt: date = anchor_date - timedelta(days=1)

        # 직전월 1일 ~ 어제 (월 단위로 넓게 재수집)
        first_of_this_month = end_dt.replace(day=1)
        # 직전월 1일: 이번달 1일에서 1일 빼고(day=1)
        prev_month_last_day = first_of_this_month - timedelta(days=1)
        start_dt: date = prev_month_last_day.replace(day=1)

        config = MacroJobConfig.from_env()
        runner = MacroJobRunner(config=config)

        # 실제 Bronze → Silver → 메타로그까지 한 번에 실행
        result = runner.run(start_date=start_dt, end_date=end_dt)

        summary = {
            "run_id": result.run_id,
            "run_mode": result.run_mode.value,
            "start_date": str(result.start_date),
            "end_date": str(result.end_date),
            "anchor_date": str(anchor_date),
            "bronze_row_count": result.bronze_result.row_count,
            "silver_row_count": result.silver_result.row_count,
        }
        
        return summary

    run_macro_job_task()


macro_pipeline_dag = macro_pipeline()