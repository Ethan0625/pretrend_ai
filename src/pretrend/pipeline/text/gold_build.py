"""Text Gold Build — 룰 기반 텍스트 feature 생성 (long 포맷).

입력: data/silver/text/text_enriched/event_date=YYYY-MM-DD/*.parquet
출력: data/gold/text/text_daily_features/year=YYYY/month=MM/gold_{YYYYMM}.parquet

Gold 스키마 (long 포맷):
    trade_date, feature_name, feature_value, feature_version,
    coverage_ratio, staleness_days

초기 rule-based feature 3개:
    1. macro_hawkish_score   — Fed/FOMC 문서 내 hawkish 키워드 비율
    2. filing_risk_burst     — 8-K 공시 수 rolling z-score (20일)
    3. policy_uncertainty_idx — macro_hawkish + filing_risk 가중합

Fail-open: Silver 데이터 없는 날짜 → feature_value=NaN, coverage_ratio=0.0
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd

from pretrend.pipeline.text.config import TextPipelineConfig

logger = logging.getLogger(__name__)

_FEATURE_VERSION = "v0"

# Gold 스키마 컬럼 순서
_GOLD_COLUMNS = [
    "trade_date",
    "feature_name",
    "feature_value",
    "feature_version",
    "coverage_ratio",
    "staleness_days",
]

# hawkish 키워드 (macro_hawkish_score 계산용)
_HAWKISH_KEYWORDS = (
    "hike", "tighten", "hawkish", "restrictive", "rate increase",
    "rate hike", "above target", "elevated inflation", "overheating",
    "higher for longer", "reduce balance sheet", "quantitative tightening",
)

# 8-K rolling z-score 윈도우
_FILING_RISK_WINDOW = 20


# ------------------------------------------------------------------
# Silver 로딩
# ------------------------------------------------------------------

def _load_silver(
    silver_root: Path,
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    """Silver text_enriched 파티션 로드 (날짜 범위 기준)."""
    frames: List[pd.DataFrame] = []
    enriched_root = silver_root / "text_enriched"
    if not enriched_root.exists():
        return pd.DataFrame()

    for partition_dir in enriched_root.iterdir():
        if not partition_dir.name.startswith("event_date="):
            continue
        date_str = partition_dir.name.split("=", 1)[1]
        try:
            part_date = date.fromisoformat(date_str)
        except ValueError:
            continue
        if not (start_date <= part_date <= end_date):
            continue
        for pq in partition_dir.glob("*.parquet"):
            frames.append(pd.read_parquet(pq))

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


# ------------------------------------------------------------------
# Feature 계산 함수
# ------------------------------------------------------------------

def _hawkish_ratio(text: str) -> float:
    """텍스트 내 hawkish 키워드 hit 비율 (0.0 ~ 1.0)."""
    if not text:
        return 0.0
    text_lower = text.lower()
    hits = sum(1 for kw in _HAWKISH_KEYWORDS if kw in text_lower)
    return min(hits / len(_HAWKISH_KEYWORDS), 1.0)


def _compute_macro_hawkish_score(df: pd.DataFrame, trade_date: date) -> pd.Series:
    """trade_date 기준 Fed/FOMC 문서 hawkish 점수 (일별 평균).

    Returns Series with index=trade_date values, single-row.
    """
    fed_docs = df[df["source"] == "fed_fomc"].copy()
    if fed_docs.empty:
        return None  # 데이터 없음 → fail-open

    fed_docs["hawkish_ratio"] = fed_docs["clean_text"].apply(_hawkish_ratio)
    score = fed_docs["hawkish_ratio"].mean()
    n_docs = len(fed_docs)
    total_docs = max(len(df), 1)
    coverage = n_docs / total_docs
    return score, coverage, n_docs


def _compute_filing_risk_burst(
    daily_counts: pd.Series,
    trade_date: date,
    window: int = _FILING_RISK_WINDOW,
) -> tuple:
    """8-K 공시 수 rolling z-score.

    daily_counts: index=date str, value=count
    Returns (z_score, coverage_ratio)
    """
    if len(daily_counts) < 2:
        return np.nan, 0.0

    counts = daily_counts.sort_index()
    recent = counts.iloc[-window:]
    if len(recent) < 2:
        return np.nan, 0.0

    mu = recent.mean()
    sigma = recent.std(ddof=1)
    if sigma == 0 or np.isnan(sigma):
        return 0.0, 1.0

    today_count = counts.get(trade_date.isoformat(), 0)
    z = (today_count - mu) / sigma
    coverage = min(len(recent) / window, 1.0)
    return float(z), float(coverage)


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

@dataclass
class TextGoldResult:
    feature_rows: int
    trade_dates: List[str]
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.error is None


def run_text_gold_build(
    start_date: date,
    end_date: date,
    cfg: Optional[TextPipelineConfig] = None,
) -> TextGoldResult:
    """Silver → Gold long-format feature 생성.

    Args:
        start_date: 집계 시작일
        end_date: 집계 종료일
        cfg: TextPipelineConfig

    Returns:
        TextGoldResult
    """
    if cfg is None:
        cfg = TextPipelineConfig.default()

    # Silver 로드 (lookback 포함: 20일 이전부터)
    lookback_start = start_date - timedelta(days=_FILING_RISK_WINDOW + 5)
    logger.info(
        "Gold build: range=[%s, %s], silver_load_from=%s",
        start_date, end_date, lookback_start,
    )

    silver_df = _load_silver(cfg.silver_root, lookback_start, end_date)

    # 8-K 일별 카운트 (filing_risk_burst 전체 lookback용)
    if not silver_df.empty:
        sec_8k = silver_df[
            (silver_df["source"] == "sec_edgar") & (silver_df["title"].str.contains("8-K", na=False))
        ].copy()
        sec_8k["event_date"] = sec_8k["event_date"].astype(str)
        daily_8k_counts = sec_8k.groupby("event_date").size()
    else:
        daily_8k_counts = pd.Series(dtype=float)

    # 날짜별 feature 계산
    rows: List[dict] = []
    current = start_date
    while current <= end_date:
        date_str = current.isoformat()

        # 당일 Silver 슬라이스
        if not silver_df.empty and "event_date" in silver_df.columns:
            day_df = silver_df[silver_df["event_date"] == date_str]
        else:
            day_df = pd.DataFrame()

        n_total = len(day_df)

        # --- macro_hawkish_score ---
        if not day_df.empty:
            result = _compute_macro_hawkish_score(day_df, current)
        else:
            result = None

        if result is not None:
            score, coverage, _ = result
            rows.append({
                "trade_date": date_str,
                "feature_name": "macro_hawkish_score",
                "feature_value": score,
                "feature_version": _FEATURE_VERSION,
                "coverage_ratio": coverage,
                "staleness_days": 0,
            })
        else:
            rows.append({
                "trade_date": date_str,
                "feature_name": "macro_hawkish_score",
                "feature_value": np.nan,
                "feature_version": _FEATURE_VERSION,
                "coverage_ratio": 0.0,
                "staleness_days": 0,
            })

        # --- filing_risk_burst ---
        # lookback window: 날짜 기준 최근 window일
        lookback_dates = pd.Series(
            {k: v for k, v in daily_8k_counts.items()
             if k <= date_str},
        )
        if len(lookback_dates) >= 2:
            z, cov = _compute_filing_risk_burst(lookback_dates, current)
        else:
            z, cov = np.nan, 0.0

        rows.append({
            "trade_date": date_str,
            "feature_name": "filing_risk_burst",
            "feature_value": z,
            "feature_version": _FEATURE_VERSION,
            "coverage_ratio": cov,
            "staleness_days": 0,
        })

        # --- policy_uncertainty_idx (hawkish + filing_risk 가중합) ---
        hawkish_val = rows[-2]["feature_value"]  # macro_hawkish_score
        filing_val = rows[-1]["feature_value"]   # filing_risk_burst
        hawkish_cov = rows[-2]["coverage_ratio"]
        filing_cov = rows[-1]["coverage_ratio"]

        if not (np.isnan(hawkish_val) and np.isnan(filing_val)):
            h = 0.0 if np.isnan(hawkish_val) else float(hawkish_val)
            f = 0.0 if np.isnan(filing_val) else float(filing_val)
            # filing_risk z-score 정규화: tanh로 [-1,1] 클리핑
            f_norm = float(np.tanh(f / 3.0))
            pui = 0.5 * h + 0.5 * f_norm
            pui_cov = (hawkish_cov + filing_cov) / 2.0
        else:
            pui = np.nan
            pui_cov = 0.0

        rows.append({
            "trade_date": date_str,
            "feature_name": "policy_uncertainty_idx",
            "feature_value": pui,
            "feature_version": _FEATURE_VERSION,
            "coverage_ratio": pui_cov,
            "staleness_days": 0,
        })

        current += timedelta(days=1)

    gold_df = pd.DataFrame(rows)[_GOLD_COLUMNS]
    trade_dates = sorted(gold_df["trade_date"].unique().tolist())

    # Gold 파티션 저장 (year/month 파티셔닝)
    try:
        _write_gold_partitions(gold_df, cfg.gold_root)
    except Exception as exc:
        logger.error("Gold write failed: %s", exc)
        return TextGoldResult(
            feature_rows=len(gold_df),
            trade_dates=trade_dates,
            error=str(exc),
        )

    logger.info(
        "Gold build complete: %d feature rows, %d dates",
        len(gold_df), len(trade_dates),
    )
    return TextGoldResult(feature_rows=len(gold_df), trade_dates=trade_dates)


def _write_gold_partitions(df: pd.DataFrame, gold_root: Path) -> None:
    """year/month Hive 파티셔닝으로 Gold 저장."""
    df = df.copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df["year"] = df["trade_date"].dt.year
    df["month"] = df["trade_date"].dt.month
    df["trade_date"] = df["trade_date"].dt.strftime("%Y-%m-%d")

    for (year, month), group in df.groupby(["year", "month"]):
        partition_dir = (
            gold_root / "text_daily_features"
            / f"year={year}"
            / f"month={month:02d}"
        )
        partition_dir.mkdir(parents=True, exist_ok=True)
        filename = f"gold_{year}{month:02d}.parquet"
        out_path = partition_dir / filename
        tmp_path = partition_dir / f".tmp_{uuid.uuid4().hex}_{filename}"

        out_df = group.drop(columns=["year", "month"]).reset_index(drop=True)
        out_df.to_parquet(tmp_path, index=False, compression="snappy")
        tmp_path.rename(out_path)
        logger.info("Gold written: %s (%d rows)", out_path, len(out_df))
