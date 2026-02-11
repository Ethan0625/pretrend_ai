from __future__ import annotations

import argparse
import datetime as dt
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd


# =========================
# 1. Config / Context
# =========================

@dataclass
class EodFeatureConfig:
    """
    Silver EOD Feature 레이어 설정.

    data_root:
        PRETREND_DATA_ROOT 환경변수 (없으면 ./data) 기준 루트.
    bronze_root:
        EOD Bronze(daily_prices) 루트 디렉토리.
    silver_root:
        EOD Silver(eod_features) 루트 디렉토리.
    """
    data_root: Path = Path(os.getenv("PRETREND_DATA_ROOT", "data"))
    bronze_root: Path = Path("data/bronze/eod/daily_prices")
    silver_root: Path = Path("data/silver/eod/eod_features")
    target_symbols: Optional[List[str]] = None
    min_history_days: int = 130  # MA120, vol_60d 등을 위해 충분한 lookback

    def __post_init__(self) -> None:
        # data_root 기준으로 실제 경로 구성
        self.bronze_root = self.data_root / "bronze" / "eod" / "daily_prices"
        self.silver_root = self.data_root / "silver" / "eod" / "eod_features"

    @classmethod
    def from_env(cls) -> "EodFeatureConfig":
        """
        PRETREND_DATA_ROOT를 반영한 기본 설정.
        """
        return cls()


@dataclass
class EodFeatureRunContext:
    """
    Silver EOD Feature 변환 실행 컨텍스트.

    feature_start_date / feature_end_date:
        최종 Silver 출력 구간 (예: 2010-01-01 ~ 2025-12-01)
    load_start_date:
        롤링 윈도우/MA 계산을 고려한 과거 로드 구간 시작일
    """
    feature_start_date: dt.date
    feature_end_date: dt.date
    run_id: str
    ingestion_ts: pd.Timestamp
    cfg: EodFeatureConfig

    @property
    def load_start_date(self) -> dt.date:
        return self.feature_start_date - dt.timedelta(days=self.cfg.min_history_days)


# =========================
# 2. Bronze Reader
# =========================

def load_bronze_eod(ctx: EodFeatureRunContext) -> pd.DataFrame:
    """
    Bronze EOD에서 필요한 구간만 로드.

    Bronze 경로 예시:
      {data_root}/bronze/eod/daily_prices/
        source=YF/theme=GENERIC/symbol=SPY/trade_date=2024-01-02/eod.parquet

    기대 스키마:
      symbol, theme, source, trade_date,
      open, high, low, close, adj_close, volume,
      currency, run_id, ingestion_ts
    """
    files = list(ctx.cfg.bronze_root.rglob("eod.parquet"))
    if not files:
        raise FileNotFoundError(f"[SilverEOD] No eod.parquet under {ctx.cfg.bronze_root}")

    df = pd.concat((pd.read_parquet(f) for f in files), ignore_index=True)

    if "trade_date" not in df.columns:
        raise KeyError("[SilverEOD] Bronze EOD must have 'trade_date' column.")

    # 날짜 필터링 (lookback 포함)
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date

    mask = (df["trade_date"] >= ctx.load_start_date) & (
        df["trade_date"] <= ctx.feature_end_date
    )

    if ctx.cfg.target_symbols:
        mask &= df["symbol"].isin(ctx.cfg.target_symbols)

    df = df.loc[mask].copy()
    if df.empty:
        print("[SilverEOD] No bronze EOD data in given range.")
        return df

    # 타입 정리 (float로 통일)
    float_cols = ["open", "high", "low", "close", "adj_close", "volume"]
    for c in float_cols:
        if c in df.columns:
            df[c] = df[c].astype(float)

    return df


# =========================
# 3. Per-symbol Feature Builders
# =========================

