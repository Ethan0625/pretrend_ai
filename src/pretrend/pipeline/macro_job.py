from __future__ import annotations

import os
import argparse
import logging
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Optional, Sequence, List, Dict, Any

import pandas as pd

from pretrend.pipeline.ingest.base import IngestContext
from pretrend.pipeline.ingest.macro import (
    MacroFetcher,
    MacroNormalizer,
    MacroWriter,
    VintageNormalizer,
    VintageWriter,
    EconEventsNormalizer,
    EconEventsWriter,
)
from pretrend.pipeline.calendar.config import CalendarConfig
from pretrend.pipeline.calendar.fred_vintages import (
    FredVintagesRunContext,
    normalize_fred_vintages,
    write_silver_fred_vintages,
)
from pretrend.pipeline.calendar.econ_events import (
    EconEventsRunContext,
    normalize_econ_events,
    write_silver_econ_events,
)
from pretrend.pipeline.calendar.runner import (
    load_bronze_fred_vintages,
    load_bronze_econ_events,
)
from pretrend.pipeline.features.macro_features import (
    MacroFeatureConfig,
    MacroFeatureRunContext,
    load_bronze_macro,
    build_macro_features,
    write_silver_macro_features,
)


logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )


class RunMode(str, Enum):
    """Macro Job 실행 모드.

    - incremental: 지정 구간만 ingest/feature 수행
    - full: 전체 재계산 용도 (현재는 스켈레톤 수준, 구현 TBD)
    """

    INCREMENTAL = "incremental"
    FULL = "full"


@dataclass
class MacroJobConfig:
    """Macro Bronze→Silver Job 공통 설정."""

    data_root: Path = Path("data")
    meta_root: Path = Path("data/meta")
    lookback_months: int = 12
    run_mode: RunMode = RunMode.INCREMENTAL

    @property
    def bronze_root(self) -> Path:
        """Bronze macro econ_indicators 루트 경로."""
        return self.data_root / "bronze" / "macro" / "econ_indicators"

    @property
    def silver_root(self) -> Path:
        """Silver macro_features 루트 경로."""
        return self.data_root / "silver" / "macro" / "macro_features"

    @property
    def ingest_output_root(self) -> Path:
        """IngestContext.output_root에 들어갈 루트."""
        return self.data_root / "bronze"

    @property
    def macro_job_log_path(self) -> Path:
        """MacroJob 메타 로그 파일 경로."""
        return self.meta_root / "macro_job_log.parquet"

    @classmethod
    def from_env(cls, run_mode: RunMode = RunMode.INCREMENTAL) -> "MacroJobConfig":
        data_root_str = os.getenv("PRETREND_DATA_ROOT", "data")
        data_root = Path(data_root_str)
        meta_root = data_root / "meta"
        return cls(data_root=data_root, meta_root=meta_root, run_mode=run_mode)


@dataclass
class MacroTaskResult:
    """각 단계(Bronze/Silver)의 결과 메타 정보."""

    row_count: int = 0
    partitions: List[str] | None = None
    extra: Dict[str, Any] | None = None


@dataclass
class MacroJobResult:
    """전체 Macro Job 실행 결과."""

    start_date: date
    end_date: date
    run_id: str
    run_mode: RunMode
    bronze_result: MacroTaskResult
    silver_result: MacroTaskResult
    bronze_vintage_result: MacroTaskResult | None = None
    bronze_econ_events_result: MacroTaskResult | None = None
    silver_calendar_result: MacroTaskResult | None = None


