"""
EOD Observability Contract 테스트 — OL1~OL5.

PR#1 DoD 필수 테스트 5종.
계약 문서: docs/architecture/eod_observability_contract.md
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from pretrend.pipeline.config.eod_observability import (
    ASSET_GROUP_ENUM,
    LABEL_BY_SYMBOL_V1,
    OBSERVABILITY_SET_V1,
    OBSERVABILITY_SYMBOLS_V1,
    validate_observability_set,
)
from pretrend.pipeline.ingest.base import IngestContext
from pretrend.pipeline.ingest.eod import EodNormalizer


# ── helpers ──────────────────────────────────────────────

def _make_raw_df(symbols: list[str]) -> pd.DataFrame:
    """Fetcher 이후 raw DataFrame 생성 (Bronze 정규화 이전)."""
    rows = []
    for sym in symbols:
        rows.append(
            {
                "symbol": sym,
                "trade_date": "2024-11-01",
                "open": 100.0,
                "high": 105.0,
                "low": 95.0,
                "close": 102.0,
                "adj_close": 102.0,
                "volume": 1_000_000,
                "source": "YF",
                "currency": "USD",
                "theme": "GENERIC",
            }
        )
    return pd.DataFrame(rows)


def _normalize(symbols: list[str]) -> pd.DataFrame:
    """symbol 리스트 → EodNormalizer 결과 반환."""
    ctx = IngestContext(
        domain="eod",
        dataset="daily_prices",
        start_date=date(2024, 11, 1),
        end_date=date(2024, 11, 1),
    )
    raw = _make_raw_df(symbols)
    normalizer = EodNormalizer()
    return normalizer.normalize(ctx, raw)


# ── OL1: SOT coverage & no duplicates ───────────────────

class TestOL1SotCoverage:
    """OL1: Observability SOT 커버리지 및 중복 없음."""

    def test_ol1_sot_coverage_and_no_duplicates(self):
        """OBSERVABILITY_SET_V1에 35개 ETF가 중복 없이 존재한다."""
        # 35개 ETF
        assert len(OBSERVABILITY_SET_V1) == 35

        # symbol 중복 금지
        symbols = [entry["symbol"] for entry in OBSERVABILITY_SET_V1]
        assert len(symbols) == len(set(symbols)), "symbol 중복 발견"

        # OBSERVABILITY_SYMBOLS_V1 == set of symbols
        assert set(OBSERVABILITY_SYMBOLS_V1) == set(symbols)

        # LABEL_BY_SYMBOL_V1 키 == symbols
        assert set(LABEL_BY_SYMBOL_V1.keys()) == set(symbols)

    def test_ol1_asset_group_enum_valid(self):
        """모든 entry의 asset_group이 ENUM에 속한다."""
        for entry in OBSERVABILITY_SET_V1:
            assert entry["asset_group"] in ASSET_GROUP_ENUM, (
                f"{entry['symbol']}: asset_group={entry['asset_group']} "
                f"not in {ASSET_GROUP_ENUM}"
            )

    def test_ol1_symbols_uppercase(self):
        """모든 symbol이 대문자이다."""
        for entry in OBSERVABILITY_SET_V1:
            assert entry["symbol"] == entry["symbol"].upper()

    def test_ol1_validate_passes(self):
        """validate_observability_set()이 예외 없이 통과한다."""
        validate_observability_set()


# ── OL2: Bronze has labels and ENUM valid ────────────────

class TestOL2BronzeLabels:
    """OL2: Bronze 정규화 시 asset_group/asset_name/asset_subtype 컬럼이 부여된다."""

    def test_ol2_bronze_has_labels_and_enum_valid(self):
        """등록된 심볼의 Bronze 출력에 asset_* 라벨이 존재하고 ENUM이 유효하다."""
        norm = _normalize(["SPY", "QQQ", "TLT"])

        # 라벨 컬럼 존재
        for col in ("asset_group", "asset_name", "asset_subtype"):
            assert col in norm.columns, f"Bronze에 {col} 컬럼 없음"

        # asset_group ENUM 검증
        for _, row in norm.iterrows():
            assert row["asset_group"] in ASSET_GROUP_ENUM, (
                f"{row['symbol']}: asset_group={row['asset_group']} "
                f"not in {ASSET_GROUP_ENUM}"
            )

    def test_ol2_label_values_match_sot(self):
        """Bronze 라벨 값이 SOT와 일치한다."""
        norm = _normalize(["SPY"])
        row = norm.iloc[0]

        sot = LABEL_BY_SYMBOL_V1["SPY"]
        assert row["asset_group"] == sot["asset_group"]
        assert row["asset_name"] == sot["asset_name"]
        assert row["asset_subtype"] == sot["asset_subtype"]


# ── OL3: Unregistered symbol raises ─────────────────────

class TestOL3UnregisteredSymbol:
    """OL3: 미등록 심볼은 예외를 발생시킨다."""

    def test_ol3_unregistered_symbol_raises(self):
        """SOT에 없는 심볼로 정규화하면 ValueError가 발생한다."""
        with pytest.raises(ValueError, match="unregistered"):
            _normalize(["FAKE_TICKER_XYZ"])


# ── OL4: Bronze → Silver labels pass-through ────────────

class TestOL4SilverPassthrough:
    """OL4: Silver가 Bronze의 asset_* 라벨을 그대로 전파한다."""

    def test_ol4_bronze_to_silver_labels_passthrough(self):
        """build_eod_features 후 asset_* 컬럼이 변경 없이 유지된다."""
        from pretrend.pipeline.features.eod_features import (
            EodFeatureConfig,
            EodFeatureRunContext,
            build_eod_features,
        )

        # Bronze 데이터 준비 (lookback 포함)
        symbols = ["SPY"]
        rows = []
        trade_dates = pd.bdate_range("2024-01-01", "2024-06-30")
        for td in trade_dates:
            rows.append(
                {
                    "symbol": "SPY",
                    "trade_date": td.date(),
                    "source": "YF",
                    "theme": "GENERIC",
                    "open": 100.0,
                    "high": 105.0,
                    "low": 95.0,
                    "close": 102.0,
                    "adj_close": 102.0,
                    "volume": 1_000_000,
                    "currency": "USD",
                    "run_id": "test_run",
                    "ingestion_ts": pd.Timestamp("2024-07-01"),
                    "asset_group": "INDEX",
                    "asset_name": "SP500",
                    "asset_subtype": "BROAD_MARKET",
                }
            )
        bronze_df = pd.DataFrame(rows)

        cfg = EodFeatureConfig(data_root=Path("/tmp/test_ol4"))
        ctx = EodFeatureRunContext(
            feature_start_date=date(2024, 6, 1),
            feature_end_date=date(2024, 6, 30),
            run_id="test_ol4",
            ingestion_ts=pd.Timestamp("2024-07-01"),
            cfg=cfg,
        )

        silver = build_eod_features(bronze_df, ctx)

        # asset_* 컬럼 존재
        for col in ("asset_group", "asset_name", "asset_subtype"):
            assert col in silver.columns, f"Silver에 {col} 컬럼 없음"

        # 값 불변 검증
        assert (silver["asset_group"] == "INDEX").all()
        assert (silver["asset_name"] == "SP500").all()
        assert (silver["asset_subtype"] == "BROAD_MARKET").all()


# ── OL5: Partition overwrite — labels stable ─────────────

class TestOL5IdempotentLabels:
    """OL5: 파티션 덮어쓰기 후 라벨이 안정적이다."""

    def test_ol5_partition_overwrite_idempotent_labels_stable(self, tmp_path):
        """두 번 쓰기 후에도 asset_* 라벨이 동일하다."""
        from pretrend.pipeline.features.eod_features import (
            EodFeatureConfig,
            EodFeatureRunContext,
            write_silver_eod_features,
        )

        cfg = EodFeatureConfig(data_root=tmp_path)

        def _make_silver_df(run_label: str) -> pd.DataFrame:
            return pd.DataFrame(
                {
                    "symbol": ["SPY"],
                    "trade_date": [pd.Timestamp("2024-01-05")],
                    "source": ["YF"],
                    "theme": ["GENERIC"],
                    "open": [100.0],
                    "high": [105.0],
                    "low": [95.0],
                    "close": [102.0],
                    "adj_close": [102.0],
                    "volume": [1_000],
                    "currency": ["USD"],
                    "run_id": ["bronze_run"],
                    "ingestion_ts": [pd.Timestamp("2024-02-01")],
                    "prev_adj_close": [99.0],
                    "ret_1d": [0.01],
                    "log_ret_1d": [0.01],
                    "ret_5d": [0.02],
                    "ret_20d": [0.05],
                    "vol_20d": [0.015],
                    "vol_60d": [0.012],
                    "ma_5": [101.0],
                    "ma_20": [100.0],
                    "ma_60": [99.0],
                    "ma_120": [98.0],
                    "ma_ratio_5_20": [0.01],
                    "atr_14": [2.0],
                    "gain_1d": [1.0],
                    "loss_1d": [0.0],
                    "avg_gain_14": [0.7],
                    "avg_loss_14": [0.3],
                    "rsi_14": [70.0],
                    "intraday_range": [0.05],
                    "gap_open": [0.005],
                    "volume_zscore_20d": [0.3],
                    "is_trading_day": [True],
                    "is_missing_imputed": [False],
                    "is_outlier": [False],
                    "is_partial_day": [False],
                    "run_id_silver": [run_label],
                    "ingestion_ts_silver": [pd.Timestamp("2024-02-01")],
                    "asset_group": ["INDEX"],
                    "asset_name": ["SP500"],
                    "asset_subtype": ["BROAD_MARKET"],
                }
            )

        ctx1 = EodFeatureRunContext(
            feature_start_date=date(2024, 1, 1),
            feature_end_date=date(2024, 1, 31),
            run_id="run_first",
            ingestion_ts=pd.Timestamp("2024-02-01"),
            cfg=cfg,
        )
        ctx2 = EodFeatureRunContext(
            feature_start_date=date(2024, 1, 1),
            feature_end_date=date(2024, 1, 31),
            run_id="run_second",
            ingestion_ts=pd.Timestamp("2024-02-01"),
            cfg=cfg,
        )

        write_silver_eod_features(_make_silver_df("run_first"), ctx1)
        write_silver_eod_features(_make_silver_df("run_second"), ctx2)

        # 파티션에서 읽기
        part_dir = (
            cfg.silver_root
            / "symbol=SPY"
            / "year=2024"
            / "month=01"
        )
        files = sorted(part_dir.rglob("*.parquet"))
        assert files, "parquet 파일 없음"

        loaded = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)

        # 중복 없음
        assert len(loaded) == 1

        # 라벨 안정성
        row = loaded.iloc[0]
        assert row["asset_group"] == "INDEX"
        assert row["asset_name"] == "SP500"
        assert row["asset_subtype"] == "BROAD_MARKET"
