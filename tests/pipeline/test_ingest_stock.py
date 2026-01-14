# [코드] tests/pipeline/test_ingest_stock.py
import pandas as pd

from pretrend.pipeline.ingest.base import IngestContext
from pretrend.pipeline.ingest.stock import StockConfig, StockFetcher, StockNormalizer


def test_stock_fetcher_returns_datasets(tmp_path):
    """
    StockFetcher가 stock_master / fundamentals 두 개의 DataFrame을
    반환하는지 확인한다.
    """
    config = StockConfig(provider="fmp", api_key=None, universe_seed_path=None)
    context = IngestContext(
        domain="stock",
        dataset="stock_master",
        run_id="test_run_stock",
        output_root=tmp_path / "bronze",
        meta_root=tmp_path / "meta",
    )

    fetcher = StockFetcher(config=config)
    raw = fetcher.fetch(context)

    assert set(raw.keys()) == {"stock_master", "fundamentals"}
    for df in raw.values():
        assert isinstance(df, pd.DataFrame)


def test_stock_normalizer_passes_through_data():
    """
    StockNormalizer가 최소한 입력 row 수를 보존하는지,
    그리고 추후 run_id/ingestion_ts 등을 추가했을 때도
    테스트를 쉽게 확장할 수 있도록 구조를 잡는다.
    """
    context = IngestContext(
        domain="stock",
        dataset="stock_master",
        run_id="test_run_stock",
    )

    stock_master = pd.DataFrame(
        {
            "ticker": ["AAPL"],
            "sector": ["Information Technology"],
            "industry": ["Consumer Electronics"],
            "market_cap": [3_000_000_000_000],
        }
    )
    fundamentals = pd.DataFrame(
        {
            "ticker": ["AAPL"],
            "revenue": [100.0],
            "eps": [6.0],
            "roe": [0.3],
        }
    )

    raw = {
        "stock_master": stock_master,
        "fundamentals": fundamentals,
    }

    normalizer = StockNormalizer()
    normalized = normalizer.normalize(context, raw)

    assert set(normalized.keys()) == {"stock_master", "fundamentals"}
    assert len(normalized["stock_master"]) == 1
    assert len(normalized["fundamentals"]) == 1

    # TODO: 이후 통화/단위 변환, 컬럼 존재 여부, run_id 등 세부 검증 추가