def _add_returns(g: pd.DataFrame) -> pd.DataFrame:
    """
    일간/멀티데이 수익률 Feature.
    """
    g = g.sort_values("trade_date")
    g["prev_adj_close"] = g["adj_close"].shift(1)

    g["ret_1d"] = g["adj_close"] / g["prev_adj_close"] - 1.0
    g["log_ret_1d"] = np.log(g["adj_close"] / g["prev_adj_close"])

    g["ret_5d"] = g["adj_close"] / g["adj_close"].shift(5) - 1.0
    g["ret_20d"] = g["adj_close"] / g["adj_close"].shift(20) - 1.0
    return g


def _add_vol_ma(g: pd.DataFrame) -> pd.DataFrame:
    """
    이동 변동성 + 이동 평균 Feature.
    """
    g = g.sort_values("trade_date")

    # 변동성 (log 수익률 기준)
    g["vol_20d"] = g["log_ret_1d"].rolling(20, min_periods=5).std()
    g["vol_60d"] = g["log_ret_1d"].rolling(60, min_periods=10).std()

    # 이동 평균
    for window in [5, 20, 60, 120]:
        g[f"ma_{window}"] = g["adj_close"].rolling(
            window, min_periods=window // 2
        ).mean()

    g["ma_ratio_5_20"] = g["ma_5"] / g["ma_20"] - 1.0
    return g


