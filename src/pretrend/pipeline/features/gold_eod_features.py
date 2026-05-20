"""
Gold EOD Feature v1 — fact mart.

Silver EOD features를 Gold 레이어로 전파한다.
- Observability labels (asset_group/asset_name/asset_subtype) carry-forward
- lineage 컬럼 추가 (run_id_gold, ingestion_ts_gold)
- Grain: (symbol, trade_date)
"""
from __future__ import annotations

import argparse
import logging
import os
import shutil
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

import pandas as pd

logger = logging.getLogger(__name__)


GOLD_EOD_FEATURE_COLUMNS: List[str] = [
    # identity
    "symbol",
    "trade_date",
    # price
    "open",
    "high",
    "low",
    "close",
    "adj_close",
    "volume",
    "currency",
    # returns
    "prev_adj_close",
    "ret_1d",
    "log_ret_1d",
    "ret_5d",
    "ret_20d",
    # volatility / MA
    "vol_20d",
    "vol_60d",
    "ma_5",
    "ma_20",
    "ma_60",
    "ma_120",
    "ma_ratio_5_20",
    # technical
    "atr_14",
    "rsi_14",
    # micro
    "intraday_range",
    "gap_open",
    "volume_zscore_20d",
    # quality
    "is_trading_day",
    "is_missing_imputed",
    "is_outlier",
    "is_partial_day",
    # observability labels
    "asset_group",
    "asset_name",
    "asset_subtype",
    # lineage
    "run_id_gold",
    "ingestion_ts_gold",
]


# ── Loader ──────────────────────────────────────────────


def _iter_month_starts(start: date, end: date) -> Iterable[date]:
    current = start.replace(day=1)
    end_month = end.replace(day=1)
    while current <= end_month:
        yield current
        current = (pd.Timestamp(current) + pd.DateOffset(months=1)).date()


def _is_tmp_path(path: Path) -> bool:
    return any(part.startswith("_tmp_run=") for part in path.parts)


def _list_silver_eod_files(
    silver_root: Path,
    start_date: Optional[date],
    end_date: Optional[date],
    symbols: Optional[List[str]],
) -> list[Path]:
    if symbols:
        symbol_dirs = [silver_root / f"symbol={symbol}" for symbol in symbols]
    else:
        symbol_dirs = sorted(silver_root.glob("symbol=*"))

    if start_date is None or end_date is None:
        files = [
            path
            for symbol_dir in symbol_dirs
            for path in symbol_dir.rglob("*.parquet")
            if not _is_tmp_path(path)
        ]
        return sorted(set(files))

    files: list[Path] = []
    seen: set[Path] = set()
    for symbol_dir in symbol_dirs:
        for month_start in _iter_month_starts(start_date, end_date):
            month_dir = (
                symbol_dir
                / f"year={month_start.year:04d}"
                / f"month={month_start.month:02d}"
            )
            for path in month_dir.glob("*.parquet"):
                if not _is_tmp_path(path) and path not in seen:
                    seen.add(path)
                    files.append(path)
    return sorted(files)


def load_silver_eod_features(
    silver_root: Path,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    symbols: Optional[List[str]] = None,
) -> pd.DataFrame:
    """Silver EOD features parquet를 로드한다.

    Parameters
    ----------
    silver_root : Silver EOD features 루트 (e.g. data/silver/eod/eod_features)
    start_date, end_date : 날짜 필터 (optional)
    symbols : 심볼 필터 (optional)
    """
    files = _list_silver_eod_files(silver_root, start_date, end_date, symbols)
    if not files:
        logger.warning("[GoldEOD] No Silver EOD parquet under %s", silver_root)
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


# ── Builder ─────────────────────────────────────────────


