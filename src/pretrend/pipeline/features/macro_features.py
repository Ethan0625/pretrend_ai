from __future__ import annotations

import argparse
import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

import numpy as np
import pandas as pd


# =========================
# 0. Indicator Constants
# =========================

INDICATOR_CPI_HEADLINE = "CPI_US_ALL_ITEMS_SA"
INDICATOR_CPI_CORE = "CPI_US_CORE_SA"
INDICATOR_UNRATE = "US_UNEMPLOYMENT_RATE"
INDICATOR_FEDFUNDS = "US_FED_FUNDS_RATE"
INDICATOR_DGS10 = "US_TREASURY_10Y_YIELD"


# =========================
# 1. Config / Context
# =========================

@dataclass
class MacroFeatureConfig:
    """
    Silver Macro Feature 레이어 설정.
    """
    bronze_root: Path = Path("data/bronze/macro/econ_indicators")
    silver_root: Path = Path("data/silver/macro/macro_features")
    target_indicators: Optional[List[str]] = None

    @classmethod
    def from_defaults(cls) -> "MacroFeatureConfig":
        return cls(
            target_indicators=[
                INDICATOR_CPI_HEADLINE,
                INDICATOR_CPI_CORE,
                INDICATOR_UNRATE,
                INDICATOR_FEDFUNDS,
                INDICATOR_DGS10,
            ]
        )


@dataclass
class MacroFeatureRunContext:
    """
    Silver 변환 실행 컨텍스트.
    Bronze IngestContext와는 별도로 Silver 전용 context.
    """
    start_date: dt.date
    end_date: dt.date
    run_id: str
    ingestion_ts: pd.Timestamp
    cfg: MacroFeatureConfig


# =========================
# 2. Bronze Reader
# =========================

def load_bronze_macro(ctx: MacroFeatureRunContext) -> pd.DataFrame:
    """
    Bronze macro econ_indicators에서 필요한 구간만 로드.

    입력 스키마 (Bronze):
        indicator_id, date, value, unit, source, run_id, ingestion_ts
    """
    files = list(ctx.cfg.bronze_root.rglob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"No parquet under {ctx.cfg.bronze_root}")

    df = pd.concat((pd.read_parquet(f) for f in files), ignore_index=True)

    df["date"] = pd.to_datetime(df["date"]).dt.date

    mask = (df["date"] >= ctx.start_date) & (df["date"] <= ctx.end_date)
    if ctx.cfg.target_indicators:
        mask &= df["indicator_id"].isin(ctx.cfg.target_indicators)

    df = df.loc[mask].copy()
    if df.empty:
        print("[SilverMacro] No bronze data in given range.")
        return df

    df["value"] = df["value"].astype(float)
    return df


# =========================
# 3. Common Feature Builder
# =========================