def _add_atr(g: pd.DataFrame, window: int = 14) -> pd.DataFrame:
    """
    ATR(평균 실제 변동폭) Feature.
    """
    g = g.sort_values("trade_date")
    prev_close = g["close"].shift(1)

    tr = pd.concat(
        [
            g["high"] - g["low"],
            (g["high"] - prev_close).abs(),
            (g["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    g["atr_14"] = tr.rolling(window, min_periods=window // 2).mean()
    return g


def _add_rsi(g: pd.DataFrame, window: int = 14) -> pd.DataFrame:
    """
    RSI(14) Feature (SMA 기반).
    """
    g = g.sort_values("trade_date")

    change = g["adj_close"].diff()
    g["gain_1d"] = change.clip(lower=0.0)
    g["loss_1d"] = (-change).clip(lower=0.0)

    g["avg_gain_14"] = g["gain_1d"].rolling(window, min_periods=window).mean()
    g["avg_loss_14"] = g["loss_1d"].rolling(window, min_periods=window).mean()

    rs = g["avg_gain_14"] / g["avg_loss_14"]
    g["rsi_14"] = 100.0 - (100.0 / (1.0 + rs))

    # avg_loss_14 == 0 인 경우 RSI = 100 처리
    zero_loss_mask = g["avg_loss_14"] == 0.0
    g.loc[zero_loss_mask, "rsi_14"] = 100.0

    return g


def _add_micro_features(g: pd.DataFrame) -> pd.DataFrame:
    """
    Intraday/Volume 기반 추가 Feature.
    """
    g = g.sort_values("trade_date")
    prev_close = g["close"].shift(1)

    g["intraday_range"] = (g["high"] - g["low"]) / prev_close
    g["gap_open"] = (g["open"] - prev_close) / prev_close

    vol_mean = g["volume"].rolling(20, min_periods=5).mean()
    vol_std = g["volume"].rolling(20, min_periods=5).std()
    g["volume_zscore_20d"] = (g["volume"] - vol_mean) / vol_std

    return g


def _add_quality_flags(g: pd.DataFrame) -> pd.DataFrame:
    """
    데이터 품질 및 이상치 플래그.
    """
    g = g.sort_values("trade_date")

    # 거래일 플래그(추후 거래소 캘린더와 연동 가능, 현재는 True)
    g["is_trading_day"] = True

    # 결측/보간 관련 (현재는 단순 NaN 존재 여부)
    g["is_missing_imputed"] = g["adj_close"].isna()

    # 수익률 기반 이상치 플래그 (절대수익률 30% 초과)
    g["is_outlier"] = g["ret_1d"].abs() > 0.30

    # 조기폐장 등 부분 거래일 여부(초기에는 False, 나중에 캘린더 연동 가능)
    g["is_partial_day"] = False

    return g


# =========================
# 4. Feature Builder (전체)
# =========================

def build_eod_features(df: pd.DataFrame, ctx: EodFeatureRunContext) -> pd.DataFrame:
    """
    Bronze EOD → Silver eod_features 전체 변환.
    """
    if df.empty:
        return df

    df = df.sort_values(["symbol", "trade_date"]).copy()

    def _per_symbol(g: pd.DataFrame) -> pd.DataFrame:
        g = _add_returns(g)
        g = _add_vol_ma(g)
        g = _add_atr(g)
        g = _add_rsi(g)
        g = _add_micro_features(g)
        g = _add_quality_flags(g)
        return g

    # Pandas 3.0+: groupby.apply() drops group key column.
    # Use explicit loop to preserve 'symbol'.
    parts = []
    for _sym, grp in df.groupby("symbol", sort=False):
        parts.append(_per_symbol(grp))
    df = pd.concat(parts, ignore_index=True)

    # Silver meta
    df["run_id_silver"] = ctx.run_id
    df["ingestion_ts_silver"] = ctx.ingestion_ts

    # 최종 출력 구간으로 필터
    df = df[
        (pd.to_datetime(df["trade_date"]).dt.date >= ctx.feature_start_date)
        & (pd.to_datetime(df["trade_date"]).dt.date <= ctx.feature_end_date)
    ]

    # Silver 최종 스키마 정리
    keep_cols = [
        "symbol",
        "trade_date",
        "source",
        "theme",
        "open",
        "high",
        "low",
        "close",
        "adj_close",
        "volume",
        "currency",
        # Bronze meta
        "run_id",
        "ingestion_ts",
        # Silver features
        "prev_adj_close",
        "ret_1d",
        "log_ret_1d",
        "ret_5d",
        "ret_20d",
        "vol_20d",
        "vol_60d",
        "ma_5",
        "ma_20",
        "ma_60",
        "ma_120",
        "ma_ratio_5_20",
        "atr_14",
        "gain_1d",
        "loss_1d",
        "avg_gain_14",
        "avg_loss_14",
        "rsi_14",
        "intraday_range",
        "gap_open",
        "volume_zscore_20d",
        "is_trading_day",
        "is_missing_imputed",
        "is_outlier",
        "is_partial_day",
        # Observability labels (Bronze pass-through)
        "asset_group",
        "asset_name",
        "asset_subtype",
        # Silver meta
        "run_id_silver",
        "ingestion_ts_silver",
    ]

    for c in keep_cols:
        if c not in df.columns:
            df[c] = np.nan

    df = df[keep_cols].copy()
    return df


# =========================
# 5. Silver Writer (멱등성)
# =========================

def _partition_keys(df: pd.DataFrame) -> Iterable[Tuple[str, int, int]]:
    dates = pd.to_datetime(df["trade_date"])
    symbols = df["symbol"].astype(str)
    return sorted(set(zip(symbols, dates.dt.year, dates.dt.month)))


def write_silver_eod_features(df: pd.DataFrame, ctx: EodFeatureRunContext) -> None:
    """
    Silver Layer 저장.
    - 파티션: symbol=XXX/year=YYYY/month=MM
    - 파일: eod_features_YYYYMM.parquet
    - 전략: (symbol, year, month) 파티션 단위 overwrite (tmp 디렉토리 사용)
    """
    if df.empty:
        print("[SilverEOD] Nothing to write.")
        return

    df = df.copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"])

    tmp_root = ctx.cfg.silver_root / f"_tmp_run={ctx.run_id}"

    for symbol, year, month in _partition_keys(df):
        part = df[
            (df["symbol"] == symbol)
            & (df["trade_date"].dt.year == year)
            & (df["trade_date"].dt.month == month)
        ]
        if part.empty:
            continue

        tmp_dir = (
            tmp_root
            / f"symbol={symbol}"
            / f"year={year:04d}"
            / f"month={month:02d}"
        )
        final_dir = (
            ctx.cfg.silver_root
            / f"symbol={symbol}"
            / f"year={year:04d}"
            / f"month={month:02d}"
        )

        tmp_dir.mkdir(parents=True, exist_ok=True)
        final_dir.mkdir(parents=True, exist_ok=True)

        tmp_file = tmp_dir / f"eod_features_{year:04d}{month:02d}.parquet"
        final_file = final_dir / f"eod_features_{year:04d}{month:02d}.parquet"

        part.to_parquet(tmp_file, index=False)

        # 파티션 단위 overwrite
        if final_file.exists():
            final_file.unlink()
        tmp_file.replace(final_file)

        print(f"[SilverEOD] Saved: {final_file}")

    # tmp 디렉토리 정리
    if tmp_root.exists():
        shutil.rmtree(tmp_root)
        print(f"[SilverEOD] Cleaned tmp directory: {tmp_root}")


# =========================
# 6. Runner (MacroJobRunner 유사)
# =========================

@dataclass
class EodFeatureResult:
    run_id: str
    start_date: dt.date
    end_date: dt.date
    symbols: List[str]
    row_count: int


def run_eod_silver_features(
    start_date: dt.date,
    end_date: dt.date,
    symbols: Optional[Sequence[str]] = None,
    cfg: Optional[EodFeatureConfig] = None,
) -> EodFeatureResult:
    """
    Bronze EOD → Silver EOD Feature 실행 러너.
    Airflow DAG에서 직접 호출하거나, CLI에서 호출 가능.
    """
    cfg = cfg or EodFeatureConfig.from_env()

    if symbols:
        target_symbols = [s.strip().upper() for s in symbols if s.strip()]
    else:
        # None이면 cfg.target_symbols 사용 (없으면 전체)
        target_symbols = cfg.target_symbols or []

    run_id = dt.datetime.utcnow().strftime("eodfeat_%Y%m%d%H%M%S")

    ctx = EodFeatureRunContext(
        feature_start_date=start_date,
        feature_end_date=end_date,
        run_id=run_id,
        ingestion_ts=pd.Timestamp.utcnow(),
        cfg=cfg,
    )
    cfg.target_symbols = target_symbols or None

    df_bronze = load_bronze_eod(ctx)
    if df_bronze.empty:
        print("[SilverEOD] No input bronze data. Exit.")
        return EodFeatureResult(
            run_id=run_id,
            start_date=start_date,
            end_date=end_date,
            symbols=target_symbols,
            row_count=0,
        )

    df_silver = build_eod_features(df_bronze, ctx)
    write_silver_eod_features(df_silver, ctx)

    return EodFeatureResult(
        run_id=run_id,
        start_date=start_date,
        end_date=end_date,
        symbols=target_symbols,
        row_count=int(len(df_silver)),
    )


# =========================
# 7. CLI Entrypoint
# =========================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Silver EOD Features")
    parser.add_argument("--start", type=str, required=True, help="YYYY-MM-DD")
    parser.add_argument("--end", type=str, required=True, help="YYYY-MM-DD")
    parser.add_argument("--run-id", type=str, default=None)
    parser.add_argument(
        "--symbols",
        type=str,
        default=None,
        help="Comma separated symbols (e.g. SPY,QQQ). If omitted, use cfg.target_symbols or all.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    feature_start = dt.datetime.strptime(args.start, "%Y-%m-%d").date()
    feature_end = dt.datetime.strptime(args.end, "%Y-%m-%d").date()

    cfg = EodFeatureConfig.from_env()

    if args.symbols:
        target_symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    else:
        target_symbols = None

    result = run_eod_silver_features(
        start_date=feature_start,
        end_date=feature_end,
        symbols=target_symbols,
        cfg=cfg,
    )

    print(
        f"[SilverEOD] done. run_id={result.run_id}, "
        f"symbols={','.join(result.symbols)}, rows={result.row_count}, "
        f"range=[{result.start_date}, {result.end_date}]"
    )


if __name__ == "__main__":
    main()
