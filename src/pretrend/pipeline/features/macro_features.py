from __future__ import annotations

import argparse
import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

from dateutil.relativedelta import relativedelta
import numpy as np
import pandas as pd
import shutil


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

    feature_start_date / feature_end_date:
        최종 Silver 출력 구간
    load_start_date:
        lookback(12개월)을 포함한 로드 구간 시작
    """
    feature_start_date: dt.date
    feature_end_date: dt.date
    run_id: str
    ingestion_ts: pd.Timestamp
    cfg: MacroFeatureConfig
    lookback_months: int = 12  # yoy/rolling_12m 기준

    @property
    def load_start_date(self) -> dt.date:
        return self.feature_start_date - relativedelta(months=self.lookback_months)


# =========================
# 2. Bronze Reader
# =========================

def load_bronze_macro(ctx: MacroFeatureRunContext) -> pd.DataFrame:
    """
    Bronze macro econ_indicators에서 필요한 구간만 로드.
    - 로드 구간: [load_start_date, feature_end_date]
    """
    files = list(ctx.cfg.bronze_root.rglob("*.parquet"))
    if not files:
        print(f"[SilverMacro] No parquet under {ctx.cfg.bronze_root}. Return empty.")
        return pd.DataFrame()

    df = pd.concat((pd.read_parquet(f) for f in files), ignore_index=True)
    df["date"] = pd.to_datetime(df["date"]).dt.date

    mask = (df["date"] >= ctx.load_start_date) & (df["date"] <= ctx.feature_end_date)
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
    if df.empty:
        return df

    df = df.sort_values(["indicator_id", "date"]).copy()

    def _per_indicator(g: pd.DataFrame) -> pd.DataFrame:
        g = g.sort_values("date")
        g["value_lag_1"] = g["value"].shift(1)
        g["value_lag_12"] = g["value"].shift(12)

        g["mom"] = np.where(
            g["value_lag_1"].notna() & (g["value_lag_1"] != 0),
            g["value"] / g["value_lag_1"] - 1.0,
            np.nan,
        )

        g["yoy"] = np.where(
            g["value_lag_12"].notna() & (g["value_lag_12"] != 0),
            g["value"] / g["value_lag_12"] - 1.0,
            np.nan,
        )

        g["rolling_3m"] = g["value"].rolling(window=3, min_periods=3).mean()
        g["rolling_12m"] = g["value"].rolling(window=12, min_periods=12).mean()
        return g

    df = (
        df.groupby("indicator_id", group_keys=False, sort=False)
          .apply(_per_indicator)
          .reset_index(drop=True)  # ✅ index 꼬임 방지
    )
    return df


# =========================
# 4. Indicator-specific Feature & Regime
# =========================

def apply_inflation_regime(df: pd.DataFrame) -> pd.DataFrame:
    """
    CPI / Core CPI 인플레이션 레짐 태깅 + level 설정.

    설계:
      - value: CPI index (1982-84=100)
      - level: yoy (인플레이션율, 전략용)
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

    # level = yoy (인플레이션 수준)
    sub["level"] = sub["yoy"]

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

    df.loc[mask, ["level", "regime"]] = sub[["level", "regime"]].to_numpy()
    return df


def apply_unrate_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    실업률 특화 Feature + 레짐.

    설계:
      - value: 실업률(%)
      - level: 실업률 수준 = value
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

    sub = df.loc[mask].copy().sort_values("date")

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
    ].to_numpy()
    return df


def apply_fedfunds_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Fed Funds Rate 특화 Feature + 레짐.

    설계:
      - value: FRED 기준금리(%)
      - level: 기준금리 수준 = value
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

    sub = df.loc[mask].copy().sort_values("date")

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
    ].to_numpy()
    return df


