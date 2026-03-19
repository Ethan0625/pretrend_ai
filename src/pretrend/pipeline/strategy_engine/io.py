"""
Strategy Engine I/O — Gold loaders + snapshot writer.

SOT: docs/strategy_engine_design.md §C, §E
"""
from __future__ import annotations

import logging
from errno import EXDEV
import shutil
from datetime import date
from pathlib import Path
from typing import List, Optional

import pandas as pd

logger = logging.getLogger(__name__)


# ── Gold Loaders ──────────────────────────────────────────


def load_gold_macro(
    gold_macro_root: Path,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> pd.DataFrame:
    """Gold Macro parquet를 로드한다.

    Returns DataFrame with GOLD_MACRO_FEATURE_COLUMNS.
    파일 없으면 빈 DataFrame 반환.
    """
    files = list(gold_macro_root.rglob("*.parquet"))
    if not files:
        logger.warning("[StrategyIO] No Gold Macro parquet under %s", gold_macro_root)
        return pd.DataFrame()

    df = pd.concat((pd.read_parquet(f) for f in files), ignore_index=True)

    if "trade_date" in df.columns:
        df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date

    if start_date is not None:
        df = df[df["trade_date"] >= start_date]
    if end_date is not None:
        df = df[df["trade_date"] <= end_date]

    return df


def load_gold_eod(
    gold_eod_root: Path,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    symbols: Optional[List[str]] = None,
) -> pd.DataFrame:
    """Gold EOD parquet를 로드한다.

    Returns DataFrame with GOLD_EOD_FEATURE_COLUMNS.
    파일 없으면 빈 DataFrame 반환.
    """
    files = list(gold_eod_root.rglob("*.parquet"))
    if not files:
        logger.warning("[StrategyIO] No Gold EOD parquet under %s", gold_eod_root)
        return pd.DataFrame()

    df = pd.concat((pd.read_parquet(f) for f in files), ignore_index=True)

    if "trade_date" in df.columns:
        df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date

    if start_date is not None:
        df = df[df["trade_date"] >= start_date]
    if end_date is not None:
        df = df[df["trade_date"] <= end_date]
    if symbols:
        df = df[df["symbol"].isin(symbols)]

    return df


def load_gold_text(
    data_root: Path,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> pd.DataFrame:
    """Gold Text parquet(rule-based + LLM)를 로드한다.

    Returns
    -------
    DataFrame
        long-format DataFrame with a normalized superset schema.
        파일이 없으면 빈 DataFrame 반환.
    """
    roots = [
        data_root / "gold" / "text" / "text_daily_features",
        data_root / "gold" / "text" / "text_llm_features",
    ]
    files: List[Path] = []
    for root in roots:
        files.extend(list(root.rglob("*.parquet")))

    if not files:
        logger.warning("[StrategyIO] No Gold Text parquet under %s/gold/text", data_root)
        return pd.DataFrame()

    df = pd.concat((pd.read_parquet(f) for f in sorted(files)), ignore_index=True)

    if "trade_date" in df.columns:
        df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce").dt.date

    for col in [
        "doc_id",
        "source",
        "feature_name",
        "feature_str",
        "confidence",
        "feature_value",
        "coverage_ratio",
        "prompt_version",
    ]:
        if col not in df.columns:
            df[col] = None

    if start_date is not None and "trade_date" in df.columns:
        df = df[df["trade_date"] >= start_date]
    if end_date is not None and "trade_date" in df.columns:
        df = df[df["trade_date"] <= end_date]

    return df.reset_index(drop=True)


# ── Snapshot Writer ───────────────────────────────────────


def write_snapshot_atomic(
    df: pd.DataFrame,
    output_root: Path,
    stage_name: str,
    decision_date: date,
    run_id: str,
) -> Path:
    """Strategy Engine 스냅샷을 atomic rename으로 저장한다.

    경로: output_root/{stage_name}/decision_date=YYYY-MM-DD/{stage_name}_YYYYMMDD.parquet

    SOT: docs/strategy_engine_design.md §E
    - _tmp_run={run_id} 경유
    - 동일 파티션 overwrite
    - idempotent (재실행 동일 결과)
    """
    dd_str = decision_date.strftime("%Y-%m-%d")
    dd_compact = decision_date.strftime("%Y%m%d")

    final_dir = output_root / stage_name / f"decision_date={dd_str}"
    final_file = final_dir / f"{stage_name}_{dd_compact}.parquet"

    tmp_dir = output_root / stage_name / f"_tmp_run={run_id}"
    tmp_file = tmp_dir / f"{stage_name}_{dd_compact}.parquet"

    tmp_dir.mkdir(parents=True, exist_ok=True)
    final_dir.mkdir(parents=True, exist_ok=True)

    df.to_parquet(tmp_file, index=False)

    if final_file.exists():
        final_file.unlink()
    try:
        tmp_file.replace(final_file)
    except OSError as exc:
        # 환경에 따라 atomic rename이 cross-device(EXDEV)로 실패할 수 있다.
        # 이 경우 move로 fallback 하여 snapshot 저장 자체는 보장한다.
        if exc.errno != EXDEV:
            raise
        shutil.move(str(tmp_file), str(final_file))

    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)

    logger.info("[StrategyIO] Saved snapshot: %s", final_file)
    return final_file
