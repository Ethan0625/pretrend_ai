"""
EOD Bronze → Silver → Gold End-to-End Job Runner.

macro_job.py 패턴을 따르며, 3단계를 순차 실행한다:
  1. Bronze ingest (yfinance → Parquet)
  2. Silver features (기술적 지표)
  3. Gold features (fact mart + labels + lineage)

Usage:
    python -m pretrend.pipeline.eod_job --start 2024-06-01 --end 2024-06-30
    python -m pretrend.pipeline.eod_job --start 2024-06-01 --end 2024-06-30 --symbols SPY,QQQ
"""
from __future__ import annotations

import argparse
import logging
import os
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd

from pretrend.pipeline.ingest.eod import (
    EodIngestConfig,
    EodIngestResult,
    run_eod_bronze_ingest,
)
from pretrend.pipeline.features.eod_features import (
    EodFeatureConfig,
    EodFeatureResult,
    run_eod_silver_features,
)
from pretrend.pipeline.features.gold_eod_features import (
    build_gold_eod_features,
    load_silver_eod_features,
    write_gold_eod_features,
)

logger = logging.getLogger(__name__)


# ── Config ─────────────────────────────────────────────


@dataclass
class EodJobConfig:
    """EOD Bronze→Silver→Gold Job 공통 설정."""

    data_root: Path = field(default_factory=lambda: Path("data"))
    meta_root: Path = field(default_factory=lambda: Path("data/meta"))

    @property
    def bronze_root(self) -> Path:
        return self.data_root / "bronze" / "eod" / "daily_prices"

    @property
    def silver_root(self) -> Path:
        return self.data_root / "silver" / "eod" / "eod_features"

    @property
    def gold_root(self) -> Path:
        return self.data_root / "gold" / "eod" / "eod_features"

    @property
    def eod_job_log_path(self) -> Path:
        return self.meta_root / "eod_job_log.parquet"

    @classmethod
    def from_env(cls) -> "EodJobConfig":
        data_root = Path(os.getenv("PRETREND_DATA_ROOT", "data"))
        return cls(data_root=data_root, meta_root=data_root / "meta")


# ── Result ─────────────────────────────────────────────


@dataclass
class EodTaskResult:
    """각 단계의 결과 메타 정보."""

    row_count: int = 0
    symbols: List[str] = field(default_factory=list)
    run_id: str = ""


@dataclass
class EodJobResult:
    """전체 EOD Job 실행 결과."""

    start_date: date
    end_date: date
    run_id: str
    bronze_result: EodTaskResult
    silver_result: EodTaskResult
    gold_result: EodTaskResult


# ── Runner ─────────────────────────────────────────────