def apply_dgs10_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    10Y 국채금리 특화 Feature.

    설계:
      - value: 10Y 금리(%)
      - level: 10Y 금리 수준 = value
      - spread_to_fedfunds = level - fedfunds (as-of join: 해당 날짜 또는 직전 날짜 기준)
      - is_yield_curve_inverted = spread_to_fedfunds < 0
      - regime:
          spread <= -0.5%          -> inverted
          -0.5% < spread < 0.5%    -> flat
          spread >= 0.5%           -> normal
    """
    dgs_mask = df["indicator_id"] == INDICATOR_DGS10
    if not dgs_mask.any():
        return df

    fed_mask = df["indicator_id"] == INDICATOR_FEDFUNDS
    if not fed_mask.any():
        # FedFunds 없으면 level만 세팅하고 종료
        df.loc[dgs_mask, "level"] = df.loc[dgs_mask, "value"].to_numpy()
        return df

    # 날짜 정규화
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])

    # 1) FedFunds 시계열: date -> fedfunds, as-of 매핑용
    fed = df.loc[fed_mask, ["date", "value"]].sort_values("date").copy()
    fed_series = fed.set_index("date")["value"]

    # 2) DGS10 row의 날짜 추출 (df 순서 유지)
    dgs_dates = df.loc[dgs_mask, "date"]
    # 각 날짜에 대해, 그 날짜 또는 직전 날짜의 FedFunds 값을 as-of 매핑
    fed_on_dgs = fed_series.reindex(dgs_dates, method="ffill").to_numpy()

    # 3) DGS10 level / spread / regime 계산
    dgs_value = df.loc[dgs_mask, "value"].to_numpy()

    level = dgs_value  # 10Y 수준 = raw 값
    spread = level - fed_on_dgs

    conditions = [
        spread <= -0.5,
        (spread > -0.5) & (spread < 0.5),
        spread >= 0.5,
    ]
    choices = [
        "inverted",
        "flat",
        "normal",
    ]
    regime = np.select(conditions, choices, default=None)
    inverted = spread < 0

    # 4) df에 반영 (index alignment 방지 위해 numpy로 대입)
    df.loc[dgs_mask, "level"] = level
    df.loc[dgs_mask, "spread_to_fedfunds"] = spread
    df.loc[dgs_mask, "regime"] = regime
    df.loc[dgs_mask, "is_yield_curve_inverted"] = inverted

    return df


def build_macro_features(df: pd.DataFrame, ctx: MacroFeatureRunContext) -> pd.DataFrame:
    """
    Bronze macro econ_indicators → Silver macro_features 전체 변환.
    """
    if df.empty:
        return df

    # 공통 시계열 Feature
    df = add_common_features(df)

    # Indicator-specific Feature & Regime
    df = apply_inflation_regime(df)
    df = apply_unrate_features(df)
    df = apply_fedfunds_features(df)
    df = apply_dgs10_features(df)

    df["ingestion_ts"] = ctx.ingestion_ts

    # 최종 출력 구간으로 필터
    df = df[
        (pd.to_datetime(df["date"]).dt.date >= ctx.feature_start_date)
        & (pd.to_datetime(df["date"]).dt.date <= ctx.feature_end_date)
    ]

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
    for c in keep_cols:
        if c not in df.columns:
            df[c] = np.nan

    # level이 NaN인 row는 기본적으로 raw value를 level로 사용
    # (CPI/Core는 apply_inflation_regime에서 level=yoy로 이미 설정)
    mask_level_na = df["level"].isna()
    if mask_level_na.any():
        df.loc[mask_level_na, "level"] = df.loc[mask_level_na, "value"]

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
    - 전략: 파티션 단위 overwrite (멱등성, tmp 디렉토리 사용)
    """
    if df.empty:
        print("[SilverMacro] Nothing to write.")
        return

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])

    tmp_root = ctx.cfg.silver_root / f"_tmp_run={ctx.run_id}"

    for year, month in _partition_keys(df):
        part = df[(df["date"].dt.year == year) & (df["date"].dt.month == month)]
        if part.empty:
            continue

        tmp_dir = tmp_root / f"year={year:04d}" / f"month={month:02d}"
        final_dir = ctx.cfg.silver_root / f"year={year:04d}" / f"month={month:02d}"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        final_dir.mkdir(parents=True, exist_ok=True)

        tmp_file = tmp_dir / f"macro_features_{year:04d}{month:02d}.parquet"
        final_file = final_dir / f"macro_features_{year:04d}{month:02d}.parquet"

        part.to_parquet(tmp_file, index=False)

        # 파티션 단위 overwrite
        if final_file.exists():
            final_file.unlink()
        tmp_file.replace(final_file)

        print(f"[SilverMacro] Saved: {final_file}")

    # tmp 디렉토리 정리
    if tmp_root.exists():
        shutil.rmtree(tmp_root)
        print(f"[SilverMacro] Cleaned tmp directory: {tmp_root}")


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
    feature_start = dt.datetime.strptime(args.start, "%Y-%m-%d").date()
    feature_end = dt.datetime.strptime(args.end, "%Y-%m-%d").date()
    run_id = args.run_id or dt.datetime.utcnow().strftime("macrofeat_%Y%m%d%H%M%S")

    cfg = MacroFeatureConfig.from_defaults()
    ctx = MacroFeatureRunContext(
        feature_start_date=feature_start,
        feature_end_date=feature_end,
        run_id=run_id,
        ingestion_ts=pd.Timestamp.utcnow(),
        cfg=cfg,
        lookback_months=12,
    )

    df_bronze = load_bronze_macro(ctx)
    if df_bronze.empty:
        print("[SilverMacro] No input data. Exit.")
        return

    df_silver = build_macro_features(df_bronze, ctx)
    write_silver_macro_features(df_silver, ctx)


if __name__ == "__main__":
    main()