class MacroJobRunner:
    """Macro Bronze→Silver End-to-End 러너."""

    def __init__(self, config: MacroJobConfig) -> None:
        self.config = config

    # ---------------------------
    # Public API
    # ---------------------------
    def run(
        self,
        start_date: date,
        end_date: date,
    ) -> MacroJobResult:
        """Macro Bronze→Silver 전체 파이프라인 실행."""
        run_id = datetime.utcnow().strftime("macrojob_%Y%m%dT%H%M%SZ")
        logger.info(
            "Starting MacroJob run_id=%s, mode=%s, start=%s, end=%s",
            run_id,
            self.config.run_mode.value,
            start_date,
            end_date,
        )

        bronze_result = self._run_bronze_ingest(start_date, end_date, run_id)
        bronze_vintage_result = self._run_bronze_vintages(start_date, end_date, run_id)
        bronze_econ_events_result = self._run_bronze_econ_events(start_date, end_date, run_id)
        silver_result = self._run_silver_features(start_date, end_date, run_id)
        silver_calendar_result = self._run_silver_calendar(run_id)

        logger.info(
            "MacroJob finished. run_id=%s, bronze_rows=%s, silver_rows=%s, "
            "vintage_rows=%s, econ_events_rows=%s, calendar_rows=%s",
            run_id,
            bronze_result.row_count,
            silver_result.row_count,
            bronze_vintage_result.row_count,
            bronze_econ_events_result.row_count,
            silver_calendar_result.row_count,
        )

        result = MacroJobResult(
            start_date=start_date,
            end_date=end_date,
            run_id=run_id,
            run_mode=self.config.run_mode,
            bronze_result=bronze_result,
            silver_result=silver_result,
            bronze_vintage_result=bronze_vintage_result,
            bronze_econ_events_result=bronze_econ_events_result,
            silver_calendar_result=silver_calendar_result,
        )

        # 🔹 여기서 메타 로그 기록
        self._log_job_result(result)

        return result

    # ---------------------------
    # 내부 단계: Bronze Ingest
    # ---------------------------
    def _run_bronze_ingest(
        self,
        start_date: date,
        end_date: date,
        run_id: str,
    ) -> MacroTaskResult:
        """FRED → Bronze econ_indicators ingest 실행."""
        logger.info(
            "[Bronze] macro ingest start. start=%s, end=%s, output_root=%s",
            start_date,
            end_date,
            self.config.ingest_output_root,
        )

        # IngestContext 구성
        ctx = IngestContext(
            domain="macro",
            dataset="econ_indicators",
            run_id=run_id,
            start_date=start_date,
            end_date=end_date,
            output_root=self.config.ingest_output_root,
            # meta_root는 기본값 data/meta 사용
        )

        fetcher = MacroFetcher()
        normalizer = MacroNormalizer()
        writer = MacroWriter()

        raw_df = fetcher.fetch(ctx)
        if raw_df is None or raw_df.empty:
            logger.warning("[Bronze] No data fetched from FRED.")
            return MacroTaskResult(row_count=0, partitions=[])

        norm_df = normalizer.normalize(ctx, raw_df)
        if norm_df is None or norm_df.empty:
            logger.warning("[Bronze] Normalized dataframe is empty.")
            return MacroTaskResult(row_count=0, partitions=[])

        writer.write(ctx, norm_df)

        # 결과 메타 정보 계산
        row_count = int(len(norm_df))
        partitions = self._extract_partitions_from_dates(norm_df["date"])

        logger.info(
            "[Bronze] macro ingest done. rows=%s, partitions=[%s]",
            row_count,
            ", ".join(partitions),
        )

        return MacroTaskResult(
            row_count=row_count,
            partitions=partitions,
            extra={},
        )

    # ---------------------------
    # 내부 단계: Bronze Calendar Vintages
    # ---------------------------
    def _run_bronze_vintages(
        self,
        start_date: date,
        end_date: date,
        run_id: str,
    ) -> MacroTaskResult:
        """FRED vintage 데이터를 수집하여 Bronze Calendar에 적재."""
        logger.info(
            "[Bronze] vintage ingest start. start=%s, end=%s",
            start_date, end_date,
        )

        ctx = IngestContext(
            domain="calendar",
            dataset="fred_vintages",
            run_id=run_id,
            start_date=start_date,
            end_date=end_date,
            output_root=self.config.ingest_output_root,
        )

        fetcher = MacroFetcher()
        normalizer = VintageNormalizer()
        writer = VintageWriter()

        raw_df = fetcher.fetch_vintages(ctx)
        if raw_df is None or raw_df.empty:
            logger.warning("[Bronze] No vintage data fetched from FRED.")
            return MacroTaskResult(row_count=0, partitions=[])

        norm_df = normalizer.normalize(ctx, raw_df)
        if norm_df is None or norm_df.empty:
            logger.warning("[Bronze] Normalized vintage dataframe is empty.")
            return MacroTaskResult(row_count=0, partitions=[])

        writer.write(ctx, norm_df)

        row_count = int(len(norm_df))
        partitions = self._extract_partitions_from_dates(
            pd.Series(norm_df["observation_date"])
        )

        logger.info(
            "[Bronze] vintage ingest done. rows=%s, partitions=[%s]",
            row_count, ", ".join(partitions),
        )
        return MacroTaskResult(row_count=row_count, partitions=partitions)

    # ---------------------------
    # 내부 단계: Bronze Calendar Econ Events
    # ---------------------------
    def _run_bronze_econ_events(
        self,
        start_date: date,
        end_date: date,
        run_id: str,
    ) -> MacroTaskResult:
        """FRED release/dates API로 econ_events를 수집하여 Bronze Calendar에 적재."""
        logger.info(
            "[Bronze] econ_events ingest start. start=%s, end=%s",
            start_date, end_date,
        )

        ctx = IngestContext(
            domain="calendar",
            dataset="econ_events",
            run_id=run_id,
            start_date=start_date,
            end_date=end_date,
            output_root=self.config.ingest_output_root,
        )

        fetcher = MacroFetcher()
        normalizer = EconEventsNormalizer()
        writer = EconEventsWriter()

        raw_df = fetcher.fetch_econ_events(ctx)
        if raw_df is None or raw_df.empty:
            logger.warning("[Bronze] No econ_events data fetched from FRED.")
            return MacroTaskResult(row_count=0, partitions=[])

        norm_df = normalizer.normalize(ctx, raw_df)
        if norm_df is None or norm_df.empty:
            logger.warning("[Bronze] Normalized econ_events dataframe is empty.")
            return MacroTaskResult(row_count=0, partitions=[])

        writer.write(ctx, norm_df)

        row_count = int(len(norm_df))
        partitions = self._extract_partitions_from_dates(
            pd.Series(norm_df["observation_date"])
        )

        logger.info(
            "[Bronze] econ_events ingest done. rows=%s, partitions=[%s]",
            row_count, ", ".join(partitions),
        )
        return MacroTaskResult(row_count=row_count, partitions=partitions)

    # ---------------------------
    # 내부 단계: Silver Calendar (fred_vintages + econ_events)
    # ---------------------------
    def _run_silver_calendar(self, run_id: str) -> MacroTaskResult:
        """Bronze Calendar → Silver Calendar (fred_vintages + econ_events)."""
        cal_cfg = CalendarConfig(data_root=self.config.data_root)
        total_rows = 0

        # ── fred_vintages Silver ──
        logger.info("[Silver] calendar fred_vintages start.")
        fred_ctx = FredVintagesRunContext(
            run_id=run_id,
            ingestion_ts=pd.Timestamp.utcnow(),
            cfg=cal_cfg,
        )
        bronze_fred = load_bronze_fred_vintages(cal_cfg)
        if bronze_fred.empty:
            logger.warning("[Silver] No bronze vintage data. Skip fred_vintages.")
        else:
            silver_fred = normalize_fred_vintages(bronze_fred, fred_ctx)
            write_silver_fred_vintages(silver_fred, fred_ctx)
            total_rows += len(silver_fred)
            logger.info("[Silver] calendar fred_vintages done. rows=%s", len(silver_fred))

        # ── econ_events Silver ──
        logger.info("[Silver] calendar econ_events start.")
        econ_ctx = EconEventsRunContext(
            run_id=run_id,
            ingestion_ts=pd.Timestamp.utcnow(),
            cfg=cal_cfg,
        )
        bronze_econ = load_bronze_econ_events(cal_cfg)
        if bronze_econ.empty:
            logger.warning("[Silver] No bronze econ_events data. Skip econ_events.")
        else:
            silver_econ = normalize_econ_events(bronze_econ, econ_ctx)
            write_silver_econ_events(silver_econ, econ_ctx)
            total_rows += len(silver_econ)
            logger.info("[Silver] calendar econ_events done. rows=%s", len(silver_econ))

        return MacroTaskResult(row_count=total_rows)

    # ---------------------------
    # 내부 단계: Silver Features
    # ---------------------------
    def _run_silver_features(
        self,
        start_date: date,
        end_date: date,
        run_id: str,
    ) -> MacroTaskResult:
        """Bronze → Silver macro_features 변환 실행."""
        logger.info(
            "[Silver] macro features start. feature_start=%s, feature_end=%s, "
            "bronze_root=%s, silver_root=%s",
            start_date,
            end_date,
            self.config.bronze_root,
            self.config.silver_root,
        )

        # 기존 macro_features 구조 재사용
        default_cfg = MacroFeatureConfig.from_defaults()
        feat_cfg = MacroFeatureConfig(
            bronze_root=self.config.bronze_root,
            silver_root=self.config.silver_root,
            target_indicators=default_cfg.target_indicators,  # 기본값(5개 지표) 사용 시 from_defaults()와 동일 동작
        )

        feat_ctx = MacroFeatureRunContext(
            feature_start_date=start_date,
            feature_end_date=end_date,
            run_id=run_id,
            ingestion_ts=pd.Timestamp.now("UTC"),
            cfg=feat_cfg,
            lookback_months=self.config.lookback_months,
        )

        df_bronze = load_bronze_macro(feat_ctx)
        if df_bronze is None or df_bronze.empty:
            logger.warning("[Silver] No bronze data in given range. Skip silver.")
            return MacroTaskResult(row_count=0, partitions=[])

        df_silver = build_macro_features(df_bronze, feat_ctx)
        if df_silver is None or df_silver.empty:
            logger.warning("[Silver] No silver features generated.")
            return MacroTaskResult(row_count=0, partitions=[])

        write_silver_macro_features(df_silver, feat_ctx)

        row_count = int(len(df_silver))
        partitions = self._extract_partitions_from_dates(df_silver["date"])

        logger.info(
            "[Silver] macro features done. rows=%s, partitions=[%s]",
            row_count,
            ", ".join(partitions),
        )

        return MacroTaskResult(
            row_count=row_count,
            partitions=partitions,
            extra={},
        )

    # ---------------------------
    # Helper
    # ---------------------------
    @staticmethod
    def _extract_partitions_from_dates(date_series: pd.Series) -> List[str]:
        """date 컬럼으로부터 year/month 파티션 문자열 리스트 생성."""
        if date_series.empty:
            return []
        dates = pd.to_datetime(date_series)
        keys = sorted(set(zip(dates.dt.year, dates.dt.month)))
        return [f"year={y:04d}/month={m:02d}" for y, m in keys]
    
    def _log_job_result(self, result: MacroJobResult) -> None:
        """
        MacroJob 실행 메타 정보를 data/meta/macro_job_log.parquet에 적재.
        - 파일이 이미 있으면 읽어서 append 후 다시 저장
        - 실패해도 파이프라인 자체는 실패시키지 않고 로그만 남김
        """
        log_path = self.config.macro_job_log_path
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)

            bv = result.bronze_vintage_result or MacroTaskResult()
            be = result.bronze_econ_events_result or MacroTaskResult()
            sc = result.silver_calendar_result or MacroTaskResult()
            record = {
                "job_type": "macro_bronze_silver",
                "run_id": result.run_id,
                "run_mode": result.run_mode.value,
                "start_date": pd.to_datetime(result.start_date),
                "end_date": pd.to_datetime(result.end_date),
                "bronze_row_count": result.bronze_result.row_count,
                "silver_row_count": result.silver_result.row_count,
                "bronze_vintage_row_count": bv.row_count,
                "bronze_econ_events_row_count": be.row_count,
                "silver_calendar_row_count": sc.row_count,
                "bronze_partitions": ",".join(result.bronze_result.partitions or []),
                "silver_partitions": ",".join(result.silver_result.partitions or []),
                "created_at": pd.Timestamp.utcnow(),
            }

            df_new = pd.DataFrame([record])

            if log_path.exists():
                df_old = pd.read_parquet(log_path)
                df = pd.concat([df_old, df_new], ignore_index=True)
            else:
                df = df_new

            df.to_parquet(log_path, index=False)
            logger.info("[Meta] Saved MacroJob log to %s", log_path)
        except Exception:
            # 메타 로깅 실패는 파이프라인 실패로 간주하지 않고 경고만 남긴다.
            logger.exception("[Meta] Failed to write MacroJob log")


