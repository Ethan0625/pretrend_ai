import pandas as pd

from pretrend.pipeline.ingest.base import IngestContext
from pretrend.pipeline.ingest.theme import ThemeConfig, ThemeFetcher, ThemeNormalizer


def test_theme_fetcher_returns_datasets(tmp_path):
    """
    ThemeFetcher가 최소한 etf_master / etf_holdings / etf_performance
    세 개의 DataFrame을 반환하는지 인터페이스 관점에서 확인한다.
    실제 API 연동 전에는 빈 DataFrame이어도 괜찮다.
    """
    config = ThemeConfig(provider="yahoo", api_key=None)
    context = IngestContext(
        domain="theme",
        dataset="etf_master",
        run_id="test_run_theme",
        output_root=tmp_path / "bronze",
        meta_root=tmp_path / "meta",
    )

    fetcher = ThemeFetcher(config=config)
    raw = fetcher.fetch(context)

    # dict 키 체크
    assert set(raw.keys()) == {"etf_master", "etf_holdings", "etf_performance"}

    # 각 값이 DataFrame인지 체크
    for df in raw.values():
        assert isinstance(df, pd.DataFrame)


def test_theme_normalizer_keeps_required_datasets():
    """
    ThemeNormalizer가 입력으로 받은 세 dataset을 그대로 반환하는지,
    그리고 최소한 run_id / ingestion_ts 같은 컬럼을 추가하는 방향으로
    확장할 수 있도록 구조를 확인한다.
    """
    context = IngestContext(
        domain="theme",
        dataset="etf_master",
        run_id="test_run_theme",
    )

    # 간단한 dummy raw 데이터
    etf_master = pd.DataFrame(
        {
            "symbol": ["SOXX"],
            "name": ["iShares Semiconductor ETF"],
            "theme": ["Semiconductor"],
        }
    )
    etf_holdings = pd.DataFrame(
        {
            "etf_symbol": ["SOXX"],
            "ticker": ["NVDA"],
            "weight": [5.0],
        }
    )
    etf_perf = pd.DataFrame(
        {
            "symbol": ["SOXX"],
            "ret_1m": [0.05],
            "ret_3m": [0.10],
        }
    )

    raw = {
        "etf_master": etf_master,
        "etf_holdings": etf_holdings,
        "etf_performance": etf_perf,
    }

    normalizer = ThemeNormalizer()
    normalized = normalizer.normalize(context, raw)

    # dataset 키 유지 여부
    assert set(normalized.keys()) == {"etf_master", "etf_holdings", "etf_performance"}

    # row 수가 유지되는지 정도는 체크 가능
    assert len(normalized["etf_master"]) == 1
    assert len(normalized["etf_holdings"]) == 1
    assert len(normalized["etf_performance"]) == 1

    # TODO: 추후 run_id, ingestion_ts 컬럼 추가 시 여기에 검증 로직 추가