def add_common_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    공통 Feature:
        - mom: value / value_1m_ago - 1
        - yoy: value / value_12m_ago - 1
        - rolling_3m: value 3개월 이동평균
        - rolling_12m: value 12개월 이동평균
    """
    if df.empty:
        return df

    df = df.sort_values(["indicator_id", "date"]).copy()

    def _per_indicator(g: pd.DataFrame) -> pd.DataFrame:
        g = g.sort_values("date")
        g["value_lag_1"] = g["value"].shift(1)
        g["value_lag_12"] = g["value"].shift(12)

        # MoM
        g["mom"] = np.where(
            g["value_lag_1"].notna() & (g["value_lag_1"] != 0),
            g["value"] / g["value_lag_1"] - 1.0,
            np.nan,
        )

        # YoY
        g["yoy"] = np.where(
            g["value_lag_12"].notna() & (g["value_lag_12"] != 0),
            g["value"] / g["value_lag_12"] - 1.0,
            np.nan,
        )

        # Rolling
        g["rolling_3m"] = g["value"].rolling(window=3, min_periods=3).mean()
        g["rolling_12m"] = g["value"].rolling(window=12, min_periods=12).mean()

        return g

    df = df.groupby("indicator_id", group_keys=False).apply(_per_indicator)
    return df


# =========================
# 4. Indicator-specific Feature & Regime
# =========================

def apply_inflation_regime(df: pd.DataFrame) -> pd.DataFrame:
    """
    CPI / Core CPI 인플레이션 레짐 태깅.

    규칙 (yoy 기준):
      yoy >= 4%         -> high_inflation
      2% <= yoy < 4%    -> elevated
      0 <= yoy < 2%     -> moderate
      yoy < 0           -> disinflation
    """
    mask = df["indicator_id"].isin([INDICATOR_CPI_HEADLINE, INDICATOR_CPI_CORE])
    if not mask.any():
        return df

    sub = df.loc[mask].copy()

    conditions = [
        sub["yoy"] >= 0.04,
        (sub["yoy"] >= 0.02) & (sub["yoy"] < 0.04),
        (sub["yoy"] >= 0.0) & (sub["yoy"] < 0.02),
        sub["yoy"] < 0.0,
    ]
    choices = [
        "high_inflation",
        "elevated",
        "moderate",
        "disinflation",
    ]
    sub["regime"] = np.select(conditions, choices, default=None)

    df.loc[mask, "regime"] = sub["regime"]
    return df


def apply_unrate_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    실업률 특화 Feature + 레짐.
      - level = value
      - delta_3m = level - level_3m_ago
      - regime:
          level <= 4% & delta_3m <= 0      -> tight
          level <= 4% & delta_3m > 0       -> loosening
          level > 4% & delta_3m <= 0       -> elevated_but_improving
          level > 4% & delta_3m > 0        -> weakening
    """
    mask = df["indicator_id"] == INDICATOR_UNRATE
    if not mask.any():
        return df

    sub = df.loc[mask].copy()
    sub = sub.sort_values("date")

    sub["level"] = sub["value"]
    sub["level_lag_3"] = sub["level"].shift(3)
    sub["delta_3m"] = sub["level"] - sub["level_lag_3"]

    conditions = [
        (sub["level"] <= 4.0) & (sub["delta_3m"] <= 0),
        (sub["level"] <= 4.0) & (sub["delta_3m"] > 0),
        (sub["level"] > 4.0) & (sub["delta_3m"] <= 0),
        (sub["level"] > 4.0) & (sub["delta_3m"] > 0),
    ]
    choices = [
        "tight",
        "loosening",
        "elevated_but_improving",
        "weakening",
    ]
    sub["regime"] = np.select(conditions, choices, default=None)

    df.loc[mask, ["level", "delta_3m", "regime"]] = sub[
        ["level", "delta_3m", "regime"]
    ]
    return df


def apply_fedfunds_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Fed Funds Rate 특화 Feature + 레짐.
      - level = value
      - delta_3m = level - level_3m_ago
      - delta_12m = level - level_12m_ago
      - regime:
          delta_3m >= 0.5   -> hiking
          delta_3m <= -0.5  -> cutting
          기타               -> paused
    """
    mask = df["indicator_id"] == INDICATOR_FEDFUNDS
    if not mask.any():
        return df

    sub = df.loc[mask].copy()
    sub = sub.sort_values("date")

    sub["level"] = sub["value"]
    sub["level_lag_3"] = sub["level"].shift(3)
    sub["level_lag_12"] = sub["level"].shift(12)
    sub["delta_3m"] = sub["level"] - sub["level_lag_3"]
    sub["delta_12m"] = sub["level"] - sub["level_lag_12"]

    conditions = [
        sub["delta_3m"] >= 0.5,
        sub["delta_3m"] <= -0.5,
    ]
    choices = [
        "hiking",
        "cutting",
    ]
    sub["regime"] = np.select(conditions, choices, default="paused")

    df.loc[mask, ["level", "delta_3m", "delta_12m", "regime"]] = sub[
        ["level", "delta_3m", "delta_12m", "regime"]
    ]
    return df


def apply_dgs10_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    10Y 국채금리 특화 Feature.
      - level = value
      - spread_to_fedfunds = level - fedfunds_level
      - is_yield_curve_inverted = spread_to_fedfunds < 0
      - regime:
          spread <= -0.5%  -> inverted
          -0.5% < spread < 0.5% -> flat
          spread >= 0.5%   -> normal
    """
    mask = df["indicator_id"] == INDICATOR_DGS10
    if not mask.any():
        return df

    sub = df.loc[mask].copy()
    sub = sub.sort_values("date")
    sub["level"] = sub["value"]

    # FEDFUNDS join
    fed = df.loc[df["indicator_id"] == INDICATOR_FEDFUNDS, ["date", "value"]].copy()
    if fed.empty:
        # FEDFUNDS 없으면 스프레드/레짐 계산 불가
        df.loc[mask, "level"] = sub["level"]
        return df

    fed = fed.rename(columns={"value": "fedfunds"})
    merged = sub.merge(fed, on="date", how="left")

    merged["spread_to_fedfunds"] = merged["level"] - merged["fedfunds"]

    conditions = [
        merged["spread_to_fedfunds"] <= -0.005,
        (merged["spread_to_fedfunds"] > -0.005)
        & (merged["spread_to_fedfunds"] < 0.005),
        merged["spread_to_fedfunds"] >= 0.005,
    ]
    choices = [
        "inverted",
        "flat",
        "normal",
    ]
    merged["regime"] = np.select(conditions, choices, default=None)
    merged["is_yield_curve_inverted"] = merged["spread_to_fedfunds"] < 0

    df.loc[mask, ["level", "spread_to_fedfunds", "regime", "is_yield_curve_inverted"]] = merged[
        ["level", "spread_to_fedfunds", "regime", "is_yield_curve_inverted"]
    ]
    return df


