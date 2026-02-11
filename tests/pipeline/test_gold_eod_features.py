"""
Gold EOD Feature v1 테스트 — GE1~GE5.

PR#3 DoD 필수 테스트.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from pretrend.pipeline.features.gold_eod_features import (
    GOLD_EOD_FEATURE_COLUMNS,
    build_gold_eod_features,
    write_gold_eod_features,
    load_silver_eod_features,
)


# ── fixture helpers ──────────────────────────────────────

def _make_silver_df(
    symbols: list[str] | None = None,
    n_days: int = 5,
    start: str = "2024-06-01",
) -> pd.DataFrame:
    """Silver EOD features fixture."""
    symbols = symbols or ["SPY", "TLT"]
    trade_dates = pd.bdate_range(start, periods=n_days)
    rows = []
    for sym in symbols:
        for i, td in enumerate(trade_dates):
            price = 100.0 + i
            rows.append(
                {
                    "symbol": sym,
                    "trade_date": td.date(),
                    "source": "YF",
                    "theme": "GENERIC",
                    "open": price,
                    "high": price + 5,
                    "low": price - 5,
                    "close": price + 2,
                    "adj_close": price + 2,
                    "volume": 1_000_000,
                    "currency": "USD",
                    "run_id": "bronze_run",
                    "ingestion_ts": pd.Timestamp("2024-07-01"),
                    "prev_adj_close": price - 1 if i > 0 else None,
                    "ret_1d": 0.01 if i > 0 else None,
                    "log_ret_1d": 0.01 if i > 0 else None,
                    "ret_5d": None,
                    "ret_20d": None,
                    "vol_20d": 0.015,
                    "vol_60d": 0.012,
                    "ma_5": price,
                    "ma_20": price - 1,
                    "ma_60": price - 2,
                    "ma_120": price - 3,
                    "ma_ratio_5_20": 0.01,
                    "atr_14": 2.0,
                    "gain_1d": 1.0,
                    "loss_1d": 0.0,
                    "avg_gain_14": 0.7,
                    "avg_loss_14": 0.3,
                    "rsi_14": 70.0,
                    "intraday_range": 0.05,
                    "gap_open": 0.005,
                    "volume_zscore_20d": 0.3,
                    "is_trading_day": True,
                    "is_missing_imputed": False,
                    "is_outlier": False,
                    "is_partial_day": False,
                    "asset_group": "INDEX" if sym != "TLT" else "BOND",
                    "asset_name": "SP500" if sym != "TLT" else "US_TREASURY_20Y",
                    "asset_subtype": "BROAD_MARKET" if sym != "TLT" else "LONG_DURATION",
                    "run_id_silver": "silver_run",
                    "ingestion_ts_silver": pd.Timestamp("2024-07-01"),
                }
            )
    return pd.DataFrame(rows)


def _run_gold(
    symbols: list[str] | None = None,
    n_days: int = 5,
) -> pd.DataFrame:
    silver = _make_silver_df(symbols=symbols, n_days=n_days)
    return build_gold_eod_features(silver)


# ── GE1: Grain uniqueness ────────────────────────────────

class TestGrainUniqueness:
    """GE1: (symbol, trade_date) grain에 중복이 없어야 한다."""

    def test_ge1_no_duplicate_grain(self):
        gold = _run_gold()
        dupes = gold.duplicated(subset=["symbol", "trade_date"], keep=False)
        assert dupes.sum() == 0, f"Duplicate rows: {gold[dupes]}"

    def test_ge1_row_count(self):
        """2 symbols * 5 days = 10 rows."""
        gold = _run_gold()
        assert len(gold) == 10


# ── GE2: Output columns ─────────────────────────────────

class TestOutputColumns:
    """GE2: Gold EOD 출력 컬럼이 계약과 일치한다."""

    def test_ge2_output_columns(self):
        gold = _run_gold()
        for col in GOLD_EOD_FEATURE_COLUMNS:
            assert col in gold.columns, f"Missing column: {col}"


# ── GE3: Labels pass-through ────────────────────────────

class TestLabelsPassthrough:
    """GE3: Silver의 asset_* 라벨이 Gold까지 변경 없이 전파된다."""

    def test_ge3_labels_match_silver(self):
        gold = _run_gold()

        spy_rows = gold[gold["symbol"] == "SPY"]
        assert (spy_rows["asset_group"] == "INDEX").all()
        assert (spy_rows["asset_name"] == "SP500").all()
        assert (spy_rows["asset_subtype"] == "BROAD_MARKET").all()

        tlt_rows = gold[gold["symbol"] == "TLT"]
        assert (tlt_rows["asset_group"] == "BOND").all()
        assert (tlt_rows["asset_name"] == "US_TREASURY_20Y").all()
        assert (tlt_rows["asset_subtype"] == "LONG_DURATION").all()


# ── GE4: Lineage columns ────────────────────────────────

class TestLineage:
    """GE4: Gold lineage 컬럼이 존재한다."""

    def test_ge4_lineage_columns(self):
        gold = _run_gold()
        assert "run_id_gold" in gold.columns
        assert "ingestion_ts_gold" in gold.columns
        assert gold["run_id_gold"].notna().all()
        assert gold["ingestion_ts_gold"].notna().all()


# ── GE5: Write idempotency ──────────────────────────────

class TestWriteIdempotent:
    """GE5: 파티션 덮어쓰기 후 중복 없이 라벨이 안정적이다."""

    def test_ge5_partition_overwrite_idempotent(self, tmp_path):
        silver = _make_silver_df()
        gold1 = build_gold_eod_features(silver, run_id="run_first")
        gold2 = build_gold_eod_features(silver, run_id="run_second")

        gold_root = tmp_path / "gold" / "eod" / "eod_features"

        write_gold_eod_features(gold1, gold_root, "run_first")
        write_gold_eod_features(gold2, gold_root, "run_second")

        # 전체 parquet 읽기
        files = sorted(gold_root.rglob("*.parquet"))
        assert files, "No parquet files found"

        loaded = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)

        # 중복 없음
        dupes = loaded.duplicated(subset=["symbol", "trade_date"], keep=False)
        assert dupes.sum() == 0

        # 라벨 안정
        spy = loaded[loaded["symbol"] == "SPY"]
        assert (spy["asset_group"] == "INDEX").all()
        assert (spy["asset_name"] == "SP500").all()

    def test_ge5_load_silver_roundtrip(self, tmp_path):
        """Silver 파일 저장 후 load_silver_eod_features로 읽을 수 있다."""
        from pretrend.pipeline.features.eod_features import (
            EodFeatureConfig,
            EodFeatureRunContext,
            write_silver_eod_features,
        )

        silver = _make_silver_df(n_days=3)

        cfg = EodFeatureConfig(data_root=tmp_path)
        ctx = EodFeatureRunContext(
            feature_start_date=date(2024, 6, 1),
            feature_end_date=date(2024, 6, 30),
            run_id="test_load",
            ingestion_ts=pd.Timestamp("2024-07-01"),
            cfg=cfg,
        )

        # trade_date를 Timestamp로 변환 (writer가 기대하는 형식)
        silver_ts = silver.copy()
        silver_ts["trade_date"] = pd.to_datetime(silver_ts["trade_date"])
        write_silver_eod_features(silver_ts, ctx)

        loaded = load_silver_eod_features(
            cfg.silver_root,
            start_date=date(2024, 6, 1),
            end_date=date(2024, 6, 30),
        )
        assert not loaded.empty
        assert "asset_group" in loaded.columns
