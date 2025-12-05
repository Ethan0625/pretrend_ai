from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from pretrend.pipeline.ingest.base import IngestContext
from pretrend.pipeline.ingest.eod import (
    EodFetcher,
    EodNormalizer,
    EodWriter,
    EodIngestConfig,
    run_eod_bronze_ingest,
)


def _make_dummy_raw_df() -> pd.DataFrame:
    """Fetcher 이후에 나올 법한 dummy raw 데이터 (Bronze 정규화 이전 형태에 가깝게 정의)."""
    data = {
        "symbol": ["SPY", "SPY"],
        "trade_date": ["2024-11-01", "2024-11-04"],
        "open": [500.0, 505.0],
        "high": [510.0, 515.0],
        "low": [495.0, 500.0],
        "close": [508.0, 512.0],
        "adj_close": [508.0, 512.0],
        "volume": [1_000_000, 1_200_000],
        "source": ["yahoo", "yahoo"],
        "currency": ["USD", "USD"],
        "theme": ["GENERIC", "GENERIC"],
    }
    return pd.DataFrame(data)


def test_eod_normalizer_adds_metadata_and_types():
    """
    EodNormalizer가:
    - 표준 Bronze 스키마 컬럼을 생성하고
    - run_id / ingestion_ts 메타데이터를 추가하며
    - 기본 타입을 맞추는지 검증.
    """
    ctx = IngestContext(
        domain="eod",
        dataset="daily_prices",
        start_date=date(2024, 11, 1),
        end_date=date(2024, 11, 4),
    )

    raw_df = _make_dummy_raw_df()
    normalizer = EodNormalizer()

    norm_df = normalizer.normalize(ctx, raw_df)

    # 핵심 컬럼 존재 여부 (Bronze 표준 스키마 기준)
    expected_cols = {
        "symbol",
        "theme",
        "source",
        "trade_date",
        "open",
        "high",
        "low",
        "close",
        "adj_close",
        "volume",
        "currency",
        "run_id",
        "ingestion_ts",
    }
    assert expected_cols.issubset(set(norm_df.columns))

    # 타입 체크
    from datetime import date as _date_type

    assert isinstance(norm_df["trade_date"].iloc[0], _date_type)
    assert pd.api.types.is_float_dtype(norm_df["open"])
    assert pd.api.types.is_integer_dtype(norm_df["volume"])

    # run_id / ingestion_ts가 context 기반으로 세팅되는지
    assert (norm_df["run_id"] == ctx.run_id).all()
    assert not norm_df["ingestion_ts"].isna().any()


def test_eod_writer_creates_partitioned_parquet(tmp_path: Path):
    """
    EodWriter가 source/theme/symbol/trade_date 파티션 구조로 Parquet 저장하는지 검증.
    """
    output_root = tmp_path / "bronze"
    ctx = IngestContext(
        domain="eod",
        dataset="daily_prices",
        output_root=output_root,
    )

    raw_df = _make_dummy_raw_df()
    normalizer = EodNormalizer()
    norm_df = normalizer.normalize(ctx, raw_df)

    writer = EodWriter()
    writer.write(ctx, norm_df)

    base_dir = (
        output_root
        / "eod"
        / "daily_prices"
        / "source=yahoo"
        / "theme=GENERIC"
        / "symbol=SPY"
    )

    # trade_date 기준 파티션 디렉토리 및 파일 존재 확인
    d1 = base_dir / "trade_date=2024-11-01" / "eod.parquet"
    d2 = base_dir / "trade_date=2024-11-04" / "eod.parquet"

    assert d1.exists(), f"{d1} 경로에 eod.parquet가 생성되어야 함"
    assert d2.exists(), f"{d2} 경로에 eod.parquet가 생성되어야 함"


@pytest.mark.skip(reason="실제 yfinance 호출이므로, 통합 테스트 시에만 사용")
def test_run_eod_bronze_ingest_integration(tmp_path: Path, monkeypatch):
    """
    통합 테스트:
    - 실제 yfinance 호출을 사용하는 경우 (네트워크 의존)
    - CI에서는 skip, 로컬에서 수동으로 확인용
    """
    # PRETREND_DATA_ROOT를 temp 디렉토리로 바인딩
    monkeypatch.setenv("PRETREND_DATA_ROOT", str(tmp_path))

    cfg = EodIngestConfig(data_root=tmp_path)
    result = run_eod_bronze_ingest(
        start_date=date(2024, 11, 1),
        end_date=date(2024, 11, 4),
        cfg=cfg,
    )

    assert result.row_count >= 0
    # 기본 심볼(SPY, QQQ, VOO) 세트가 그대로 사용되는지 검증
    assert set(result.symbols) == set(cfg.default_symbols)