class EodJobRunner:
    """EOD Bronze→Silver→Gold End-to-End 러너."""

    def __init__(self, config: EodJobConfig) -> None:
        self.config = config

    def run(
        self,
        start_date: date,
        end_date: date,
        symbols: Optional[List[str]] = None,
    ) -> EodJobResult:
        """EOD Bronze→Silver→Gold 전체 파이프라인 실행."""
        run_id = pd.Timestamp.now("UTC").strftime("eodjob_%Y%m%dT%H%M%SZ")
        logger.info(
            "Starting EodJob run_id=%s, start=%s, end=%s, symbols=%s",
            run_id, start_date, end_date, symbols,
        )

        bronze_result = self._run_bronze_ingest(start_date, end_date, symbols)
        silver_result = self._run_silver_features(start_date, end_date, symbols)
        gold_result = self._run_gold_features(start_date, end_date, run_id, symbols)

        logger.info(
            "EodJob finished. run_id=%s, bronze=%s rows, silver=%s rows, gold=%s rows",
            run_id,
            bronze_result.row_count,
            silver_result.row_count,
            gold_result.row_count,
        )

        result = EodJobResult(
            start_date=start_date,
            end_date=end_date,
            run_id=run_id,
            bronze_result=bronze_result,
            silver_result=silver_result,
            gold_result=gold_result,
        )

        self._log_job_result(result)
        return result

    # ── Bronze ──

    def _run_bronze_ingest(
        self,
        start_date: date,
        end_date: date,
        symbols: Optional[List[str]] = None,
    ) -> EodTaskResult:
        logger.info("[Bronze] EOD ingest start. start=%s, end=%s", start_date, end_date)

        cfg = EodIngestConfig(data_root=self.config.data_root)
        result: EodIngestResult = run_eod_bronze_ingest(
            start_date=start_date,
            end_date=end_date,
            symbols=symbols,
            cfg=cfg,
        )

        logger.info(
            "[Bronze] EOD ingest done. rows=%s, symbols=%s",
            result.row_count, len(result.symbols),
        )
        return EodTaskResult(
            row_count=result.row_count,
            symbols=result.symbols,
            run_id=result.run_id,
        )

    # ── Silver ──

    def _run_silver_features(
        self,
        start_date: date,
        end_date: date,
        symbols: Optional[List[str]] = None,
    ) -> EodTaskResult:
        logger.info("[Silver] EOD features start. start=%s, end=%s", start_date, end_date)

        cfg = EodFeatureConfig(data_root=self.config.data_root)
        result: EodFeatureResult = run_eod_silver_features(
            start_date=start_date,
            end_date=end_date,
            symbols=symbols,
            cfg=cfg,
        )

        logger.info(
            "[Silver] EOD features done. rows=%s, symbols=%s",
            result.row_count, len(result.symbols),
        )
        return EodTaskResult(
            row_count=result.row_count,
            symbols=result.symbols,
            run_id=result.run_id,
        )

    # ── Gold ──

    def _run_gold_features(
        self,
        start_date: date,
        end_date: date,
        run_id: str,
        symbols: Optional[List[str]] = None,
    ) -> EodTaskResult:
        logger.info("[Gold] EOD features start. start=%s, end=%s", start_date, end_date)

        df_silver = load_silver_eod_features(
            self.config.silver_root,
            start_date=start_date,
            end_date=end_date,
            symbols=symbols,
        )
        if df_silver.empty:
            logger.warning("[Gold] No Silver EOD data. Skip Gold.")
            return EodTaskResult(row_count=0)

        gold_df = build_gold_eod_features(df_silver, run_id=run_id)
        if gold_df.empty:
            logger.warning("[Gold] No Gold features generated.")
            return EodTaskResult(row_count=0)

        write_gold_eod_features(gold_df, self.config.gold_root, run_id)

        sym_list = sorted(gold_df["symbol"].unique().tolist())
        logger.info(
            "[Gold] EOD features done. rows=%s, symbols=%s",
            len(gold_df), len(sym_list),
        )
        return EodTaskResult(
            row_count=int(len(gold_df)),
            symbols=sym_list,
            run_id=run_id,
        )

    # ── Meta log ──

    def _log_job_result(self, result: EodJobResult) -> None:
        """EOD Job 메타 로그를 data/meta/eod_job_log.parquet에 적재."""
        log_path = self.config.eod_job_log_path
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)

            record: Dict[str, Any] = {
                "job_type": "eod_bronze_silver_gold",
                "run_id": result.run_id,
                "start_date": pd.to_datetime(result.start_date),
                "end_date": pd.to_datetime(result.end_date),
                "bronze_row_count": result.bronze_result.row_count,
                "silver_row_count": result.silver_result.row_count,
                "gold_row_count": result.gold_result.row_count,
                "bronze_symbols": ",".join(result.bronze_result.symbols),
                "created_at": pd.Timestamp.now("UTC"),
            }

            df_new = pd.DataFrame([record])

            if log_path.exists():
                df_old = pd.read_parquet(log_path)
                df = pd.concat([df_old, df_new], ignore_index=True)
            else:
                df = df_new

            df.to_parquet(log_path, index=False)
            logger.info("[Meta] Saved EodJob log to %s", log_path)
        except Exception:
            logger.exception("[Meta] Failed to write EodJob log")


# ── CLI ────────────────────────────────────────────────


def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="EOD Bronze→Silver→Gold E2E job runner",
    )
    parser.add_argument(
        "--start", type=str, required=True, help="시작 날짜 (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end", type=str, required=True, help="종료 날짜 (YYYY-MM-DD, inclusive)",
    )
    parser.add_argument(
        "--symbols",
        type=str,
        default=None,
        help="Comma separated symbols (e.g. SPY,QQQ). If omitted, Observability SOT.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

    args = _parse_args(argv)
    start_date = datetime.strptime(args.start, "%Y-%m-%d").date()
    end_date = datetime.strptime(args.end, "%Y-%m-%d").date()

    symbols = None
    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    config = EodJobConfig.from_env()
    runner = EodJobRunner(config=config)
    result = runner.run(start_date=start_date, end_date=end_date, symbols=symbols)

    print(
        f"[EodJob] done. run_id={result.run_id}, "
        f"bronze={result.bronze_result.row_count}, "
        f"silver={result.silver_result.row_count}, "
        f"gold={result.gold_result.row_count}, "
        f"range=[{result.start_date}, {result.end_date}]"
    )


if __name__ == "__main__":
    main()
