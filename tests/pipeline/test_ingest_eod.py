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
    """Fetcher 이후에 나올 법한 dummy raw 데이터."""
    data = {
        "symbol": ["SPY", "SPY"],
        "date": ["2024-11-01", "2024-11-04"],
        "open": [500.0, 505.0],
        "high": [510.0, 515.0],
        "low": [495.0, 500.0],
        "close": [508.0, 512.0],
        "adj_close": [508.0, 512.0],
        "volume": [1_000_000, 1_200_000],
        "source": ["yahoo", "yahoo"],
        "currency": ["USD", "USD"],
    }
    return pd.DataFrame(data)


def test_eod_normalizer_adds_metadata_and_types():
    """Normalizer가 run_id / ingestion_ts 등을 추가하고 타입을 맞추는지 검증."""
    ctx = IngestContext(
        domain="eod",
        dataset="daily_prices",
        start_date=date(2024, 11, 1),
        end_date=date(2024, 11, 4),
    )

    raw_df = _make_dummy_raw_df()
    normalizer = EodNormalizer()

    norm_df = normalizer.normalize(ctx, raw_df)

    # 핵심 컬럼 존재 여부
    expected_cols = {
        "symbol",
        "date",
        "open",
        "high",
        "low",
        "close",
        "adj_close",
        "volume",
        "source",
        "currency",
        "run_id",
        "ingestion_ts",
    }
    assert expected_cols.issubset(set(norm_df.columns))

    # 타입 체크
    assert pd.api.types.is_datetime64_any_dtype(norm_df["date"])
    assert pd.api.types.is_float_dtype(norm_df["open"])
    assert pd.api.types.is_integer_dtype(norm_df["volume"])

    # run_id / ingestion_ts가 context 기반으로 세팅되는지
    assert (norm_df["run_id"] == ctx.run_id).all()
    assert not norm_df["ingestion_ts"].isna().any()


def test_eod_writer_creates_partitioned_parquet(tmp_path: Path):
    """EodWriter가 source/symbol/year/month 구조로 Parquet 저장하는지 검증."""
    output_root = tmp_path / "bronze"
    ctx = IngestContext(
        domain="eod",
        dataset="daily_prices",
        output_root=output_root,
    )

    norm_df = _make_dummy_raw_df()
    norm_df["date"] = pd.to_datetime(norm_df["date"])

    writer = EodWriter()
    writer.write(ctx, norm_df)

    # SPY 2024-11 기준으로 경로가 만들어졌는지 확인
    year = 2024
    month = 11

    base_dir = (
        output_root
        / "eod"
        / "daily_prices"
        / "source=yahoo"
        / "symbol=SPY"
        / f"year={year:04d}"
        / f"month={month:02d}"
    )
    files = list(base_dir.glob("eod_SPY_2024*.parquet"))

    assert len(files) >= 1, "SPY EOD parquet 파일이 최소 1개 이상 생성되어야 함"


@pytest.mark.skip(reason="실제 yfinance 호출이므로, 통합 테스트 시에만 사용")
def test_run_eod_bronze_ingest_integration(tmp_path: Path, monkeypatch):
    """
    통합 테스트:
    - 실제 yfinance 호출을 사용하는 경우 (네트워크 의존)
    - CI에서는 skip, 로컬에서 수동으로 확인용
    """
    # PRETREND_DATA_ROOT를 temp 디렉토리로 바인딩
    monkeypatch.setenv("PRETREND_DATA_ROOT", str(tmp_path))

    cfg = EodIngestConfig.from_default_symbols()
    result = run_eod_bronze_ingest(
        cfg,
        start_date=date(2024, 11, 1),
        end_date=date(2024, 11, 4),
    )

    assert result.row_count >= 0
    assert set(result.symbols) == {"SPY", "QQQ", "VOO"}