def build_macro_features(df: pd.DataFrame, ctx: MacroFeatureRunContext) -> pd.DataFrame:
    """
    Bronze macro econ_indicators → Silver macro_features 전체 변환.
    """
    if df.empty:
        return df

    # 공통 Feature
    df = add_common_features(df)

    # indicator-specific Feature & regime
    df = apply_inflation_regime(df)
    df = apply_unrate_features(df)
    df = apply_fedfunds_features(df)
    df = apply_dgs10_features(df)

    df["ingestion_ts"] = ctx.ingestion_ts

    # Silver 최종 스키마 정리
    keep_cols = [
        "indicator_id",
        "date",
        "value",
        "yoy",
        "mom",
        "rolling_3m",
        "rolling_12m",
        "regime",
        "level",
        "delta_3m",
        "delta_12m",
        "spread_to_fedfunds",
        "is_yield_curve_inverted",
        "ingestion_ts",
    ]
    # 없는 컬럼은 자동으로 생성 (NaN)
    for c in keep_cols:
        if c not in df.columns:
            df[c] = np.nan

    df = df[keep_cols].copy()
    return df


# =========================
# 5. Silver Writer (멱등성)
# =========================

def _partition_keys(df: pd.DataFrame) -> Iterable[tuple[int, int]]:
    dates = pd.to_datetime(df["date"])
    return sorted(set(zip(dates.dt.year, dates.dt.month)))


def write_silver_macro_features(df: pd.DataFrame, ctx: MacroFeatureRunContext) -> None:
    """
    Silver Layer 저장.
    - 파티션: year=YYYY/month=MM
    - 파일: macro_features_YYYYMM.parquet
    - 전략: 파티션 단위 overwrite (멱등성)
    """
    if df.empty:
        print("[SilverMacro] Nothing to write.")
        return

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])

    for year, month in _partition_keys(df):
        part = df[(df["date"].dt.year == year) & (df["date"].dt.month == month)]
        if part.empty:
            continue

        tmp_dir = (
            ctx.cfg.silver_root
            / f"_tmp_run={ctx.run_id}"
            / f"year={year:04d}"
            / f"month={month:02d}"
        )
        final_dir = ctx.cfg.silver_root / f"year={year:04d}" / f"month={month:02d}"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        final_dir.mkdir(parents=True, exist_ok=True)

        tmp_file = tmp_dir / f"macro_features_{year:04d}{month:02d}.parquet"
        final_file = final_dir / f"macro_features_{year:04d}{month:02d}.parquet"

        part.to_parquet(tmp_file, index=False)

        # 간단한 멱등성 전략: 파티션 파일 단위 overwrite
        if final_file.exists():
            final_file.unlink()
        tmp_file.replace(final_file)

        print(f"[SilverMacro] Saved: {final_file}")

    # TODO: _tmp_run 디렉토리 정리 로직 추가 가능


# =========================
# 6. CLI Entrypoint
# =========================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Silver Macro Features")
    parser.add_argument("--start", type=str, required=True, help="YYYY-MM-DD")
    parser.add_argument("--end", type=str, required=True, help="YYYY-MM-DD")
    parser.add_argument("--run-id", type=str, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    start_date = dt.datetime.strptime(args.start, "%Y-%m-%d").date()
    end_date = dt.datetime.strptime(args.end, "%Y-%m-%d").date()
    run_id = args.run_id or dt.datetime.utcnow().strftime("macrofeat_%Y%m%d%H%M%S")

    cfg = MacroFeatureConfig.from_defaults()
    ctx = MacroFeatureRunContext(
        start_date=start_date,
        end_date=end_date,
        run_id=run_id,
        ingestion_ts=pd.Timestamp.utcnow(),
        cfg=cfg,
    )

    df_bronze = load_bronze_macro(ctx)
    if df_bronze.empty:
        print("[SilverMacro] No input data. Exit.")
        return

    df_silver = build_macro_features(df_bronze, ctx)
    write_silver_macro_features(df_silver, ctx)


if __name__ == "__main__":
    main()
