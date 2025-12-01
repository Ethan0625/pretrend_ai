import pandas as pd

from pretrend.pipeline.ingest.base import IngestContext
from pretrend.pipeline.ingest.macro import MacroConfig, MacroFetcher, MacroNormalizer


def test_macro_fetcher_returns_datasets(tmp_path):
    config = MacroConfig(fred_api_key="DUMMY")
    context = IngestContext(
        domain="macro",
        dataset="econ_indicators",
        run_id="test_run",
        output_root=tmp_path / "bronze",
        meta_root=tmp_path / "meta",
    )

    fetcher = MacroFetcher(config=config)
    raw = fetcher.fetch(context)

    assert "econ_indicators" in raw
    assert "news_headlines" in raw
    assert isinstance(raw["econ_indicators"], pd.DataFrame)
    assert isinstance(raw["news_headlines"], pd.DataFrame)


def test_macro_normalizer_shape():
    context = IngestContext(
        domain="macro",
        dataset="econ_indicators",
        run_id="test_run",
    )
    econ_df = pd.DataFrame({"date": ["2025-01-01"], "value": [5.0]})
    news_df = pd.DataFrame({"date": ["2025-01-01"], "title": ["test"]})

    raw = {"econ_indicators": econ_df, "news_headlines": news_df}
    normalizer = MacroNormalizer()
    normalized = normalizer.normalize(context, raw)

    assert "econ_indicators" in normalized
    assert "news_headlines" in normalized
    econ_norm = normalized["econ_indicators"]
    news_norm = normalized["news_headlines"]

    for df in (econ_norm, news_norm):
        assert "run_id" in df.columns
        assert "ingestion_ts" in df.columns
        assert (df["run_id"] == context.run_id).all()
        assert pd.api.types.is_datetime64_any_dtype(df["ingestion_ts"])
        assert not df["ingestion_ts"].isna().any()

    assert econ_norm.loc[0, "ingestion_ts"] == news_norm.loc[0, "ingestion_ts"]
