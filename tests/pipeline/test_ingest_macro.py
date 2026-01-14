# tests/pipeline/test_ingest_macro.py

import pandas as pd

from pretrend.pipeline.ingest.base import IngestContext
from pretrend.pipeline.ingest.macro import (
    FredSeriesSpec,
    FredMacroConfig,
    MacroFetcher,
    MacroNormalizer,
)


def test_macro_fetcher_returns_dataframe(monkeypatch):
    """
    MacroFetcher.fetch()가 FRED 응답을 잘 파싱해서
    단일 DataFrame을 반환하는지 검증.
    실제 HTTP 호출은 monkeypatch로 막는다.
    """
    # 1) 테스트용 Config (실제 API Key는 사용하지 않음)
    config = FredMacroConfig(
        api_key="DUMMY_KEY",
        series_list=[
            FredSeriesSpec(
                series_id="TEST_SERIES",
                indicator_id="TEST_INDICATOR",
                unit="Index",
            )
        ],
    )

    context = IngestContext(
        domain="macro",
        dataset="econ_indicators",
        run_id="test_run",
    )

    # 2) requests.get을 FRED 더미 응답으로 치환
    def fake_get(url, params, timeout):
        class DummyResponse:
            def raise_for_status(self):
                pass

            def json(self):
                # value="." 인 것은 스킵되는지까지 검증
                return {
                    "observations": [
                        {"date": "2025-01-01", "value": "100.0"},
                        {"date": "2025-02-01", "value": "101.5"},
                        {"date": "2025-03-01", "value": "."},
                    ]
                }

        return DummyResponse()

    monkeypatch.setattr(
        "pretrend.pipeline.ingest.macro.requests.get",
        fake_get,
    )

    # 3) fetch 실행
    fetcher = MacroFetcher(config=config)
    df = fetcher.fetch(context)

    # 4) 검증
    assert isinstance(df, pd.DataFrame)
    # "." 값은 스킵되므로 2개만 남아야 함
    assert len(df) == 2

    expected_cols = {
        "date",
        "value",
        "indicator_id",
        "unit",
        "source",
        "series_id",
    }
    assert expected_cols.issubset(df.columns)
    assert (df["indicator_id"] == "TEST_INDICATOR").all()
    assert (df["unit"] == "Index").all()
    assert (df["source"] == "FRED").all()
    assert (df["series_id"] == "TEST_SERIES").all()


def test_macro_normalizer_adds_meta_and_casts_types():
    """
    MacroNormalizer가 타입 정리(date/value)와
    run_id, ingestion_ts 메타 컬럼을 잘 추가하는지 검증.
    """
    context = IngestContext(
        domain="macro",
        dataset="econ_indicators",
        run_id="test_run",
    )

    raw_df = pd.DataFrame(
        {
            "date": ["2025-01-01"],
            "value": ["5.0"],
            "indicator_id": ["TEST_IND"],
            "unit": ["Index"],
            "source": ["TEST_SRC"],
            "series_id": ["TEST_SER"],
        }
    )

    normalizer = MacroNormalizer()
    norm = normalizer.normalize(context, raw_df)

    # 컬럼 순서/존재 검증
    assert list(norm.columns) == [
        "indicator_id",
        "date",
        "value",
        "unit",
        "source",
        "run_id",
        "ingestion_ts",
    ]

    # 값/타입 검증
    assert norm.loc[0, "indicator_id"] == "TEST_IND"
    assert norm.loc[0, "unit"] == "Index"
    assert norm.loc[0, "source"] == "TEST_SRC"

    # run_id 부여 여부
    assert norm.loc[0, "run_id"] == context.run_id

    # date는 date 타입으로 변환되어야 함
    assert norm.loc[0, "date"].__class__.__name__ in ("date", "datetime.date")

    # value는 float로 변환되어야 함
    assert isinstance(norm.loc[0, "value"], float)

    # ingestion_ts는 datetime 타입이어야 하고, NaN이면 안 됨
    assert not norm["ingestion_ts"].isna().any()
    # dtype 체크 (string으로부터 to_datetime으로 변환 가능하면 충분)
    pd.to_datetime(norm["ingestion_ts"])  # 예외 없으면 OK