# ======================
# CLI Entry Point
# ======================

def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Macro Bronze→Silver E2E job runner",
    )
    parser.add_argument(
        "--start",
        type=str,
        required=True,
        help="시작 날짜 (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end",
        type=str,
        required=True,
        help="종료 날짜 (YYYY-MM-DD, inclusive)",
    )
    parser.add_argument(
        "--mode",
        type=str,
        default=RunMode.INCREMENTAL.value,
        choices=[m.value for m in RunMode],
        help="실행 모드 (incremental / full)",
    )
    return parser.parse_args(argv)


def _parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as e:
        raise ValueError(f"날짜 파싱 실패: {value} (형식: YYYY-MM-DD)") from e


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = _parse_args(argv)
    start_date = _parse_date(args.start)
    end_date = _parse_date(args.end)
    run_mode = RunMode(args.mode)

    config = MacroJobConfig.from_env(run_mode=run_mode)
    runner = MacroJobRunner(config=config)

    result = runner.run(start_date=start_date, end_date=end_date)

    # 요약 로그 (Airflow/XCom 등과 연동할 때 사용 가능)
    logger.info(
        "MacroJob summary: run_id=%s, mode=%s, "
        "start=%s, end=%s, bronze_rows=%s, silver_rows=%s, "
        "vintage_rows=%s, econ_events_rows=%s, calendar_rows=%s",
        result.run_id,
        result.run_mode.value,
        result.start_date,
        result.end_date,
        result.bronze_result.row_count,
        result.silver_result.row_count,
        result.bronze_vintage_result.row_count if result.bronze_vintage_result else 0,
        result.bronze_econ_events_result.row_count if result.bronze_econ_events_result else 0,
        result.silver_calendar_result.row_count if result.silver_calendar_result else 0,
    )


if __name__ == "__main__":
    main()
