from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict

import os
from pathlib import Path

import pendulum
from airflow.decorators import dag, task

from pretrend.pipeline.ingest.eod import (
    EodIngestConfig,
    run_eod_bronze_ingest,
)
from pretrend.pipeline.features.eod_features import (
    EodFeatureConfig,
    run_eod_silver_features,
)
from pretrend.pipeline.features.gold_eod_features import (
    build_gold_eod_features,
    load_silver_eod_features,
    write_gold_eod_features,
)


# ---------------------------
# 미국장 마지막 완전 거래일 계산
# ---------------------------

def get_last_us_trading_date(now_et: pendulum.DateTime | None = None) -> date:
    """
    미국장(US/Eastern) 기준 '마지막 완전한 거래일'을 계산.
    - market_close = 16:00 ET
    - buffer = 2시간 (데이터 확정/반영 여유)
    - 주말(토/일)은 직전 금요일로 롤백
    - 미국 공휴일은 아직 미반영(TODO)
    """
    if now_et is None:
        now_et = pendulum.now("US/Eastern")

    MARKET_CLOSE_HOUR = 16
    BUFFER_HOURS = 2

    # 장 마감 + 버퍼 이전이면 '어제'까지가 완전한 거래일
    if now_et.hour < MARKET_CLOSE_HOUR + BUFFER_HOURS:
        candidate = (now_et - timedelta(days=1)).date()
    else:
        candidate = now_et.date()

    # 주말이면 직전 평일까지 롤백
    while candidate.weekday() >= 5:  # 5=토, 6=일
        candidate -= timedelta(days=1)

    return candidate


# ---------------------------
# Airflow DAG 정의
# ---------------------------

DEFAULT_ARGS: Dict[str, Any] = {
    "owner": "pretrend",
    "retries": 2,
    "retry_delay": timedelta(minutes=15),
    "depends_on_past": False,
}