def build_gold_eod_features(
    df_silver: pd.DataFrame,
    run_id: Optional[str] = None,
) -> pd.DataFrame:
    """Silver EOD → Gold EOD fact mart.

    Parameters
    ----------
    df_silver : Silver EOD features DataFrame.
    run_id : Gold run ID (optional, auto-generated if None).

    Returns
    -------
    DataFrame with GOLD_EOD_FEATURE_COLUMNS, sorted by (symbol, trade_date).
    """
    if df_silver.empty:
        return pd.DataFrame(columns=GOLD_EOD_FEATURE_COLUMNS)

    if run_id is None:
        run_id = pd.Timestamp.now("UTC").strftime("gold_eod_%Y%m%d%H%M%S")

    df = df_silver.copy()

    # Lineage
    df["run_id_gold"] = run_id
    df["ingestion_ts_gold"] = pd.Timestamp.now("UTC")

    # Dedup on grain (symbol, trade_date) — keep last
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    df = df.drop_duplicates(subset=["symbol", "trade_date"], keep="last")

    # Ensure all output columns exist
    for col in GOLD_EOD_FEATURE_COLUMNS:
        if col not in df.columns:
            df[col] = None

    # Drop intermediate columns not needed in Gold
    df = df[GOLD_EOD_FEATURE_COLUMNS].copy()

    df = df.sort_values(["symbol", "trade_date"]).reset_index(drop=True)
    return df


# ── Writer ──────────────────────────────────────────────


def write_gold_eod_features(
    df: pd.DataFrame,
    gold_root: Path,
    run_id: str,
) -> None:
    """Gold EOD features를 parquet로 저장 (멱등, partition overwrite).

    경로: gold_root/symbol=XXX/year=YYYY/month=MM/gold_eod_features_YYYYMM.parquet
    """
    if df.empty:
        logger.warning("[GoldEOD] Nothing to write.")
        return

    df = df.copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"])

    tmp_root = gold_root / f"_tmp_run={run_id}"

    partitions = sorted(
        set(
            zip(
                df["symbol"].astype(str),
                df["trade_date"].dt.year,
                df["trade_date"].dt.month,
            )
        )
    )

    for symbol, year, month in partitions:
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
            gold_root
            / f"symbol={symbol}"
            / f"year={year:04d}"
            / f"month={month:02d}"
        )
        tmp_dir.mkdir(parents=True, exist_ok=True)
        final_dir.mkdir(parents=True, exist_ok=True)

        tmp_file = tmp_dir / f"gold_eod_features_{year:04d}{month:02d}.parquet"
        final_file = final_dir / f"gold_eod_features_{year:04d}{month:02d}.parquet"

        part.to_parquet(tmp_file, index=False)

        if final_file.exists():
            final_file.unlink()
        try:
            tmp_file.replace(final_file)
        except OSError:
            shutil.move(str(tmp_file), str(final_file))

        logger.info("[GoldEOD] Saved: %s", final_file)

    if tmp_root.exists():
        shutil.rmtree(tmp_root)
        logger.info("[GoldEOD] Cleaned tmp: %s", tmp_root)


# ── CLI ────────────────────────────────────────────────


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build Gold EOD Features from Silver EOD parquet",
    )
    parser.add_argument("--start", type=str, required=True, help="YYYY-MM-DD")
    parser.add_argument("--end", type=str, required=True, help="YYYY-MM-DD")
    parser.add_argument(
        "--symbols",
        type=str,
        default=None,
        help="Comma separated symbols (e.g. SPY,QQQ). If omitted, all symbols.",
    )
    parser.add_argument("--run-id", type=str, default=None)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

    args = parse_args(argv)
    start_date = datetime.strptime(args.start, "%Y-%m-%d").date()
    end_date = datetime.strptime(args.end, "%Y-%m-%d").date()

    data_root = Path(os.getenv("PRETREND_DATA_ROOT", "data"))
    silver_root = data_root / "silver" / "eod" / "eod_features"
    gold_root = data_root / "gold" / "eod" / "eod_features"
    run_id = args.run_id or pd.Timestamp.now("UTC").strftime("gold_eod_%Y%m%d%H%M%S")

    symbols = None
    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    # 1) Load Silver
    df_silver = load_silver_eod_features(
        silver_root, start_date=start_date, end_date=end_date, symbols=symbols,
    )
    if df_silver.empty:
        logger.warning("[GoldEOD] No Silver data. Nothing to build.")
        return

    # 2) Build Gold
    gold = build_gold_eod_features(df_silver, run_id=run_id)

    # 3) Write
    write_gold_eod_features(gold, gold_root, run_id)

    n_symbols = gold["symbol"].nunique() if not gold.empty else 0
    print(
        f"[GoldEOD] done. run_id={run_id}, "
        f"symbols={n_symbols}, rows={len(gold)}, "
        f"range=[{start_date}, {end_date}]"
    )


if __name__ == "__main__":
    main()
