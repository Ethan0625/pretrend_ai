"""Gold SKEW feature builder.

Contract: .agent/task/CODEX_P5-2d_skew_gold_feature.md
"""

from __future__ import annotations

import argparse
import math
import shutil
from pathlib import Path
from typing import Optional

import pandas as pd


SKEW_GOLD_COLUMNS = [
    "trade_date",
    "skew_close",
    "skew_zscore_252",
    "skew_extreme_flag",
    "run_id",
    "ingestion_ts",
]


def load_skew_eod_gold(eod_root: Path) -> pd.DataFrame:
    files = sorted((eod_root / "symbol=^SKEW").rglob("*.parquet"))
    if not files:
        return pd.DataFrame(columns=["trade_date", "adj_close"])
    df = pd.concat((pd.read_parquet(f) for f in files), ignore_index=True)
    out = df[["trade_date", "adj_close"]].copy()
    out["trade_date"] = pd.to_datetime(out["trade_date"]).dt.date
    out = out.sort_values("trade_date").drop_duplicates(
        subset=["trade_date"], keep="last"
    )
    return out.reset_index(drop=True)


def build_skew_gold_features(df_eod: pd.DataFrame, run_id: str) -> pd.DataFrame:
    if df_eod.empty:
        return pd.DataFrame(columns=SKEW_GOLD_COLUMNS)

    out = df_eod[["trade_date", "adj_close"]].copy()
    out = out.sort_values("trade_date").reset_index(drop=True)
    out["skew_close"] = out["adj_close"].astype(float)

    rolling = out["skew_close"].rolling(window=252, min_periods=60)
    rolling_mean = rolling.mean()
    rolling_std = rolling.std()
    out["skew_zscore_252"] = (out["skew_close"] - rolling_mean) / rolling_std

    zscores = out["skew_zscore_252"].dropna()
    if zscores.empty:
        out["skew_extreme_flag"] = 0
    else:
        top_k = max(1, math.ceil(len(out) * 0.05))
        extreme_dates = set(zscores.nlargest(top_k).index.tolist())
        out["skew_extreme_flag"] = out.index.to_series().isin(extreme_dates).astype(int)

    out["run_id"] = run_id
    out["ingestion_ts"] = pd.Timestamp.now("UTC")
    return out[SKEW_GOLD_COLUMNS].copy()


def write_skew_gold_features(df: pd.DataFrame, gold_root: Path, run_id: str) -> None:
    if df.empty:
        return

    for stale_tmp in gold_root.glob("_tmp_run=*"):
        if stale_tmp.is_dir():
            shutil.rmtree(stale_tmp, ignore_errors=True)

    tmp_root = gold_root / f"_tmp_run={run_id}"
    for row in df.itertuples(index=False):
        trade_date = pd.Timestamp(row.trade_date).date()
        date_token = trade_date.strftime("%Y-%m-%d")
        file_token = trade_date.strftime("%Y%m%d")
        tmp_dir = tmp_root / f"date={date_token}"
        final_dir = gold_root / f"date={date_token}"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        final_dir.mkdir(parents=True, exist_ok=True)

        tmp_file = tmp_dir / f"skew_{file_token}.parquet"
        final_file = final_dir / f"skew_{file_token}.parquet"
        pd.DataFrame([row._asdict()]).to_parquet(tmp_file, index=False)
        if final_file.exists():
            final_file.unlink()
        shutil.move(str(tmp_file), str(final_file))

    if tmp_root.exists():
        shutil.rmtree(tmp_root)


def run_skew_gold_pipeline(
    eod_root: Path,
    gold_root: Path,
    run_id: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> pd.DataFrame:
    df = load_skew_eod_gold(eod_root)
    if df.empty:
        return pd.DataFrame(columns=SKEW_GOLD_COLUMNS)

    if start is not None:
        start_date = pd.to_datetime(start).date()
        df = df[df["trade_date"] >= start_date]
    if end is not None:
        end_date = pd.to_datetime(end).date()
        df = df[df["trade_date"] <= end_date]

    features = build_skew_gold_features(df, run_id=run_id)
    write_skew_gold_features(features, gold_root=gold_root, run_id=run_id)
    return features


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--eod-root",
        default="data/gold/eod/eod_features",
    )
    parser.add_argument(
        "--gold-root",
        default="data/gold/macro/skew/put_call",
    )
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    args = parser.parse_args()

    run_id = args.run_id or f"skew_gold_{pd.Timestamp.now('UTC').strftime('%Y%m%dT%H%M%SZ')}"
    df = run_skew_gold_pipeline(
        eod_root=Path(args.eod_root),
        gold_root=Path(args.gold_root),
        run_id=run_id,
        start=args.start,
        end=args.end,
    )
    print(f"rows={len(df)} run_id={run_id}")


if __name__ == "__main__":
    main()