@dag(
    dag_id="eod_pipeline_dag",
    description="미국장 기준 마지막 완전 거래일 EOD Bronze→Silver→Gold E2E 파이프라인",
    default_args=DEFAULT_ARGS,
    # 매일 한 번 돌리되, 실제 대상 날짜는 get_last_us_trading_date()로 결정
    start_date=pendulum.datetime(2010, 1, 1, tz="Asia/Seoul"),
    schedule="0 8 * * *",  # 매일 08:00 KST (미국 장 마감 후 2시간+)
    catchup=False,
    max_active_runs=1,
    tags=["pretrend", "eod", "bronze", "silver", "gold"],
)
def eod_pipeline():
    """
    EOD Bronze→Silver→Gold 전체를 한 번에 수행하는 Airflow DAG.

    - data_interval_start를 US/Eastern으로 변환하여 대상 거래일을 결정.
      backfill/scheduled run 모두 논리 실행일 기준으로 처리.
    - Bronze ingest(Observability SOT 32개 ETF) → Silver Feature → Gold fact mart 순차 실행.
    """

    @task(task_id="ensure_data_lake_bootstrap")
    def ensure_data_lake_bootstrap_task() -> Dict[str, Any]:
        from pretrend.ops.backfill_once import run_backfill_once

        return run_backfill_once()

    @task(task_id="run_eod_bronze_ingest")
    def run_eod_bronze_ingest_task(
        _bootstrap_summary: Dict[str, Any],
        **context: Any,
    ) -> Dict[str, Any]:
        # 1) Airflow data_interval_start → US/Eastern 변환 (backfill 호환)
        data_interval_start = context["data_interval_start"]
        now_et = data_interval_start.in_tz("US/Eastern")

        # 2) 마지막 완전한 거래일 계산
        target_date: date = get_last_us_trading_date(now_et)

        # 3) EOD ingest 구간은 target_date 하루
        start_dt = target_date
        end_dt = target_date

        # 4) Config 준비 (data_root는 PRETREND_DATA_ROOT 또는 기본 'data')
        data_root = Path(os.getenv("PRETREND_DATA_ROOT", "data"))
        cfg = EodIngestConfig(data_root=data_root)

        # 5) EOD Bronze ingest 실행 (기본 심볼: cfg.default_symbols → Observability SOT)
        result = run_eod_bronze_ingest(
            start_date=start_dt,
            end_date=end_dt,
            cfg=cfg,
        )

        summary: Dict[str, Any] = {
            "bronze_run_id": result.run_id,
            "start_date": str(result.start_date),
            "end_date": str(result.end_date),
            "row_count": result.row_count,
            "symbols": ",".join(result.symbols),
            "target_date": str(target_date),
            "data_interval_et": now_et.to_iso8601_string(),
        }
        return summary

    @task(task_id="run_eod_silver_features")
    def run_eod_silver_features_task(bronze_summary: Dict[str, Any]) -> Dict[str, Any]:
        """
        Bronze 요약(XCom) 정보를 받아 동일 날짜/심볼에 대해 Silver Feature 생성.
        """
        # Bronze 결과에서 대상 날짜/심볼 가져오기
        start_dt = date.fromisoformat(bronze_summary["start_date"])
        end_dt = date.fromisoformat(bronze_summary["end_date"])
        symbols_str = bronze_summary["symbols"]
        symbols = [s.strip() for s in symbols_str.split(",") if s.strip()]

        # Silver Config (PRETREND_DATA_ROOT 기반)
        cfg = EodFeatureConfig.from_env()

        result = run_eod_silver_features(
            start_date=start_dt,
            end_date=end_dt,
            symbols=symbols,
            cfg=cfg,
        )

        summary: Dict[str, Any] = {
            "silver_run_id": result.run_id,
            "start_date": str(result.start_date),
            "end_date": str(result.end_date),
            "row_count": result.row_count,
            "symbols": ",".join(result.symbols),
        }
        return summary

    @task(task_id="run_eod_gold_features")
    def run_eod_gold_features_task(silver_summary: Dict[str, Any]) -> Dict[str, Any]:
        """
        Silver 요약(XCom) 정보를 받아 동일 날짜/심볼에 대해 Gold Feature 생성.
        """
        import pandas as pd

        start_dt = date.fromisoformat(silver_summary["start_date"])
        end_dt = date.fromisoformat(silver_summary["end_date"])
        symbols_str = silver_summary["symbols"]
        symbols = [s.strip() for s in symbols_str.split(",") if s.strip()]

        data_root = Path(os.getenv("PRETREND_DATA_ROOT", "data"))
        silver_root = data_root / "silver" / "eod" / "eod_features"
        gold_root = data_root / "gold" / "eod" / "eod_features"
        run_id = pd.Timestamp.now("UTC").strftime("gold_eod_%Y%m%d%H%M%S")

        df_silver = load_silver_eod_features(
            silver_root, start_date=start_dt, end_date=end_dt, symbols=symbols,
        )
        if df_silver.empty:
            return {
                "gold_run_id": run_id,
                "start_date": str(start_dt),
                "end_date": str(end_dt),
                "row_count": 0,
                "symbols": "",
            }

        gold_df = build_gold_eod_features(df_silver, run_id=run_id)
        write_gold_eod_features(gold_df, gold_root, run_id)

        summary: Dict[str, Any] = {
            "gold_run_id": run_id,
            "start_date": str(start_dt),
            "end_date": str(end_dt),
            "row_count": int(len(gold_df)),
            "symbols": ",".join(sorted(gold_df["symbol"].unique().tolist())),
        }
        return summary

    bootstrap_summary = ensure_data_lake_bootstrap_task()
    bronze_summary = run_eod_bronze_ingest_task(bootstrap_summary)
    silver_summary = run_eod_silver_features_task(bronze_summary)
    run_eod_gold_features_task(silver_summary)


eod_pipeline_dag = eod_pipeline()
